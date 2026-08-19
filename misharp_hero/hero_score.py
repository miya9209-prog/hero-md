from __future__ import annotations
import math
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
    """출시 전 설명 가능한 MVP 점수."""
    dna = 50 if dna_score is None else clamp(dna_score)
    md = 50 if md_score is None else clamp(md_score)
    season = 50 if season_score is None else clamp(season_score)
    reorder = 50 if reorder_score is None else clamp(reorder_score)
    content = 50 if content_score is None else clamp(content_score)

    # margin_rate는 0~100% 입력을 가정. 20~50%를 0~100으로 선형화.
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

def fallback_postlaunch_score(views, cvr, rpv, qty, revenue):
    # 데이터가 아직 적을 때 사용하는 임시 기준. 이후 히스토리 백분위로 자동 전환.
    view_s = clamp(views / 2000 * 100)
    cvr_s = clamp(cvr / 0.04 * 100)
    rpv_s = clamp(rpv / 2000 * 100)
    qty_s = clamp(qty / 50 * 100)
    rev_s = clamp(revenue / 2_500_000 * 100)
    score = cvr_s*0.30 + rpv_s*0.25 + qty_s*0.20 + rev_s*0.15 + view_s*0.10
    return round(score, 1)

def postlaunch_score(row: dict, history: pd.DataFrame | None = None):
    views = float(row.get("views") or 0)
    cvr = float(row.get("cvr") or 0)
    rpv = float(row.get("rpv") or 0)
    qty = float(row.get("qty") or 0)
    revenue = float(row.get("revenue") or 0)

    if history is None or len(history) < 5:
        return fallback_postlaunch_score(views, cvr, rpv, qty, revenue)

    parts = {
        "cvr": (_percentile(history["cvr"], cvr), 0.30),
        "rpv": (_percentile(history["rpv"], rpv), 0.25),
        "qty": (_percentile(history["qty"], qty), 0.20),
        "revenue": (_percentile(history["revenue"], revenue), 0.15),
        "views": (_percentile(history["views"], views), 0.10),
    }
    if any(v[0] is None for v in parts.values()):
        return fallback_postlaunch_score(views, cvr, rpv, qty, revenue)
    return round(sum(pct * w for pct, w in parts.values()), 1)

def hero_grade(score: float):
    if score >= 85:
        return "🔥 HERO"
    if score >= 70:
        return "💎 HERO 유력"
    if score >= 55:
        return "관찰"
    return "재검토"

def diagnose(views, cvr, history: pd.DataFrame | None = None):
    if history is not None and len(history) >= 5:
        view_mid = float(pd.to_numeric(history["views"], errors="coerce").median())
        cvr_mid = float(pd.to_numeric(history["cvr"], errors="coerce").median())
    else:
        view_mid = 800
        cvr_mid = 0.02

    high_view = float(views or 0) >= view_mid
    high_cvr = float(cvr or 0) >= cvr_mid

    if high_view and high_cvr:
        return "HERO"
    if not high_view and high_cvr:
        return "숨은 HERO(노출 확대)"
    if high_view and not high_cvr:
        return "전환 문제(상세/가격/핏 점검)"
    return "저반응(우선순위 재검토)"
