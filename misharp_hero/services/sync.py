from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from misharp_hero.hero_score import postlaunch_score, hero_grade, diagnose
from misharp_hero.repository import (
    current_launches,
    metrics_history,
    latest_sera_by_product,
    latest_inventory_by_product,
    upsert_hero_metric_v2,
    log_sync,
)
from misharp_hero.services.cafe24_analytics import Cafe24AnalyticsClient


def _pick(primary, fallback):
    if primary not in (None, ""):
        return primary
    return fallback


def _map_by_no(data):
    if data is None or data.empty:
        return {}
    return {str(r["product_no"]): r.to_dict() for _, r in data.iterrows()}


def sync_launch_metrics(include_future_close=False, product_no: str | None = None):
    """HERO 관찰상품의 Cafe24 Analytics를 갱신합니다.

    product_no가 주어지면 해당 상품만 즉시 갱신합니다.
    예약 실행에서는 product_no를 생략해 전체 관찰상품을 갱신합니다.
    """
    launches = current_launches(only_observed=True)
    if product_no is not None and not launches.empty:
        target_no = str(product_no).strip()
        launches = launches[launches["product_no"].astype(str) == target_no].copy()
    if launches.empty:
        return 0

    history = metrics_history()
    sera_map = _map_by_no(latest_sera_by_product())
    inv_map = _map_by_no(latest_inventory_by_product())
    client = Cafe24AnalyticsClient()
    now = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
    count = 0

    # 동일 시간창은 API 결과를 재사용
    window_cache = {}

    for _, row in launches.iterrows():
        product_no = str(row.get("product_no") or "").strip()
        if not product_no:
            continue
        start_at = pd.to_datetime(row["launch_at"]).to_pydatetime()
        close_at = pd.to_datetime(row["close_48h_at"]).to_pydatetime()
        end_at = min(now, close_at)
        if end_at <= start_at:
            continue
        if not include_future_close and now < start_at:
            continue

        cache_key = (start_at.replace(second=0, microsecond=0), end_at.replace(second=0, microsecond=0))
        if cache_key not in window_cache:
            rows = client.merged_product_metrics(start_at, end_at)
            window_cache[cache_key] = {str(x["product_no"]): x for x in rows}
        analytics = window_cache[cache_key].get(product_no, {})
        sera = sera_map.get(product_no, {})
        inv = inv_map.get(product_no, {})

        a_views = int(analytics.get("views") or 0)
        a_orders = int(analytics.get("order_count") or 0)
        a_qty = int(analytics.get("qty") or 0)
        a_revenue = float(analytics.get("revenue") or 0)
        a_cart = int(analytics.get("cart_count") or 0)
        a_cart_rate = float(analytics.get("cart_rate") or 0)

        s_views = sera.get("sera_views")
        s_orders = sera.get("sera_orders")
        s_qty = sera.get("sera_qty")
        s_revenue = sera.get("sera_revenue")

        # Cafe24 Analytics를 1차 공식값, SERA를 보완/교차검증으로 사용
        views = a_views if a_views > 0 else int(s_views or 0)
        orders = a_orders if a_orders > 0 else int(s_orders or 0)
        qty = a_qty if a_qty > 0 else int(s_qty or 0)
        revenue = a_revenue if a_revenue > 0 else float(s_revenue or 0)
        cvr = orders / views if views else 0
        qty_cvr = qty / views if views else 0
        rpv = revenue / views if views else 0
        stock_qty = inv.get("sellmate_stock_qty")

        metric = {
            "launch_id": int(row["id"]),
            "product_no": product_no,
            "start_at": start_at,
            "end_at": end_at,
            "analytics_views": a_views,
            "analytics_cart_count": a_cart,
            "analytics_cart_rate": a_cart_rate,
            "analytics_order_count": a_orders,
            "analytics_qty": a_qty,
            "analytics_revenue": a_revenue,
            "sera_views": None if pd.isna(s_views) else s_views,
            "sera_orders": None if pd.isna(s_orders) else s_orders,
            "sera_qty": None if pd.isna(s_qty) else s_qty,
            "sera_revenue": None if pd.isna(s_revenue) else s_revenue,
            "sera_opv": None if pd.isna(sera.get("sera_opv")) else sera.get("sera_opv"),
            "sera_espv": None if pd.isna(sera.get("sera_espv")) else sera.get("sera_espv"),
            "sera_click_value": None if pd.isna(sera.get("sera_click_value")) else sera.get("sera_click_value"),
            "views": views,
            "cart_count": a_cart,
            "cart_rate": a_cart_rate if a_cart_rate else (a_cart / views if views else 0),
            "order_count": orders,
            "qty": qty,
            "revenue": revenue,
            "cvr": cvr,
            "qty_cvr": qty_cvr,
            "rpv": rpv,
            "sellmate_stock_qty": None if pd.isna(stock_qty) else int(stock_qty),
            "source_confidence": "A" if analytics else ("B" if sera else "C"),
            "collected_at": datetime.utcnow(),
        }
        score = postlaunch_score(metric, history)
        metric["hero_score"] = score
        metric["hero_grade"] = hero_grade(score)
        metric["diagnosis"] = diagnose(
            views,
            cvr,
            history,
            cart_rate=metric["cart_rate"],
            stock_qty=metric["sellmate_stock_qty"],
        )
        upsert_hero_metric_v2(metric)
        count += 1

    log_sync("48H HERO", "성공", f"{count}개")
    return count
