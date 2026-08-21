from __future__ import annotations
import pandas as pd


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, float(v)))


def prelaunch_score(
    focus=False,
    dna_score=None,
    margin_rate=None,
    season_score=None,
    reorder_score=None,
    content_score=None,
    md_score=None,
):
    dna = 50 if dna_score is None else clamp(dna_score)
    md = 50 if md_score is None else clamp(md_score)
    season = 50 if season_score is None else clamp(season_score)
    reorder = 50 if reorder_score is None else clamp(reorder_score)
    content = 50 if content_score is None else clamp(content_score)
    if margin_rate is None:
        margin = 50
    else:
        margin = clamp((float(margin_rate) - 20) / 30 * 100)
    score = (
        md * 0.25
        + dna * 0.20
        + margin * 0.15
        + season * 0.15
        + reorder * 0.10
        + content * 0.10
        + (100 if focus else 0) * 0.05
    )
    return round(clamp(score), 1)


def _percentile(series: pd.Series, value: float):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 5:
        return None
    return float((s <= value).mean() * 100)


def fallback_postlaunch_score(views, cvr, rpv, qty, revenue, cart_rate=0, click_signal=None):
    view_s = clamp(views / 2000 * 100)
    cvr_s = clamp(cvr / 0.04 * 100)
    rpv_s = clamp(rpv / 2000 * 100)
    cart_s = clamp(cart_rate / 0.08 * 100)
    qty_s = clamp(qty / 50 * 100)
    rev_s = clamp(revenue / 2_500_000 * 100)
    click_s = 50 if click_signal is None else clamp(float(click_signal))
    score = (
        cvr_s * 0.25
        + rpv_s * 0.20
        + cart_s * 0.15
        + qty_s * 0.15
        + rev_s * 0.10
        + view_s * 0.10
        + click_s * 0.05
    )
    return round(score, 1)


def postlaunch_score(row: dict, history: pd.DataFrame | None = None):
    views = float(row.get("views") or 0)
    cvr = float(row.get("cvr") or 0)
    rpv = float(row.get("rpv") or 0)
    cart_rate = float(row.get("cart_rate") or 0)
    qty = float(row.get("qty") or 0)
    revenue = float(row.get("revenue") or 0)
    click_signal = row.get("sera_click_value")

    required = ["cvr", "rpv", "qty", "revenue", "views"]
    if history is None or len(history) < 5 or any(c not in history.columns for c in required):
        return fallback_postlaunch_score(views, cvr, rpv, qty, revenue, cart_rate, click_signal)

    parts = {
        "cvr": (_percentile(history["cvr"], cvr), 0.25),
        "rpv": (_percentile(history["rpv"], rpv), 0.20),
        "qty": (_percentile(history["qty"], qty), 0.15),
        "revenue": (_percentile(history["revenue"], revenue), 0.10),
        "views": (_percentile(history["views"], views), 0.10),
    }
    if "cart_rate" in history.columns:
        parts["cart_rate"] = (_percentile(history["cart_rate"], cart_rate), 0.15)
    else:
        parts["cart_rate"] = (clamp(cart_rate / 0.08 * 100), 0.15)

    if click_signal is None:
        parts["click"] = (50.0, 0.05)
    elif "sera_click_value" in history.columns:
        pct = _percentile(history["sera_click_value"], float(click_signal))
        parts["click"] = ((50.0 if pct is None else pct), 0.05)
    else:
        parts["click"] = (clamp(float(click_signal)), 0.05)

    if any(v[0] is None for v in parts.values()):
        return fallback_postlaunch_score(views, cvr, rpv, qty, revenue, cart_rate, click_signal)
    return round(sum(pct * w for pct, w in parts.values()), 1)


def hero_grade(score: float):
    if score >= 85:
        return "🔥 HERO"
    if score >= 70:
        return "💎 HERO 유력"
    if score >= 55:
        return "관찰"
    return "재검토"


def diagnose(views, cvr, history: pd.DataFrame | None = None, cart_rate=0, stock_qty=None):
    if history is not None and len(history) >= 5:
        view_mid = float(pd.to_numeric(history["views"], errors="coerce").median())
        cvr_mid = float(pd.to_numeric(history["cvr"], errors="coerce").median())
    else:
        view_mid = 800
        cvr_mid = 0.02

    high_view = float(views or 0) >= view_mid
    high_cvr = float(cvr or 0) >= cvr_mid

    if high_view and high_cvr:
        result = "HERO"
    elif not high_view and high_cvr:
        result = "숨은 HERO(노출 확대)"
    elif high_view and not high_cvr:
        if float(cart_rate or 0) >= 0.05:
            result = "구매 직전 이탈(가격/배송/혜택 점검)"
        else:
            result = "전환 문제(상세/가격/핏 점검)"
    else:
        result = "저반응(우선순위 재검토)"

    if stock_qty is not None and stock_qty <= 0 and result in {"HERO", "숨은 HERO(노출 확대)"}:
        result += " · 재고 0(셀메이트 확인)"
    elif stock_qty is not None and stock_qty <= 10 and result == "HERO":
        result += " · 재고주의"
    return result
