from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from misharp_hero.repository import current_launches, log_sync, update_return_metric
from misharp_hero.services.cafe24_admin import Cafe24AdminClient

# Cafe24: 반품 완료/환불 단계. 요청/접수 단계는 실제 반품률에 포함하지 않는다.
RETURN_COMPLETED_STATUSES = {"R40", "R41", "R42", "R43"}


def _int(v):
    try:
        return int(float(v or 0))
    except Exception:
        return 0


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "item", "orders", "data", "resource"):
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
        return [value]
    return []


def _orders_rows(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("orders", "resource", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for inner in value.values():
                if isinstance(inner, list):
                    return inner
    return []


def _returned_qty_from_orders(orders, product_no: str):
    """Cafe24 주문 응답에서 특정 상품의 반품완료 수량과 주문수를 계산한다.

    order_status가 R40~R43이거나 status_code가 C3(Return)인 주문상품만 포함한다.
    부분반품이면 claim_quantity를 우선하고, 없으면 quantity를 사용한다.
    """
    target = str(product_no).strip()
    returned_qty = 0
    returned_orders = set()

    for order in orders or []:
        order_id = str(order.get("order_id") or "").strip()
        items = _as_list(order.get("items"))
        if not items and isinstance(order.get("item"), (list, dict)):
            items = _as_list(order.get("item"))

        matched_this_order = False
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("product_no") or "").strip() != target:
                continue

            order_status = str(item.get("order_status") or "").strip().upper()
            status_code = str(item.get("status_code") or "").strip().upper()
            claim_type = str(item.get("claim_type") or "").strip().lower()
            return_done = (
                order_status in RETURN_COMPLETED_STATUSES
                or status_code == "C3"
                or claim_type in {"return", "returned"}
            )
            if not return_done:
                continue

            claim_qty = _int(item.get("claim_quantity"))
            qty = claim_qty if claim_qty > 0 else _int(item.get("quantity"))
            if qty <= 0:
                continue

            returned_qty += qty
            matched_this_order = True

        if matched_this_order and order_id:
            returned_orders.add(order_id)

    return len(returned_orders), returned_qty


class Cafe24ReturnClient:
    """HERO 최초 48시간 구매 cohort의 완료 반품을 조회한다."""

    def __init__(self):
        self.client = Cafe24AdminClient()

    def returned_orders_for_product(self, product_no: str, start_at: datetime, end_at: datetime):
        rows = []
        offset = 0
        limit = 1000
        while True:
            params = {
                "shop_no": 1,
                "start_date": start_at.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": end_at.strftime("%Y-%m-%d %H:%M:%S"),
                "date_type": "order_date",
                "product_no": str(product_no),
                "order_status": ",".join(sorted(RETURN_COMPLETED_STATUSES)),
                "embed": "items",
                "limit": limit,
                "offset": offset,
            }
            payload = self.client.get("/orders", params)
            part = _orders_rows(payload)
            rows.extend(part)
            if len(part) < limit:
                break
            offset += limit
            if offset > 15000:
                raise RuntimeError("Cafe24 반품 주문 조회가 15,000건을 초과했습니다.")
        return rows

    def cohort_return_stats(self, product_no: str, start_at: datetime, end_at: datetime):
        orders = self.returned_orders_for_product(product_no, start_at, end_at)
        order_count, qty = _returned_qty_from_orders(orders, product_no)
        return {"return_order_count": order_count, "return_qty": qty}


def sync_return_metrics(product_no: str | None = None):
    """48시간이 완료된 관찰상품의 '초기 48H cohort 반품률'을 갱신한다.

    분모: Cafe24 Analytics 최초 48시간 판매수량(hero_metrics_v2.qty)
    분자: 그 최초 48시간에 주문된 상품 중 Cafe24에서 반품 완료된 수량

    반품은 시간 지연 지표이므로 HERO Score에는 포함하지 않고 사후판단에만 사용한다.
    """
    launches = current_launches(only_observed=True)
    if launches.empty:
        return 0

    now = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
    launches = launches[pd.to_datetime(launches["close_48h_at"]) < now].copy()
    if product_no is not None and not launches.empty:
        target = str(product_no).strip()
        launches = launches[launches["product_no"].astype(str) == target].copy()
    if launches.empty:
        return 0

    client = Cafe24ReturnClient()
    count = 0
    for _, row in launches.iterrows():
        launch_id = int(row["id"])
        pno = str(row.get("product_no") or "").strip()
        if not pno:
            continue

        start_at = pd.to_datetime(row["launch_at"]).to_pydatetime()
        close_at = pd.to_datetime(row["close_48h_at"]).to_pydatetime()
        sold_qty = _int(row.get("qty"))

        stats = client.cohort_return_stats(pno, start_at, close_at)
        return_qty = _int(stats.get("return_qty"))
        return_orders = _int(stats.get("return_order_count"))
        return_rate = (return_qty / sold_qty) if sold_qty > 0 else None

        update_return_metric(
            launch_id=launch_id,
            return_order_count=return_orders,
            return_qty=return_qty,
            return_rate=return_rate,
            collected_at=datetime.utcnow(),
        )
        count += 1

    log_sync("Cafe24 반품률", "성공", f"{count}개")
    return count
