from __future__ import annotations
import time
import requests
from misharp_hero.config import CAFE24_MALL_ID, CAFE24_API_VERSION
from misharp_hero.services.oauth import valid_access_token
from misharp_hero.repository import upsert_product, log_sync

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
        r = requests.get(f"{self.base}{path}", headers=self.headers(), params=params or {}, timeout=40)
        if r.status_code == 429:
            time.sleep(2)
            r = requests.get(f"{self.base}{path}", headers=self.headers(), params=params or {}, timeout=40)
        r.raise_for_status()
        return r.json()

    def fetch_products(self, limit=100, max_pages=50):
        rows, offset = [], 0
        limit = min(int(limit), 100)
        for _ in range(max_pages):
            if offset >= 5000:
                break
            data = self.get("/products", {"limit": limit, "offset": offset})
            part = data.get("products", []) if isinstance(data, dict) else []
            rows.extend(part)
            if len(part) < limit:
                break
            offset += limit
        return rows

def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None

def normalize_product(p):
    return {
        "product_no": str(p.get("product_no") or "").strip() or None,
        "product_code": str(p.get("product_code") or "").strip() or None,
        "product_name": p.get("product_name") or p.get("name") or "",
        "supplier_name": p.get("supplier_name") or "",
        "category": p.get("category_name") or "",
        "selling_price": _num(p.get("price") or p.get("selling_price")),
        "stock_qty": int(_num(p.get("stock_quantity") or p.get("quantity")) or 0),
        "image_url": p.get("detail_image") or p.get("list_image") or p.get("image_url") or "",
    }

def sync_products():
    client = Cafe24AdminClient()
    products = client.fetch_products()
    count = 0
    for p in products:
        upsert_product(normalize_product(p))
        count += 1
    log_sync("Cafe24 Admin 상품", "성공", f"{count}개")
    return count
