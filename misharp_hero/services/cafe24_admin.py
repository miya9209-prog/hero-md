from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from misharp_hero.config import CAFE24_MALL_ID, CAFE24_API_VERSION
from misharp_hero.db import get_engine
from misharp_hero.models import Product
from misharp_hero.repository import log_sync
from misharp_hero.services.oauth import valid_access_token


class Cafe24AdminClient:
    def __init__(self):
        if not CAFE24_MALL_ID:
            raise RuntimeError("CAFE24_MALL_ID가 없습니다.")
        self.base = f"https://{CAFE24_MALL_ID}.cafe24api.com/api/v2/admin"

    def headers(self):
        token = valid_access_token("admin")
        if not token:
            raise RuntimeError("Cafe24 Admin 인증토큰이 없습니다.")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Cafe24-Api-Version": CAFE24_API_VERSION,
        }

    def get(self, path, params=None):
        url = f"{self.base}{path}"
        last_error = None
        token = valid_access_token("admin")
        if not token:
            raise RuntimeError("Cafe24 Admin 인증토큰이 없습니다.")

        for attempt in range(5):
            try:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Cafe24-Api-Version": CAFE24_API_VERSION,
                }
                r = requests.get(url, headers=headers, params=params or {}, timeout=40)

                if r.status_code == 401:
                    # Force one authoritative refresh after server rejection.
                    token = valid_access_token("admin", force_refresh=True)
                    if token and attempt < 4:
                        time.sleep(0.2)
                        continue

                if r.status_code == 429:
                    time.sleep(2 + attempt * 2)
                    continue
                if 500 <= r.status_code < 600:
                    last_error = RuntimeError(f"Cafe24 서버 오류 {r.status_code}")
                    time.sleep(1 + attempt * 2)
                    continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                last_error = e
                if attempt < 4:
                    time.sleep(1 + attempt * 2)
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("Cafe24 API 호출에 실패했습니다.")

    def fetch_product_page(self, since_product_no=0, limit=100):
        data = self.get(
            "/products",
            {"limit": min(max(int(limit), 1), 100), "since_product_no": int(since_product_no)},
        )
        return data.get("products", []) if isinstance(data, dict) else []

    def fetch_updated_products(self, start_at: datetime, end_at: datetime, limit=100):
        rows, offset = [], 0
        while True:
            params = {
                "limit": min(max(int(limit), 1), 100),
                "offset": offset,
                "updated_start_date": start_at.isoformat(timespec="seconds"),
                "updated_end_date": end_at.isoformat(timespec="seconds"),
            }
            data = self.get("/products", params)
            part = data.get("products", []) if isinstance(data, dict) else []
            rows.extend(part)
            if len(part) < params["limit"]:
                break
            offset += params["limit"]
            if offset >= 5000:
                # 변경상품이 5천개 이상이면 안전하게 전체 동기화 권장
                raise RuntimeError("수정상품이 5,000개 이상입니다. 전체 상품 동기화를 실행하세요.")
        return rows


def _num(v):
    try:
        if v is None or v == "":
            return None
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def _dt(v):
    if not v:
        return None
    try:
        # Cafe24 ISO 문자열의 timezone 정보는 DB 호환을 위해 제거한다.
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _flag(v):
    if v is None or v == "":
        return None
    raw = str(v).strip().upper()
    if raw in {"T", "TRUE", "Y", "YES", "1"}:
        return "T"
    if raw in {"F", "FALSE", "N", "NO", "0"}:
        return "F"
    return raw[:20]


def normalize_product(p):
    return {
        "product_no": str(p.get("product_no") or "").strip() or None,
        "product_code": str(p.get("product_code") or "").strip() or None,
        "product_name": p.get("product_name") or p.get("name") or "",
        "supplier_name": p.get("supplier_name") or "",
        "category": p.get("category_name") or "",
        "supply_price": _num(p.get("supply_price")),
        "selling_price": _num(p.get("price") or p.get("selling_price")),
        "retail_price": _num(p.get("retail_price")),
        "display": _flag(p.get("display")),
        "selling": _flag(p.get("selling")),
        "cafe24_created_at": _dt(p.get("created_date") or p.get("created_at")),
        "cafe24_updated_at": _dt(p.get("updated_date") or p.get("updated_at")),
        # 중요: Cafe24 Admin의 stock_quantity는 HERO ITEM OS 실제 재고로 사용하지 않음.
        "image_url": p.get("detail_image") or p.get("list_image") or p.get("image_url") or "",
        "updated_at": datetime.utcnow(),
    }


def _chunks(rows, size):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def bulk_upsert_products(raw_rows, batch_size=500):
    rows = [normalize_product(r) for r in raw_rows]
    rows = [r for r in rows if r.get("product_no")]
    if not rows:
        return 0

    engine = get_engine()
    saved = 0
    with engine.begin() as conn:
        for batch in _chunks(rows, batch_size):
            if engine.dialect.name == "postgresql":
                stmt = pg_insert(Product).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[Product.product_no],
                    set_={
                        "product_code": stmt.excluded.product_code,
                        "product_name": stmt.excluded.product_name,
                        "supplier_name": stmt.excluded.supplier_name,
                        "category": stmt.excluded.category,
                        "supply_price": stmt.excluded.supply_price,
                        "selling_price": stmt.excluded.selling_price,
                        "retail_price": stmt.excluded.retail_price,
                        "display": stmt.excluded.display,
                        "selling": stmt.excluded.selling,
                        "cafe24_created_at": stmt.excluded.cafe24_created_at,
                        "cafe24_updated_at": stmt.excluded.cafe24_updated_at,
                        "image_url": stmt.excluded.image_url,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
            elif engine.dialect.name == "sqlite":
                stmt = sqlite_insert(Product).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["product_no"],
                    set_={
                        "product_code": stmt.excluded.product_code,
                        "product_name": stmt.excluded.product_name,
                        "supplier_name": stmt.excluded.supplier_name,
                        "category": stmt.excluded.category,
                        "supply_price": stmt.excluded.supply_price,
                        "selling_price": stmt.excluded.selling_price,
                        "retail_price": stmt.excluded.retail_price,
                        "display": stmt.excluded.display,
                        "selling": stmt.excluded.selling,
                        "cafe24_created_at": stmt.excluded.cafe24_created_at,
                        "cafe24_updated_at": stmt.excluded.cafe24_updated_at,
                        "image_url": stmt.excluded.image_url,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
            else:
                raise RuntimeError(f"지원하지 않는 DB: {engine.dialect.name}")
            conn.execute(stmt)
            saved += len(batch)
    return saved


def sync_products_full():
    client = Cafe24AdminClient()
    total_saved = 0
    since_product_no = 0
    buffer = []
    seen = set()

    while True:
        products = client.fetch_product_page(since_product_no=since_product_no, limit=100)
        if not products:
            break
        buffer.extend(products)
        nums = []
        for p in products:
            try:
                nums.append(int(p.get("product_no")))
            except Exception:
                pass
        if not nums:
            raise RuntimeError("Cafe24 상품번호를 확인할 수 없습니다.")
        next_no = max(nums)
        if next_no <= since_product_no or next_no in seen:
            raise RuntimeError(f"Cafe24 상품 조회가 반복됩니다. product_no={next_no}")
        seen.add(next_no)
        since_product_no = next_no

        if len(buffer) >= 500:
            total_saved += bulk_upsert_products(buffer)
            buffer = []
        if len(products) < 100:
            break
        time.sleep(0.05)

    if buffer:
        total_saved += bulk_upsert_products(buffer)

    log_sync("Cafe24 상품마스터", "성공", f"전체 {total_saved}개")
    return total_saved


def sync_products_incremental(hours=48):
    end_at = datetime.now(ZoneInfo("Asia/Seoul"))
    start_at = end_at - timedelta(hours=int(hours))
    client = Cafe24AdminClient()
    rows = client.fetch_updated_products(start_at, end_at)
    count = bulk_upsert_products(rows)
    log_sync("Cafe24 상품마스터", "성공", f"최근 {hours}시간 수정 {count}개")
    return count


# 기존 버튼/스크립트 호환
sync_products = sync_products_full
