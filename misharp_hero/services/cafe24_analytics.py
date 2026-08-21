from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from misharp_hero.config import CAFE24_MALL_ID, CAFE24_SHOP_NO
from misharp_hero.repository import upsert_analytics_daily, log_sync
from misharp_hero.services.oauth import valid_access_token


class Cafe24AnalyticsClient:
    BASE = "https://ca-api.cafe24data.com"

    def __init__(self, throttle_seconds=0.55):
        self.throttle_seconds = throttle_seconds
        self._last = 0.0

    def _token(self):
        token = valid_access_token("admin")
        if not token:
            raise RuntimeError("Cafe24 OAuth 토큰이 없습니다.")
        return token

    def _wait(self):
        elapsed = time.time() - self._last
        if elapsed < self.throttle_seconds:
            time.sleep(self.throttle_seconds - elapsed)

    def get(self, path, params):
        """GET with automatic token refresh on HTTP 401.

        A stored expiry timestamp is only a hint. Cafe24 can invalidate an
        access token earlier, so one forced refresh+retry is the authoritative
        recovery path.
        """
        url = f"{self.BASE}{path}"
        token = self._token()

        for auth_attempt in range(2):
            self._wait()
            r = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                params=params,
                timeout=45,
            )
            self._last = time.time()

            if r.status_code == 401 and auth_attempt == 0:
                token = valid_access_token("admin", force_refresh=True)
                if not token:
                    break
                continue

            if r.status_code == 429:
                time.sleep(3)
                continue

            if r.ok:
                return r.json()

            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise RuntimeError(f"Cafe24 Analytics 실패 {r.status_code}: {detail}")

        raise RuntimeError("Cafe24 Analytics 인증 갱신에 실패했습니다. 데이터·설정에서 Cafe24 권한을 다시 승인해주세요.")

    @staticmethod
    def _rows(payload):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        # API 응답 버전에 따라 최상단 또는 resource 내부 리스트를 모두 대응
        for key in ("resource", "products", "carts", "data"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for vv in v.values():
                    if isinstance(vv, list):
                        return vv
        for v in payload.values():
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for vv in v.values():
                    if isinstance(vv, list):
                        return vv
        return []

    def paginate(self, path, params, limit=1000):
        rows = []
        offset = 0
        limit = min(max(int(limit), 50), 1000)
        while True:
            p = dict(params)
            p.update({"limit": limit, "offset": offset})
            part = self._rows(self.get(path, p))
            rows.extend(part)
            if len(part) < limit:
                break
            offset += limit
        return rows

    def _base_params(self, start_at: datetime, end_at: datetime):
        return {
            "mall_id": CAFE24_MALL_ID,
            "shop_no": CAFE24_SHOP_NO,
            "start_date": start_at.strftime("%Y-%m-%d"),
            "end_date": end_at.strftime("%Y-%m-%d"),
            "start_datetime": start_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_datetime": end_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "timezone": "Asia/Seoul",
        }

    def product_views(self, start_at: datetime, end_at: datetime):
        return self.paginate("/products/view", self._base_params(start_at, end_at))

    def product_sales(self, start_at: datetime, end_at: datetime):
        return self.paginate("/products/sales", self._base_params(start_at, end_at))

    def carts_action(self, start_at: datetime, end_at: datetime):
        return self.paginate("/carts/action", self._base_params(start_at, end_at))

    def merged_product_metrics(self, start_at: datetime, end_at: datetime):
        views = self.product_views(start_at, end_at)
        sales = self.product_sales(start_at, end_at)
        carts = self.carts_action(start_at, end_at)
        return merge_metric_rows(views, sales, carts)


def _int(v):
    try:
        return int(float(v or 0))
    except Exception:
        return 0


def _float(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def merge_metric_rows(views_rows, sales_rows, cart_rows):
    merged = {}

    def item(no):
        no = str(no or "").strip()
        if not no:
            return None
        return merged.setdefault(
            no,
            {
                "product_no": no,
                "product_name": "",
                "views": 0,
                "cart_count": 0,
                "cart_rate": 0.0,
                "order_count": 0,
                "qty": 0,
                "revenue": 0.0,
            },
        )

    for r in views_rows:
        x = item(r.get("product_no"))
        if x:
            x["product_name"] = r.get("product_name") or x["product_name"]
            x["views"] = _int(r.get("count") or r.get("view_count"))

    for r in sales_rows:
        x = item(r.get("product_no"))
        if x:
            x["product_name"] = r.get("product_name") or x["product_name"]
            x["order_count"] = _int(r.get("order_count"))
            x["qty"] = _int(r.get("order_product_count") or r.get("qty"))
            x["revenue"] = _float(r.get("order_amount"))

    for r in cart_rows:
        x = item(r.get("product_no"))
        if x:
            x["product_name"] = r.get("product_name") or x["product_name"]
            x["cart_count"] = _int(r.get("add_cart_count"))
            raw_rate = _float(r.get("add_cart_rate"))
            x["cart_rate"] = raw_rate / 100 if raw_rate > 1 else raw_rate

    # API 장바구니율이 비어 있으면 조회수 기준 계산
    for x in merged.values():
        if not x["cart_rate"] and x["views"]:
            x["cart_rate"] = x["cart_count"] / x["views"]
    return list(merged.values())


def sync_analytics_day(target_date: date):
    start_at = datetime.combine(target_date, datetime.min.time())
    end_at = datetime.combine(target_date, datetime.max.time()).replace(microsecond=0)
    client = Cafe24AnalyticsClient()
    rows = client.merged_product_metrics(start_at, end_at)
    payload = []
    now = datetime.utcnow()
    for r in rows:
        payload.append(
            {
                "metric_date": target_date.isoformat(),
                "product_no": str(r["product_no"]),
                "product_name": r.get("product_name") or "",
                "views": r.get("views", 0),
                "cart_count": r.get("cart_count", 0),
                "cart_rate": r.get("cart_rate", 0),
                "order_count": r.get("order_count", 0),
                "qty": r.get("qty", 0),
                "revenue": r.get("revenue", 0),
                "raw_json": json.dumps(r, ensure_ascii=False),
                "collected_at": now,
            }
        )
    count = upsert_analytics_daily(payload)
    log_sync("Cafe24 Analytics", "성공", f"{target_date.isoformat()} {count}개 상품")
    return count


def sync_analytics_days(days=2, include_today=True):
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    total = 0
    start_offset = 0 if include_today else 1
    for n in range(start_offset, start_offset + int(days)):
        total += sync_analytics_day(today - timedelta(days=n))
    return total
