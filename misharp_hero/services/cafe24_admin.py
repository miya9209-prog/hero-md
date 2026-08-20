from __future__ import annotations

import time
from datetime import datetime

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

        self.base = (
            f"https://{CAFE24_MALL_ID}.cafe24api.com/api/v2/admin"
        )

    def headers(self):
        token = valid_access_token("admin")

        if not token:
            raise RuntimeError(
                "Cafe24 Admin 인증토큰이 없습니다."
            )

        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Cafe24-Api-Version": CAFE24_API_VERSION,
        }

    def get(self, path, params=None):
        url = f"{self.base}{path}"
        last_error = None

        for attempt in range(5):
            try:
                r = requests.get(
                    url,
                    headers=self.headers(),
                    params=params or {},
                    timeout=40,
                )

                if r.status_code == 429:
                    time.sleep(2 + attempt * 2)
                    continue

                if 500 <= r.status_code < 600:
                    last_error = RuntimeError(
                        f"Cafe24 서버 오류 {r.status_code}"
                    )
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

        raise RuntimeError(
            "Cafe24 API 호출에 실패했습니다."
        )

    def fetch_product_page(
        self,
        since_product_no=0,
        limit=100,
    ):
        limit = min(
            max(int(limit), 1),
            100,
        )

        data = self.get(
            "/products",
            {
                "limit": limit,
                "since_product_no": int(since_product_no),
            },
        )

        if not isinstance(data, dict):
            return []

        return data.get("products", []) or []


def _num(v):
    try:
        if v is None or v == "":
            return None

        return float(
            str(v)
            .replace(",", "")
            .strip()
        )

    except Exception:
        return None


def normalize_product(p):
    product_no = p.get("product_no")

    if product_no is not None:
        product_no = str(product_no).strip()

    return {
        "product_no": product_no or None,

        "product_code": (
            str(
                p.get("product_code")
                or ""
            ).strip()
            or None
        ),

        "product_name": (
            p.get("product_name")
            or p.get("name")
            or ""
        ),

        "supplier_name": (
            p.get("supplier_name")
            or ""
        ),

        "category": (
            p.get("category_name")
            or ""
        ),

        "selling_price": _num(
            p.get("price")
            or p.get("selling_price")
        ),

        "stock_qty": int(
            _num(
                p.get("stock_quantity")
                or p.get("quantity")
            )
            or 0
        ),

        "image_url": (
            p.get("detail_image")
            or p.get("list_image")
            or p.get("image_url")
            or ""
        ),
    }


def _chunks(rows, size):
    for i in range(
        0,
        len(rows),
        size,
    ):
        yield rows[i:i + size]


def bulk_upsert_products(
    rows,
    batch_size=500,
):
    cleaned = []

    for row in rows:
        item = normalize_product(row)

        if not item.get("product_no"):
            continue

        cleaned.append(item)

    if not cleaned:
        return 0

    engine = get_engine()
    dialect = engine.dialect.name

    saved = 0

    with engine.begin() as conn:

        for batch in _chunks(
            cleaned,
            batch_size,
        ):

            if dialect == "postgresql":

                stmt = pg_insert(
                    Product
                ).values(batch)

                stmt = (
                    stmt.on_conflict_do_update(
                        index_elements=[
                            Product.product_no
                        ],
                        set_={
                            "product_code":
                                stmt.excluded.product_code,

                            "product_name":
                                stmt.excluded.product_name,

                            "supplier_name":
                                stmt.excluded.supplier_name,

                            "category":
                                stmt.excluded.category,

                            "selling_price":
                                stmt.excluded.selling_price,

                            "stock_qty":
                                stmt.excluded.stock_qty,

                            "image_url":
                                stmt.excluded.image_url,

                            "updated_at":
                                datetime.utcnow(),
                        },
                    )
                )

                conn.execute(stmt)

            elif dialect == "sqlite":

                stmt = sqlite_insert(
                    Product
                ).values(batch)

                stmt = (
                    stmt.on_conflict_do_update(
                        index_elements=[
                            "product_no"
                        ],
                        set_={
                            "product_code":
                                stmt.excluded.product_code,

                            "product_name":
                                stmt.excluded.product_name,

                            "supplier_name":
                                stmt.excluded.supplier_name,

                            "category":
                                stmt.excluded.category,

                            "selling_price":
                                stmt.excluded.selling_price,

                            "stock_qty":
                                stmt.excluded.stock_qty,

                            "image_url":
                                stmt.excluded.image_url,

                            "updated_at":
                                datetime.utcnow(),
                        },
                    )
                )

                conn.execute(stmt)

            else:
                raise RuntimeError(
                    "지원하지 않는 DB 종류입니다: "
                    f"{dialect}"
                )

            saved += len(batch)

    return saved


def sync_products():
    client = Cafe24AdminClient()

    total_saved = 0
    since_product_no = 0

    buffer = []
    seen_last_numbers = set()

    while True:
        products = client.fetch_product_page(
            since_product_no=since_product_no,
            limit=100,
        )

        if not products:
            break

        buffer.extend(products)

        product_numbers = []

        for product in products:
            try:
                number = int(
                    product.get("product_no")
                )
                product_numbers.append(number)
            except Exception:
                continue

        if not product_numbers:
            raise RuntimeError(
                "Cafe24 상품번호를 확인할 수 없습니다."
            )

        next_since_product_no = max(
            product_numbers
        )

        if (
            next_since_product_no
            <= since_product_no
        ):
            raise RuntimeError(
                "Cafe24 상품 조회 위치가 진행되지 않습니다. "
                f"현재 상품번호: {since_product_no}, "
                f"다음 상품번호: {next_since_product_no}"
            )

        if (
            next_since_product_no
            in seen_last_numbers
        ):
            raise RuntimeError(
                "Cafe24 상품 조회가 반복되고 있습니다. "
                f"상품번호: {next_since_product_no}"
            )

        seen_last_numbers.add(
            next_since_product_no
        )

        since_product_no = (
            next_since_product_no
        )

        if len(buffer) >= 500:
            total_saved += (
                bulk_upsert_products(
                    buffer,
                    batch_size=500,
                )
            )

            buffer = []

        if len(products) < 100:
            break

        # Cafe24 API 호출이 너무 몰리지 않도록
        # 아주 짧게 간격을 둡니다.
        time.sleep(0.05)

    if buffer:
        total_saved += (
            bulk_upsert_products(
                buffer,
                batch_size=500,
            )
        )

    log_sync(
        "Cafe24 Admin 상품",
        "성공",
        f"{total_saved}개 전체 동기화",
    )

    return total_saved
