from __future__ import annotations
import time
from datetime import datetime
import requests
from misharp_hero.config import CAFE24_MALL_ID
from misharp_hero.services.oauth import valid_access_token, load_token

class Cafe24AnalyticsClient:
    BASE = "https://ca-api.cafe24data.com"

    def __init__(self, throttle_seconds=1.55):
        self.throttle_seconds = throttle_seconds
        self._last = 0.0

    def _token(self):
        # Cafe24 Analytics API는 Analytics 앱의 별도 OAuth 인증을 사용합니다.
        if not load_token("analytics"):
            raise RuntimeError("Cafe24 Analytics 전용 OAuth 토큰이 없습니다. 설정·연동에서 Analytics 인증을 먼저 완료하세요.")
        token = valid_access_token("analytics")
        if not token:
            raise RuntimeError("Cafe24 Analytics OAuth 토큰을 갱신할 수 없습니다.")
        return token

    def _wait(self):
        elapsed = time.time() - self._last
        if elapsed < self.throttle_seconds:
            time.sleep(self.throttle_seconds - elapsed)

    def get(self, path, params):
        self._wait()
        r = requests.get(
            f"{self.BASE}{path}",
            headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"},
            params=params,
            timeout=40,
        )
        self._last = time.time()
        if r.status_code == 429:
            time.sleep(3)
            r = requests.get(
                f"{self.BASE}{path}",
                headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"},
                params=params,
                timeout=40,
            )
            self._last = time.time()
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _rows(payload):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for k, v in payload.items():
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for vv in v.values():
                    if isinstance(vv, list):
                        return vv
        return []

    def product_view(self, start_at: datetime, end_at: datetime):
        params = {
            "mall_id": CAFE24_MALL_ID,
            "shop_no": 1,
            "start_date": start_at.strftime("%Y-%m-%d"),
            "end_date": end_at.strftime("%Y-%m-%d"),
            "start_datetime": start_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_datetime": end_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "timezone": "Asia/Seoul",
            "limit": 1000,
            "offset": 0,
        }
        return self._rows(self.get("/products/view", params))

    def product_sales(self, start_at: datetime, end_at: datetime):
        params = {
            "mall_id": CAFE24_MALL_ID,
            "shop_no": 1,
            "start_date": start_at.strftime("%Y-%m-%d"),
            "end_date": end_at.strftime("%Y-%m-%d"),
            "start_datetime": start_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_datetime": end_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "timezone": "Asia/Seoul",
            "limit": 1000,
            "offset": 0,
        }
        return self._rows(self.get("/products/sales", params))

def merge_product_metric(product_no, views_rows, sales_rows):
    key = str(product_no or "").strip()
    v = next((x for x in views_rows if str(x.get("product_no") or "").strip() == key), {})
    s = next((x for x in sales_rows if str(x.get("product_no") or "").strip() == key), {})
    views = int(float(v.get("count") or v.get("view_count") or 0))
    orders = int(float(s.get("order_count") or 0))
    qty = int(float(s.get("order_product_count") or s.get("qty") or 0))
    revenue = float(s.get("order_amount") or 0)
    return {
        "views": views,
        "order_count": orders,
        "qty": qty,
        "revenue": revenue,
        "cvr": orders / views if views else 0,
        "qty_cvr": qty / views if views else 0,
        "rpv": revenue / views if views else 0,
    }
