from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from misharp_hero.repository import (
    log_sync,
    recent_registered_product_nos,
    upsert_history_monthly,
)
from misharp_hero.services.cafe24_analytics import Cafe24AnalyticsClient


KST = ZoneInfo("Asia/Seoul")


def _shift_month(year: int, month: int, delta: int):
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def month_window(year: int, month: int):
    last_day = monthrange(year, month)[1]
    start_at = datetime(year, month, 1, 0, 0, 0)
    end_at = datetime(year, month, last_day, 23, 59, 59)
    return start_at, end_at


def sync_history_month(year: int, month: int, years_back: int = 3):
    """월별 Analytics 성과를 수집하되, 등록일 기준 최근 N년 상품만 저장한다."""
    start_at, end_at = month_window(int(year), int(month))
    now_kst = datetime.now(KST).replace(tzinfo=None)
    cutoff = now_kst - timedelta(days=365 * int(years_back) + 1)

    allowed = recent_registered_product_nos(cutoff)
    client = Cafe24AnalyticsClient()
    rows = client.merged_product_metrics(start_at, end_at)

    period_month = f"{int(year):04d}-{int(month):02d}"
    collected_at = datetime.utcnow()
    payload = []
    for r in rows:
        product_no = str(r.get("product_no") or "").strip()
        if not product_no or product_no not in allowed:
            continue
        views = int(r.get("views") or 0)
        order_count = int(r.get("order_count") or 0)
        revenue = float(r.get("revenue") or 0)
        payload.append(
            {
                "period_month": period_month,
                "product_no": product_no,
                "product_name": r.get("product_name") or "",
                "views": views,
                "cart_count": int(r.get("cart_count") or 0),
                "cart_rate": float(r.get("cart_rate") or 0),
                "order_count": order_count,
                "qty": int(r.get("qty") or 0),
                "revenue": revenue,
                "cvr": (order_count / views) if views else 0.0,
                "rpv": (revenue / views) if views else 0.0,
                "collected_at": collected_at,
            }
        )

    count = upsert_history_monthly(payload)
    log_sync("HERO 3년 학습데이터", "성공", f"{period_month} · {count}개 상품")
    return count


def sync_completed_months(months: int = 36, years_back: int = 3):
    """현재 월을 제외한 최근 완료월을 과거→최근 순서로 수집한다."""
    today = datetime.now(KST)
    targets = []
    for n in range(int(months), 0, -1):
        y, m = _shift_month(today.year, today.month, -n)
        targets.append((y, m))

    total = 0
    details = []
    for y, m in targets:
        count = sync_history_month(y, m, years_back=years_back)
        total += count
        details.append((f"{y:04d}-{m:02d}", count))
    return {"months": len(targets), "rows": total, "details": details}
