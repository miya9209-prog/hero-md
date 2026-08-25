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
    """레거시 사전평가 호환. v3.0의 핵심은 출시 후 실제 데이터 기반 판정이다."""
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


def _series(history: pd.DataFrame | None, col: str):
    if history is None or col not in history.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(history[col], errors="coerce").replace([math.inf, -math.inf], pd.NA).dropna()


def _percentile(history: pd.DataFrame | None, col: str, value: float):
    s = _series(history, col)
    if len(s) < 5:
        return None
    return float((s <= float(value or 0)).mean() * 100)


def fallback_postlaunch_score(views, cvr, rpv, qty, revenue):
    """비교집단이 부족할 때만 쓰는 절대기준.

    공식 가중치:
    구매전환율(CVR) 30 / 조회당 매출(RPV) 25 / 판매수량 20 / 매출 15 / 상품조회수 10.
    """
    view_s = clamp(float(views or 0) / 2000 * 100)
    cvr_s = clamp(float(cvr or 0) / 0.04 * 100)
    rpv_s = clamp(float(rpv or 0) / 2000 * 100)
    qty_s = clamp(float(qty or 0) / 50 * 100)
    rev_s = clamp(float(revenue or 0) / 2_500_000 * 100)
    score = (
        cvr_s * 0.30
        + rpv_s * 0.25
        + qty_s * 0.20
        + rev_s * 0.15
        + view_s * 0.10
    )
    return round(score, 1)


def postlaunch_score(row: dict, history: pd.DataFrame | None = None):
    views = float(row.get("views") or 0)
    cvr = float(row.get("cvr") or 0)
    rpv = float(row.get("rpv") or 0)
    qty = float(row.get("qty") or 0)
    revenue = float(row.get("revenue") or 0)

    required = ["cvr", "rpv", "qty", "revenue", "views"]
    if history is None or len(history) < 5 or any(c not in history.columns for c in required):
        return fallback_postlaunch_score(views, cvr, rpv, qty, revenue)

    parts = {
        "cvr": (_percentile(history, "cvr", cvr), 0.30),
        "rpv": (_percentile(history, "rpv", rpv), 0.25),
        "qty": (_percentile(history, "qty", qty), 0.20),
        "revenue": (_percentile(history, "revenue", revenue), 0.15),
        "views": (_percentile(history, "views", views), 0.10),
    }
    if any(v[0] is None for v in parts.values()):
        return fallback_postlaunch_score(views, cvr, rpv, qty, revenue)
    return round(sum(pct * w for pct, w in parts.values()), 1)


def hero_grade(score: float):
    score = float(score or 0)
    if score >= 85:
        return "🔥 HERO"
    if score >= 70:
        return "💎 HERO 유력"
    if score >= 55:
        return "관찰"
    return "재검토"


def _pct_ko(v):
    return f"{float(v or 0) * 100:.1f}%"


def _money_ko(v):
    return f"{float(v or 0):,.0f}원"


def _rank_phrase(pct):
    if pct is None:
        return None
    top = max(1, int(round(100 - pct)))
    if top <= 10:
        return f"상위 {top}%"
    if top <= 25:
        return f"상위 {top}%"
    if pct < 40:
        return "하위권"
    return "중간권"


def diagnose_with_why(row: dict, history: pd.DataFrame | None = None):
    """자동진단 + WHY + 권장행동.

    사용 데이터는 Cafe24 Analytics와 반품률뿐이다.
    SERA/Sellmate를 판정값에 혼합하지 않는다.
    """
    views = float(row.get("views") or 0)
    cart_rate = float(row.get("cart_rate") or 0)
    cvr = float(row.get("cvr") or 0)
    rpv = float(row.get("rpv") or 0)
    qty = float(row.get("qty") or 0)
    revenue = float(row.get("revenue") or 0)
    score = float(row.get("hero_score") or 0)
    return_rate = row.get("return_rate")
    try:
        return_rate = None if pd.isna(return_rate) else float(return_rate)
    except Exception:
        return_rate = None

    p_view = _percentile(history, "views", views)
    p_cvr = _percentile(history, "cvr", cvr)
    p_rpv = _percentile(history, "rpv", rpv)
    p_qty = _percentile(history, "qty", qty)
    p_rev = _percentile(history, "revenue", revenue)

    if history is not None and len(history) >= 5:
        view_mid = float(_series(history, "views").median() or 0)
        cvr_mid = float(_series(history, "cvr").median() or 0)
        rpv_mid = float(_series(history, "rpv").median() or 0)
    else:
        view_mid, cvr_mid, rpv_mid = 800.0, 0.02, 1000.0

    high_view = views >= view_mid
    high_cvr = cvr >= cvr_mid
    high_rpv = rpv >= rpv_mid

    if score >= 85:
        diagnosis = "HERO"
        action = "확대 검토"
    elif (not high_view) and high_cvr and high_rpv:
        diagnosis = "숨은 HERO"
        action = "노출 확대 후 재평가"
    elif high_view and not high_cvr:
        diagnosis = "전환 문제"
        action = "상세·가격·핏·혜택 점검"
    elif score >= 70:
        diagnosis = "HERO 유력"
        action = "집중관찰"
    elif score >= 55:
        diagnosis = "관찰"
        action = "추가 데이터 확인"
    else:
        diagnosis = "저반응"
        action = "우선순위 재검토"

    # 48H 이후 반품률은 품질 경고로 WHY에 반영하되 HERO Score 자체는 변경하지 않는다.
    return_warning = None
    if return_rate is not None:
        if return_rate >= 0.10:
            return_warning = "반품률 10% 이상"
            action = "확대 전 반품사유 확인"
        elif return_rate >= 0.07:
            return_warning = "반품률 주의"
            if action == "확대 검토":
                action = "반품사유 확인 후 확대"

    reasons = []
    if p_cvr is not None:
        reasons.append(f"구매전환율(CVR) {_pct_ko(cvr)} · {_rank_phrase(p_cvr)}")
    else:
        reasons.append(f"구매전환율(CVR) {_pct_ko(cvr)}")
    if p_rpv is not None:
        reasons.append(f"조회당 매출(RPV) {_money_ko(rpv)} · {_rank_phrase(p_rpv)}")
    else:
        reasons.append(f"조회당 매출(RPV) {_money_ko(rpv)}")
    if p_view is not None:
        reasons.append(f"상품조회수 {int(views):,}회 · {_rank_phrase(p_view)}")
    else:
        reasons.append(f"상품조회수 {int(views):,}회")

    # 판매가 발생한 경우 판매량/매출의 WHY를 한 줄 더 추가.
    extra = []
    if qty > 0:
        rank = _rank_phrase(p_qty)
        extra.append(f"판매수량 {int(qty):,}개" + (f" · {rank}" if rank else ""))
    if revenue > 0:
        rank = _rank_phrase(p_rev)
        extra.append(f"매출 {_money_ko(revenue)}" + (f" · {rank}" if rank else ""))
    if return_rate is not None:
        extra.append(f"반품률 {_pct_ko(return_rate)}")
    if return_warning:
        extra.append(return_warning)

    selected_extra = extra[:2]
    if return_rate is not None and not any("반품률" in x for x in selected_extra):
        selected_extra.append(f"반품률 {_pct_ko(return_rate)}")
    if return_warning and return_warning not in selected_extra:
        selected_extra.append(return_warning)

    why = " / ".join(reasons + selected_extra)
    return {
        "diagnosis": diagnosis,
        "why": why,
        "recommended_action": action,
    }


def diagnose(views, cvr, history: pd.DataFrame | None = None, cart_rate=0, stock_qty=None):
    """v2 호환용 간단 진단."""
    if history is not None and len(history) >= 5:
        view_s = _series(history, "views")
        cvr_s = _series(history, "cvr")
        view_mid = float(view_s.median()) if len(view_s) else 800.0
        cvr_mid = float(cvr_s.median()) if len(cvr_s) else 0.02
    else:
        view_mid, cvr_mid = 800.0, 0.02

    high_view = float(views or 0) >= view_mid
    high_cvr = float(cvr or 0) >= cvr_mid
    if high_view and high_cvr:
        return "HERO"
    if not high_view and high_cvr:
        return "숨은 HERO(노출 확대)"
    if high_view and not high_cvr:
        if float(cart_rate or 0) >= 0.05:
            return "구매 직전 이탈(가격/배송/혜택 점검)"
        return "전환 문제(상세/가격/핏 점검)"
    return "저반응(우선순위 재검토)"
