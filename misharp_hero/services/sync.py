from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from misharp_hero.hero_score import postlaunch_score, hero_grade, diagnose_with_why
from misharp_hero.repository import (
    current_launches,
    three_year_history_benchmark,
    upsert_hero_metric_v2,
    log_sync,
)
from misharp_hero.services.cafe24_analytics import Cafe24AnalyticsClient


def sync_launch_metrics(include_future_close=False, product_no: str | None = None):
    """상품 탐색 대상의 Cafe24 Analytics를 갱신한다.

    v3.0 원칙:
    - 공식 판정 데이터는 Cafe24 Analytics 하나만 사용한다.
    - SERA와 Sellmate 값을 fallback/혼합하지 않는다.
    - product_no가 주어지면 신상품 등록 직후 해당 상품 1개만 즉시 수집한다.
    """
    launches = current_launches(only_observed=True)
    if product_no is not None and not launches.empty:
        target_no = str(product_no).strip()
        launches = launches[launches["product_no"].astype(str) == target_no].copy()
    if launches.empty:
        return 0

    history = three_year_history_benchmark()
    client = Cafe24AnalyticsClient()
    now = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
    count = 0

    # 동일 시간창은 API 결과 재사용
    window_cache: dict[tuple, dict[str, dict]] = {}

    for _, row in launches.iterrows():
        pno = str(row.get("product_no") or "").strip()
        if not pno:
            continue

        start_at = pd.to_datetime(row["launch_at"]).to_pydatetime()
        close_at = pd.to_datetime(row["close_48h_at"]).to_pydatetime()
        end_at = min(now, close_at)

        if end_at <= start_at:
            continue
        if not include_future_close and now < start_at:
            continue

        cache_key = (
            start_at.replace(second=0, microsecond=0),
            end_at.replace(second=0, microsecond=0),
        )
        if cache_key not in window_cache:
            rows = client.merged_product_metrics(start_at, end_at)
            window_cache[cache_key] = {str(x["product_no"]): x for x in rows}

        analytics = window_cache[cache_key].get(pno, {})

        views = int(analytics.get("views") or 0)
        orders = int(analytics.get("order_count") or 0)
        qty = int(analytics.get("qty") or 0)
        revenue = float(analytics.get("revenue") or 0)
        cart_count = int(analytics.get("cart_count") or 0)
        cart_rate = float(analytics.get("cart_rate") or 0)
        if not cart_rate and views:
            cart_rate = cart_count / views

        cvr = orders / views if views else 0.0
        qty_cvr = qty / views if views else 0.0
        rpv = revenue / views if views else 0.0

        metric = {
            "launch_id": int(row["id"]),
            "product_no": pno,
            "start_at": start_at,
            "end_at": end_at,
            "analytics_views": views,
            "analytics_cart_count": cart_count,
            "analytics_cart_rate": cart_rate,
            "analytics_order_count": orders,
            "analytics_qty": qty,
            "analytics_revenue": revenue,

            # 레거시 컬럼은 비워 두되 공식값에는 절대 사용하지 않는다.
            "sera_views": None,
            "sera_orders": None,
            "sera_qty": None,
            "sera_revenue": None,
            "sera_opv": None,
            "sera_espv": None,
            "sera_click_value": None,

            "views": views,
            "cart_count": cart_count,
            "cart_rate": cart_rate,
            "order_count": orders,
            "qty": qty,
            "revenue": revenue,
            "cvr": cvr,
            "qty_cvr": qty_cvr,
            "rpv": rpv,
            "sellmate_stock_qty": None,
            "source_confidence": "Cafe24 Analytics",
            "collected_at": datetime.utcnow(),
        }

        score = postlaunch_score(metric, history)
        metric["hero_score"] = score
        metric["hero_grade"] = hero_grade(score)

        diagnosis = diagnose_with_why(
            {
                **metric,
                "return_rate": row.get("return_rate"),
                "hero_score": score,
            },
            history,
        )
        metric["diagnosis"] = diagnosis["diagnosis"]
        metric["why_text"] = diagnosis["why"]
        metric["recommended_action"] = diagnosis["recommended_action"]

        upsert_hero_metric_v2(metric)
        count += 1

    log_sync("상품 탐색 48H", "성공", f"{count}개")
    return count
