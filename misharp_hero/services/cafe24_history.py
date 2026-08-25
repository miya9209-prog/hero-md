from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from misharp_hero.repository import (
    log_sync,
    recent_registered_product_nos,
    upsert_history_monthly,
    upsert_category_monthly,
    apply_representative_categories,
)
from misharp_hero.services.cafe24_analytics import Cafe24AnalyticsClient


KST = ZoneInfo("Asia/Seoul")
# Cafe24 Analytics 일부 endpoint는 긴 date 범위를 거부한다.
# 안전하게 최대 7일씩 잘라 호출한 뒤 월/기간 단위로 다시 합산한다.
MAX_QUERY_DAYS = 7


def _shift_month(year: int, month: int, delta: int):
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def month_window(year: int, month: int):
    last_day = monthrange(year, month)[1]
    start_at = datetime(year, month, 1, 0, 0, 0)
    end_at = datetime(year, month, last_day, 23, 59, 59)
    return start_at, end_at


def _chunk_windows(start_at: datetime, end_at: datetime, days: int = MAX_QUERY_DAYS):
    """start_at~end_at을 최대 N일(달력일 기준) 구간으로 분할한다."""
    cursor = start_at
    while cursor <= end_at:
        chunk_end = min(
            end_at,
            (cursor + timedelta(days=max(1, int(days)) - 1)).replace(hour=23, minute=59, second=59),
        )
        yield cursor, chunk_end
        cursor = (chunk_end + timedelta(seconds=1)).replace(hour=0, minute=0, second=0)


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


def _merged_metrics_chunked(client: Cafe24AnalyticsClient, start_at: datetime, end_at: datetime):
    """여러 7일 구간의 상품 성과를 product_no 기준으로 합산한다."""
    merged = {}
    for chunk_start, chunk_end in _chunk_windows(start_at, end_at):
        for r in client.merged_product_metrics(chunk_start, chunk_end):
            product_no = str(r.get("product_no") or "").strip()
            if not product_no:
                continue
            x = merged.setdefault(
                product_no,
                {
                    "product_no": product_no,
                    "product_name": "",
                    "views": 0,
                    "cart_count": 0,
                    "order_count": 0,
                    "qty": 0,
                    "revenue": 0.0,
                },
            )
            x["product_name"] = r.get("product_name") or x["product_name"]
            x["views"] += _int(r.get("views"))
            x["cart_count"] += _int(r.get("cart_count"))
            x["order_count"] += _int(r.get("order_count"))
            x["qty"] += _int(r.get("qty"))
            x["revenue"] += _float(r.get("revenue"))

    result = []
    for x in merged.values():
        x["cart_rate"] = (x["cart_count"] / x["views"]) if x["views"] else 0.0
        result.append(x)
    return result


def _categorydetails_chunked(client: Cafe24AnalyticsClient, start_at: datetime, end_at: datetime):
    """여러 7일 구간의 카테고리 성과를 product_no+category_no 기준으로 합산한다."""
    merged = {}
    for chunk_start, chunk_end in _chunk_windows(start_at, end_at):
        for r in client.product_categorydetails(chunk_start, chunk_end):
            product_no = str(r.get("product_no") or "").strip()
            category_no = str(r.get("category_no") or "").strip()
            if not product_no or not category_no:
                continue
            key = (product_no, category_no)
            x = merged.setdefault(
                key,
                {
                    "product_no": product_no,
                    "product_name": "",
                    "product_code": "",
                    "category_no": category_no,
                    "category_name": "",
                    "sales_count_per_category": 0,
                    "sales_item_per_category": 0,
                    "sales_price_per_category": 0.0,
                    "carts_count_per_category": 0,
                },
            )
            x["product_name"] = r.get("product_name") or x["product_name"]
            x["product_code"] = r.get("product_code") or x["product_code"]
            x["category_name"] = r.get("category_name") or x["category_name"]
            x["sales_count_per_category"] += _int(r.get("sales_count_per_category"))
            x["sales_item_per_category"] += _int(r.get("sales_item_per_category"))
            x["sales_price_per_category"] += _float(r.get("sales_price_per_category"))
            x["carts_count_per_category"] += _int(r.get("carts_count_per_category"))
    return list(merged.values())


def sync_category_month(year: int, month: int, years_back: int = 3):
    """월별 실제 Cafe24 Analytics 카테고리 성과를 저장하고 대표 카테고리를 상품DB에 반영한다."""
    start_at, end_at = month_window(int(year), int(month))
    now_kst = datetime.now(KST).replace(tzinfo=None)
    cutoff = now_kst - timedelta(days=365 * int(years_back) + 1)
    allowed = recent_registered_product_nos(cutoff)
    client = Cafe24AnalyticsClient()
    rows = _categorydetails_chunked(client, start_at, end_at)

    period_month = f"{int(year):04d}-{int(month):02d}"
    collected_at = datetime.utcnow()
    payload = []
    touched = set()
    for r in rows:
        product_no = str(r.get("product_no") or "").strip()
        category_no = str(r.get("category_no") or "").strip()
        category_name = str(r.get("category_name") or "").strip()
        if not product_no or product_no not in allowed or not category_no or not category_name:
            continue
        touched.add(product_no)
        payload.append(
            {
                "period_month": period_month,
                "product_no": product_no,
                "product_name": r.get("product_name") or "",
                "product_code": r.get("product_code") or "",
                "category_no": category_no,
                "category_name": category_name,
                "sales_count": _int(r.get("sales_count_per_category")),
                "qty": _int(r.get("sales_item_per_category")),
                "revenue": _float(r.get("sales_price_per_category")),
                "cart_count": _int(r.get("carts_count_per_category")),
                "collected_at": collected_at,
            }
        )

    saved = upsert_category_monthly(payload)
    updated = apply_representative_categories(sorted(touched)) if touched else 0
    log_sync("Cafe24 카테고리", "성공", f"{period_month} · {saved}행 / 상품DB {updated}개 반영")
    return {"rows": saved, "products": len(touched), "updated": updated}


def sync_history_month(year: int, month: int, years_back: int = 3):
    """월별 Analytics 성과를 최대 7일씩 나눠 수집하고 최근 N년 상품만 저장한다."""
    start_at, end_at = month_window(int(year), int(month))
    now_kst = datetime.now(KST).replace(tzinfo=None)
    cutoff = now_kst - timedelta(days=365 * int(years_back) + 1)

    allowed = recent_registered_product_nos(cutoff)
    client = Cafe24AnalyticsClient()
    rows = _merged_metrics_chunked(client, start_at, end_at)

    period_month = f"{int(year):04d}-{int(month):02d}"
    collected_at = datetime.utcnow()
    payload = []
    for r in rows:
        product_no = str(r.get("product_no") or "").strip()
        if not product_no or product_no not in allowed:
            continue
        views = _int(r.get("views"))
        order_count = _int(r.get("order_count"))
        revenue = _float(r.get("revenue"))
        cart_count = _int(r.get("cart_count"))
        payload.append(
            {
                "period_month": period_month,
                "product_no": product_no,
                "product_name": r.get("product_name") or "",
                "views": views,
                "cart_count": cart_count,
                "cart_rate": (cart_count / views) if views else 0.0,
                "order_count": order_count,
                "qty": _int(r.get("qty")),
                "revenue": revenue,
                "cvr": (order_count / views) if views else 0.0,
                "rpv": (revenue / views) if views else 0.0,
                "collected_at": collected_at,
            }
        )

    count = upsert_history_monthly(payload)
    category_result = sync_category_month(year, month, years_back=years_back)
    log_sync(
        "HERO 3년 학습데이터",
        "성공",
        f"{period_month} · {count}개 상품 / 카테고리 {category_result['rows']}행",
    )
    return count


def sync_completed_months(months: int = 36, years_back: int = 3):
    """현재 월을 제외한 완료월을 최근→과거 순서로 수집한다.

    Cafe24 Analytics는 계정/리소스별로 과거 조회 가능 범위 밖의 날짜에
    "date 범위를 초과하였습니다."(400)를 반환할 수 있다.
    최근 월부터 역순으로 수집해 가능한 데이터는 먼저 모두 보존하고,
    과거 한계에 도달하면 정상 종료한다.
    """
    today = datetime.now(KST)
    targets = []
    for n in range(1, int(months) + 1):
        y, m = _shift_month(today.year, today.month, -n)
        targets.append((y, m))

    total = 0
    details = []
    stopped_at = None
    stop_reason = None

    for y, m in targets:
        period = f"{y:04d}-{m:02d}"
        try:
            count = sync_history_month(y, m, years_back=years_back)
        except RuntimeError as exc:
            message = str(exc)
            if "date 범위를 초과" in message or "400 BAD_REQUEST" in message:
                stopped_at = period
                stop_reason = "Cafe24 Analytics 과거 조회 가능 범위 도달"
                log_sync(
                    "HERO 3년 학습데이터",
                    "부분완료",
                    f"{period}부터 과거 데이터 조회 불가 · 최근 {len(details)}개월 저장 완료",
                )
                break
            raise

        total += count
        details.append((period, count))

    return {
        "requested_months": int(months),
        "collected_months": len(details),
        "rows": total,
        "earliest_collected": details[-1][0] if details else None,
        "stopped_at": stopped_at,
        "stop_reason": stop_reason,
        "details": details,
    }


def sync_recent_categories(days: int = 90, years_back: int = 3):
    """최근 N일 카테고리 실적을 7일씩 나눠 현재 월 스냅샷으로 갱신한다."""
    now = datetime.now(KST)
    start_at = (now - timedelta(days=max(1, int(days)))).replace(tzinfo=None)
    end_at = now.replace(tzinfo=None)
    cutoff = now.replace(tzinfo=None) - timedelta(days=365 * int(years_back) + 1)
    allowed = recent_registered_product_nos(cutoff)
    rows = _categorydetails_chunked(Cafe24AnalyticsClient(), start_at, end_at)

    period_month = now.strftime("%Y-%m")
    collected_at = datetime.utcnow()
    payload, touched = [], set()
    for r in rows:
        product_no = str(r.get("product_no") or "").strip()
        category_no = str(r.get("category_no") or "").strip()
        category_name = str(r.get("category_name") or "").strip()
        if not product_no or product_no not in allowed or not category_no or not category_name:
            continue
        touched.add(product_no)
        payload.append({
            "period_month": period_month,
            "product_no": product_no,
            "product_name": r.get("product_name") or "",
            "product_code": r.get("product_code") or "",
            "category_no": category_no,
            "category_name": category_name,
            "sales_count": _int(r.get("sales_count_per_category")),
            "qty": _int(r.get("sales_item_per_category")),
            "revenue": _float(r.get("sales_price_per_category")),
            "cart_count": _int(r.get("carts_count_per_category")),
            "collected_at": collected_at,
        })

    saved = upsert_category_monthly(payload)
    updated = apply_representative_categories(sorted(touched)) if touched else 0
    log_sync("Cafe24 카테고리", "성공", f"최근 {days}일 · {saved}행 / 상품DB {updated}개 반영")
    return {"rows": saved, "products": len(touched), "updated": updated}
