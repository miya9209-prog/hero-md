from __future__ import annotations
from datetime import datetime
import pandas as pd
from misharp_hero.services.cafe24_analytics import Cafe24AnalyticsClient, merge_product_metric
from misharp_hero.repository import current_launches, metrics_history, upsert_metric48h, log_sync
from misharp_hero.hero_score import postlaunch_score, hero_grade, diagnose

def sync_launch_metrics(include_future_close=False):
    launches = current_launches()
    if launches.empty:
        return 0

    history = metrics_history()
    client = Cafe24AnalyticsClient()
    now = datetime.now()
    count = 0

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

        views_rows = client.product_view(start_at, end_at)
        sales_rows = client.product_sales(start_at, end_at)
        metric = merge_product_metric(product_no, views_rows, sales_rows)
        score = postlaunch_score(metric, history)
        metric.update({
            "launch_id": int(row["id"]),
            "product_no": product_no,
            "start_at": start_at,
            "end_at": end_at,
            "hero_score": score,
            "hero_grade": hero_grade(score),
            "diagnosis": diagnose(metric["views"], metric["cvr"], history),
            "collected_at": datetime.utcnow(),
        })
        upsert_metric48h(metric)
        count += 1

    log_sync("Cafe24 Analytics 48H", "성공", f"{count}개")
    return count
