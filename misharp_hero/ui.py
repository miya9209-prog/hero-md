from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import math
import tempfile

import pandas as pd
import streamlit as st

from misharp_hero.config import (
    DATABASE_URL,
    CAFE24_MALL_ID,
    CAFE24_CLIENT_ID,
    CAFE24_REDIRECT_URI,
    CAFE24_SCOPES,
    MISHARP_NEW_PRODUCT_URL,
    MISHARP_HOME_URL,
)
from misharp_hero.hero_score import diagnose_with_why
from misharp_hero.repository import (
    count_products,
    count_product_master,
    count_hero_watch,
    ended_followups,
    exploration_launches,
    get_product_md,
    history_summary,
    dna_history_dataset,
    judgment_launches,
    new_product_discovery_status,
    product_master_filter_values,
    product_master_page,
    save_judgment_workflow,
    save_product_md,
    sync_status_df,
    three_year_history_benchmark,
)
from misharp_hero.services.cafe24_admin import (
    Cafe24AdminClient,
    sync_products_full,
    sync_products_incremental,
)
from misharp_hero.services.cafe24_analytics import (
    Cafe24AnalyticsClient,
    sync_analytics_days,
)
from misharp_hero.services.cafe24_history import sync_history_month, sync_recent_categories
from misharp_hero.services.cafe24_returns import sync_return_metrics
from misharp_hero.services.md_excel_import import import_md_excel
from misharp_hero.services.new_product_discovery import discover_new_products
from misharp_hero.services.oauth import AdminOAuth, load_token
from misharp_hero.services.sync import sync_launch_metrics


KST = ZoneInfo("Asia/Seoul")


def html_escape(v):
    import html
    return html.escape(str(v or ""))


def _pct(v):
    try:
        return f"{float(v) * 100:.2f}%"
    except Exception:
        return "-"


def _money(v):
    try:
        return f"{float(v):,.0f}원"
    except Exception:
        return "-"


def _intfmt(v):
    try:
        return f"{int(float(v)):,}"
    except Exception:
        return "-"


def _return_rate(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    try:
        return f"{float(v) * 100:.2f}%"
    except Exception:
        return "-"


def _as_dt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        x = pd.to_datetime(v)
        if pd.isna(x):
            return None
        return x.to_pydatetime()
    except Exception:
        return None


def _yn_flag(v, true_label, false_label):
    raw = str(v or "").strip().upper()
    if raw in {"T", "TRUE", "Y", "YES", "1"}:
        return true_label
    if raw in {"F", "FALSE", "N", "NO", "0"}:
        return false_label
    return "-"


def _hours_elapsed(launch_at):
    dt = _as_dt(launch_at)
    if not dt:
        return 0.0
    now = datetime.now(KST).replace(tzinfo=None)
    return max(0.0, (now - dt).total_seconds() / 3600)


def _build_diagnosis_rows(data: pd.DataFrame):
    history = three_year_history_benchmark()
    rows = []
    for _, r in data.iterrows():
        payload = r.to_dict()
        result = diagnose_with_why(payload, history)
        payload["_diagnosis_live"] = result["diagnosis"]
        payload["_why_live"] = result["why"]
        payload["_action_live"] = result["recommended_action"]
        rows.append(payload)
    return pd.DataFrame(rows)


def page_explore():
    st.title("상품 탐색")
    st.caption(
        "미샵 신상페이지에 새롭게 등장한 상품을 출시로 판단하고, "
        "Cafe24 API로 상품정보와 판매·진열 상태를 확인한 뒤 자동 등록합니다. "
        "등록 후 48시간 동안 Cafe24 Analytics로 실제 판매반응을 관찰합니다."
    )

    status = new_product_discovery_status()
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("신상 현재상품", f"{int(status.get('current') or 0):,}개")
    s2.metric("이번 확인 신규등장", f"{int(status.get('added') or 0):,}개")
    s3.metric("이번 확인 페이지이탈", f"{int(status.get('removed') or 0):,}개")
    checked_at = status.get("captured_at")
    if checked_at:
        try:
            checked_text = pd.to_datetime(checked_at).strftime("%m-%d %H:%M")
        except Exception:
            checked_text = "-"
    else:
        checked_text = "-"
    s4.metric("마지막 신상 확인", checked_text)

    st.caption(
        "상품탐색 등록은 '신상페이지 신규등장 + Cafe24 판매/진열 확인'이 모두 충족된 상품만 자동 처리합니다."
    )

    data = exploration_launches()
    if data.empty:
        st.info(
            "현재 48시간 탐색 중인 신상품이 없습니다. "
            "자동탐색은 GitHub Actions에서 주기적으로 실행되며, 관리자 메뉴에서 즉시 실행할 수도 있습니다."
        )
        return

    data = _build_diagnosis_rows(data)
    data["경과시간"] = data["launch_at"].apply(lambda x: f"{_hours_elapsed(x):.1f}H")
    data["남은시간"] = data["close_48h_at"].apply(
        lambda x: f"{max(0, (_as_dt(x) - datetime.now(KST).replace(tzinfo=None)).total_seconds()/3600):.1f}H"
        if _as_dt(x) else "-"
    )
    data["구매전환율(CVR)"] = data["cvr"].apply(_pct)
    data["조회당 매출(RPV)"] = data["rpv"].apply(_money)
    data["장바구니율"] = data["cart_rate"].apply(_pct)
    data["히로 점수(HERO Score)"] = pd.to_numeric(data["hero_score"], errors="coerce").round(1)
    data["자동진단"] = data["_diagnosis_live"]
    data["추천"] = data["_action_live"]
    data["탐색경로"] = data["discovery_source"].fillna("수동 등록")
    data["신상감지시각"] = data["discovered_at"].apply(
        lambda x: _as_dt(x).strftime("%m-%d %H:%M") if _as_dt(x) else "-"
    )
    data["판매상태"] = data.apply(
        lambda r: (
            str(r.get("homepage_exit_status") or "").strip()
            if str(r.get("homepage_exit_status") or "").strip()
            else ("신상페이지 노출중" if r.get("homepage_last_seen_at") is not None else "확인중")
        ),
        axis=1,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("48시간 탐색중", f"{len(data):,}")
    m2.metric("HERO/HERO 유력", f"{int((pd.to_numeric(data['hero_score'], errors='coerce').fillna(0) >= 70).sum()):,}")
    m3.metric("숨은 HERO", f"{int((data['자동진단'] == '숨은 HERO').sum()):,}")
    m4.metric("전환 문제", f"{int((data['자동진단'] == '전환 문제').sum()):,}")

    cols = [
        "product_name", "신상감지시각", "판매상태", "경과시간", "남은시간",
        "views", "cart_count", "장바구니율", "order_count", "qty", "revenue",
        "구매전환율(CVR)", "조회당 매출(RPV)", "히로 점수(HERO Score)",
        "hero_grade", "자동진단", "추천", "탐색경로",
    ]
    cols = [c for c in cols if c in data.columns]
    st.dataframe(
        data[cols].rename(
            columns={
                "product_name": "상품명",
                "views": "상품조회수",
                "cart_count": "장바구니",
                "order_count": "판매건수",
                "qty": "판매수량",
                "revenue": "매출",
                "hero_grade": "상품등급",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("WHY · 왜 이렇게 진단했나요?")
    labels = {
        int(r["id"]): f"{r['product_name']} · {r['자동진단']}"
        for _, r in data.iterrows()
    }
    selected = st.selectbox(
        "상품 선택",
        list(labels.keys()),
        format_func=lambda x: labels[x],
        key="why_explore_select",
    )
    row = data[data["id"] == selected].iloc[0]
    st.markdown(
        f"""
        <div class="mso-why">
          <b>자동진단: {row['자동진단']}</b> · 추천: <b>{row['추천']}</b><br>
          WHY: {row['_why_live']}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "WHY는 현재 상품의 상품조회수·구매전환율(CVR)·조회당 매출(RPV)·판매량·매출을 "
        "최근 비교집단과 대조해 설명합니다. 공식 성과 데이터는 Cafe24 Analytics 하나만 사용합니다."
    )


def page_judgment_followup():
    st.title("상품 판정 및 후속업무 관리")
    st.caption(
        "상품 탐색에서 48시간이 끝난 상품이 자동으로 이동합니다. "
        "상품등급과 WHY를 확인하고 MD팀·제작팀 업무를 같은 화면에서 저장해 공유합니다."
    )

    c1, c2 = st.columns([1, 3])
    include_ended = c1.checkbox("관찰종료 포함", value=False)
    status_filter = c2.selectbox(
        "판정 필터",
        ["전체", "미정", "확대", "유지관찰", "보완", "중단", "관찰종료"],
    )

    data = judgment_launches(include_ended=include_ended)

    # 방어 필터:
    # repository의 close_48h_at 계산값과 무관하게 실제 launch_at 기준
    # 48시간이 지난 상품만 판정/후속업무 화면에 노출한다.
    # 상품 탐색(0~48H)과 판정(48H 이후)이 동시에 보이는 상황을 차단한다.
    if not data.empty and "launch_at" in data.columns:
        now_kst = datetime.now(KST).replace(tzinfo=None)
        launched = pd.to_datetime(data["launch_at"], errors="coerce")
        elapsed_hours = (pd.Timestamp(now_kst) - launched).dt.total_seconds() / 3600
        data = data[launched.notna() & (elapsed_hours >= 48.0)].copy()

    if data.empty:
        st.info("아직 48시간이 완료된 상품이 없습니다.")
        return

    if status_filter != "전체":
        if status_filter == "미정":
            data = data[data["md_followup"].fillna("") == ""].copy()
        else:
            data = data[data["md_followup"].fillna("") == status_filter].copy()
    if data.empty:
        st.info("선택한 조건에 해당하는 상품이 없습니다.")
        return

    data = _build_diagnosis_rows(data)
    data["반품률"] = data["return_rate"].apply(_return_rate)
    data["상품등급"] = data["hero_grade"].fillna("-")
    data["자동진단"] = data["_diagnosis_live"] + " → " + data["_action_live"]
    data["WHY"] = data["_why_live"]
    data["MD팀업무"] = data["md_team_work"].fillna("")
    data["제작팀업무"] = data["production_team_work"].fillna("")
    data["기타 메모"] = data["other_note"].fillna("")
    data["판정"] = data["md_followup"].fillna("미정")

    # 팀 협의안의 판정표 항목을 그대로 중심에 둔다.
    # 판정표에서는 팀이 바로 읽고 실행할 업무 내용을 우선한다.
    # WHY 전체 문장은 아래 선택 상품 상세영역에서 충분히 보여주므로
    # 상단 표에서는 제외해 MD/제작/기타 메모 폭을 확보한다.
    display_cols = [
        "product_name", "반품률", "상품등급", "자동진단",
        "판정", "MD팀업무", "제작팀업무", "기타 메모",
    ]
    display_df = data[display_cols].rename(columns={"product_name": "상품명"})
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=min(520, 42 + max(1, len(display_df)) * 42),
        column_config={
            "상품명": st.column_config.TextColumn("상품명", width="medium"),
            "반품률": st.column_config.TextColumn("반품률", width="small"),
            "상품등급": st.column_config.TextColumn("상품등급", width="small"),
            "자동진단": st.column_config.TextColumn("자동진단", width="medium"),
            "판정": st.column_config.TextColumn("판정", width="small"),
            "MD팀업무": st.column_config.TextColumn(
                "MD팀업무",
                width="large",
                help="MD팀이 저장한 후속 실행업무",
            ),
            "제작팀업무": st.column_config.TextColumn(
                "제작팀업무",
                width="large",
                help="제작팀이 저장한 후속 실행업무",
            ),
            "기타 메모": st.column_config.TextColumn(
                "기타 메모",
                width="large",
                help="여러 팀이 함께 보는 공용 메모",
            ),
        },
    )

    st.subheader("공유 후속업무 작성")
    label_map = {
        int(r["id"]): f"{r['product_name']} · {r['상품등급']} · 현재 판정: {r['판정']}"
        for _, r in data.iterrows()
    }
    launch_id = st.selectbox(
        "업무를 작성할 상품",
        list(label_map.keys()),
        format_func=lambda x: label_map[x],
    )
    chosen = data[data["id"] == launch_id].iloc[0]

    st.markdown(
        f"""
        <div class="mso-why">
          <b>WHY</b> · {chosen['_why_live']}<br>
          <b>자동진단</b> · {chosen['_diagnosis_live']} / 추천: {chosen['_action_live']}
        </div>
        """,
        unsafe_allow_html=True,
    )

    decisions = ["미정", "확대", "유지관찰", "보완", "중단", "관찰종료"]
    current = str(chosen.get("md_followup") or "미정")
    idx = decisions.index(current) if current in decisions else 0

    with st.form(f"shared_followup_{launch_id}"):
        decision = st.selectbox("상품 판정", decisions, index=idx)
        a, b = st.columns(2)
        md_work = a.text_area(
            "MD팀업무",
            value=str(chosen.get("md_team_work") or ""),
            placeholder="예: 메인 노출 확대 / 가격 검토 / 재주문 확인",
            height=150,
        )
        production_work = b.text_area(
            "제작팀업무",
            value=str(chosen.get("production_team_work") or ""),
            placeholder="예: 추가 생산 가능수량 확인 / 원단·납기 확인",
            height=150,
        )
        other_note = st.text_area(
            "기타 메모",
            value=str(chosen.get("other_note") or ""),
            placeholder="여러 팀이 함께 참고할 내용",
            height=120,
        )
        submitted = st.form_submit_button("판정 및 후속업무 저장", type="primary", use_container_width=True)
        if submitted:
            save_judgment_workflow(
                int(launch_id),
                decision,
                md_team_work=md_work,
                production_team_work=production_work,
                other_note=other_note,
            )
            st.success("상품 판정과 공유 후속업무를 저장했습니다.")
            st.rerun()

    with st.expander("48시간 상세 성과 보기", expanded=False):
        detail_cols = [
            "product_name", "views", "cart_count", "cart_rate",
            "order_count", "qty", "revenue", "cvr", "rpv", "return_rate", "hero_score",
        ]
        detail = data[detail_cols].copy()
        detail["cart_rate"] = detail["cart_rate"].apply(_pct)
        detail["cvr"] = detail["cvr"].apply(_pct)
        detail["rpv"] = detail["rpv"].apply(_money)
        detail["return_rate"] = detail["return_rate"].apply(_return_rate)
        detail["revenue"] = detail["revenue"].apply(_money)
        st.dataframe(
            detail.rename(
                columns={
                    "product_name": "상품명",
                    "views": "상품조회수",
                    "cart_count": "장바구니",
                    "cart_rate": "장바구니율",
                    "order_count": "판매건수",
                    "qty": "판매수량",
                    "revenue": "매출",
                    "cvr": "구매전환율(CVR)",
                    "rpv": "조회당 매출(RPV)",
                    "return_rate": "반품률",
                    "hero_score": "히로 점수(HERO Score)",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


def page_misharp_dna():
    """최근 3년 성과에서 시기별 잘 팔린 상품의 공통점을 뽑아 다음 신상 기획 가이드로 변환한다."""
    from collections import Counter
    import re

    st.title("미샵 DNA")
    st.caption(
        "최근 3년의 실제 판매성과에서 시기별 잘 팔린 상품의 공통점을 추출해 다음 신상품 기획에 참고할 가이드를 제안합니다. "
        "3년 이전 상품은 회사 상품DB에는 남지만 DNA 분석에는 사용하지 않습니다."
    )

    summary = history_summary()
    if summary.empty or int(summary.iloc[0].get("rows_count") or 0) == 0:
        st.info(
            "아직 미샵 DNA 학습데이터가 없습니다. 먼저 데이터·설정의 '최근 3년 비교데이터'에서 지난달 시험수집을 실행하거나 "
            "GitHub Actions의 36개월 히스토리 backfill을 실행해주세요."
        )
        return

    srow = summary.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("학습 상품", f"{int(srow.get('product_count') or 0):,}개")
    c2.metric("월별 성과행", f"{int(srow.get('rows_count') or 0):,}개")
    c3.metric("데이터 시작", str(srow.get("first_month") or "-"))
    c4.metric("최근 데이터", str(srow.get("last_month") or "-"))

    st.subheader("1. 분석할 시기와 성공 기준")
    a, b = st.columns([1, 1.4])
    period_label = a.selectbox(
        "분석 기간",
        ["최근 3개월", "최근 6개월", "최근 12개월", "최근 24개월", "최근 36개월"],
        index=2,
        help="패션 트렌드 변화를 반영하기 위해 최대 최근 3년까지만 봅니다.",
    )
    months = {"최근 3개월": 3, "최근 6개월": 6, "최근 12개월": 12, "최근 24개월": 24, "최근 36개월": 36}[period_label]
    metric_label = b.selectbox(
        "잘 팔린 상품 기준",
        ["매출", "판매수량", "구매전환율(CVR)", "조회당 매출(RPV)"],
        index=0,
        help="한 가지 지표만 절대기준으로 쓰지 않고, 선택한 지표 상위상품에서 공통 특성을 찾습니다.",
    )
    metric_col = {"매출": "revenue", "판매수량": "qty", "구매전환율(CVR)": "cvr", "조회당 매출(RPV)": "rpv"}[metric_label]

    data = dna_history_dataset(months)
    if data.empty:
        st.warning("선택한 기간에 분석 가능한 최근 3년 성과데이터가 없습니다.")
        return

    # 최소한의 유효 반응이 있는 상품만 비교한다.
    eligible = data[(data["views"] > 0) | (data["qty"] > 0) | (data["revenue"] > 0)].copy()
    if eligible.empty:
        st.warning("선택 기간에 유효한 상품성과가 없습니다.")
        return

    top_n = min(30, max(10, int(round(len(eligible) * 0.20))))
    winners = eligible.sort_values([metric_col, "revenue", "qty"], ascending=False).head(top_n).copy()

    def price_band(v):
        try:
            x = float(v or 0)
        except Exception:
            x = 0
        if x <= 0: return "가격정보 없음"
        if x < 30000: return "3만원 미만"
        if x < 40000: return "3만원대"
        if x < 50000: return "4만원대"
        if x < 70000: return "5~6만원대"
        if x < 100000: return "7~9만원대"
        return "10만원 이상"

    winners["가격대"] = winners["selling_price"].apply(price_band)
    cats = [str(x).strip() for x in winners.get("category", pd.Series(dtype=str)).tolist() if str(x).strip() and str(x).lower() not in {"none", "nan", "미분류"}]
    top_categories = Counter(cats).most_common(5)
    top_price = Counter(winners["가격대"].tolist()).most_common(4)

    stopwords = {
        "color","colors","컬러","미샵","기획","단독","세일","특가","free","size","사이즈",
        "티셔츠","블라우스","팬츠","원피스","니트","셔츠","자켓","재킷","스커트","가디건",
        "반팔","긴팔","여성","데일리","the","and","with"
    }
    tokens = []
    for name in winners["product_name"].fillna("").astype(str):
        for t in re.findall(r"[가-힣A-Za-z0-9]+", name):
            k = t.strip().lower()
            if len(k) >= 2 and k not in stopwords and not k.isdigit():
                tokens.append(k)
    top_keywords = Counter(tokens).most_common(8)

    st.subheader("2. 이 시기 잘 팔린 상품의 공통점")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("상위 분석상품", f"{len(winners):,}개")
    m2.metric("상위상품 평균 구매전환율(CVR)", _pct(winners["cvr"].mean()))
    m3.metric("상위상품 평균 조회당 매출(RPV)", _money(winners["rpv"].mean()))
    m4.metric("상위상품 평균 판매가", _money(winners.loc[winners["selling_price"] > 0, "selling_price"].mean() if (winners["selling_price"] > 0).any() else 0))

    g1, g2, g3 = st.columns(3)
    with g1:
        st.markdown("**강한 카테고리**")
        if top_categories:
            for name, cnt in top_categories:
                st.write(f"• {name} · {cnt}개")
        else:
            st.write("카테고리 데이터 보강 필요")
    with g2:
        st.markdown("**반응 좋은 가격대**")
        for name, cnt in top_price:
            st.write(f"• {name} · {cnt}개")
    with g3:
        st.markdown("**상품명에서 반복되는 핵심어**")
        if top_keywords:
            st.write(" · ".join([f"{k}({v})" for k, v in top_keywords]))
        else:
            st.write("반복 키워드가 충분하지 않습니다.")

    st.subheader("3. 다음 신상 기획 가이드")
    cat_text = top_categories[0][0] if top_categories else "상위 반응 카테고리"
    price_text = top_price[0][0] if top_price else "상위 반응 가격대"
    kw_text = ", ".join([k for k, _ in top_keywords[:4]]) if top_keywords else "상품명·핏·소재 키워드"
    median_cvr = float(winners["cvr"].median() or 0)
    median_rpv = float(winners["rpv"].median() or 0)
    median_views = float(winners["views"].median() or 0)

    st.markdown(
        f"""
        <div class="mso-why">
        <b>미샵 DNA 제안</b><br>
        • <b>우선 검토 영역:</b> {html_escape(cat_text)} 계열과 <b>{html_escape(price_text)}</b> 가격대를 다음 신상 후보군에서 우선 비교해보세요.<br>
        • <b>반복 신호:</b> 상위상품에서 <b>{html_escape(kw_text)}</b> 같은 표현이 반복됩니다. 실제 기획에서는 단어 자체보다 그 단어가 가리키는 핏·소재·착용상황을 확인하세요.<br>
        • <b>출시 후 초기 기대선:</b> 상위상품 중앙값 기준 상품조회수 약 <b>{median_views:,.0f}</b>, 구매전환율(CVR) <b>{median_cvr*100:.2f}%</b>, 조회당 매출(RPV) <b>{median_rpv:,.0f}원</b>입니다.<br>
        • <b>활용 원칙:</b> 이 가이드는 '이 디자인을 그대로 만들라'는 답이 아니라, MD가 다음 신상을 고를 때 <b>무엇을 먼저 확인할지 알려주는 데이터 근거</b>입니다. 현재 트렌드·고객반응·현장 MD 판단과 함께 사용하세요.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("4. 근거가 된 상위상품")
    show = winners[["product_name", "category", "selling_price", "views", "cart_count", "qty", "revenue", "cvr", "rpv"]].copy()
    show["판매가"] = show["selling_price"].apply(_money)
    show["구매전환율(CVR)"] = show["cvr"].apply(_pct)
    show["조회당 매출(RPV)"] = show["rpv"].apply(_money)
    show["매출"] = show["revenue"].apply(_money)
    show = show.rename(columns={"product_name":"상품명", "category":"카테고리", "views":"상품조회수", "cart_count":"장바구니", "qty":"판매수량"})
    st.dataframe(
        show[["상품명", "카테고리", "판매가", "상품조회수", "장바구니", "판매수량", "매출", "구매전환율(CVR)", "조회당 매출(RPV)"]],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("미샵 DNA를 어떻게 해석하나요?"):
        st.markdown(
            """
            - **최근 3년만 사용**: 오래된 유행이 현재 기획에 과도하게 영향을 주지 않도록 합니다.
            - **기간을 바꿔 비교**: 최근 3개월은 현재 트렌드, 12개월은 계절을 포함한 안정적 패턴, 36개월은 반복되는 미샵 고객 DNA를 보는 데 유리합니다.
            - **매출만 보지 않기**: 매출·판매수량·구매전환율(CVR)·조회당 매출(RPV)을 각각 바꿔보면 '많이 노출된 상품'과 '상품력이 강한 상품'을 구분할 수 있습니다.
            - **공통점은 가설**: 자동 추출된 공통점은 다음 상품 기획의 질문을 만드는 자료입니다. 최종 상품선정은 현재 트렌드, 원가, 공급조건, 고객 VOC와 함께 판단합니다.
            """
        )

def page_product_db():
    st.title("상품DB")
    st.caption("Cafe24 전체 상품DB와 운영정보를 한 곳에서 확인·관리합니다.")

    today = datetime.now(KST).date()
    filter_values = product_master_filter_values()

    f1, f2, f3, f4 = st.columns([2.3, 1, 1, 1])
    search = f1.text_input("상품 검색", placeholder="상품명 / 상품코드 / 상품번호")
    selling_label = f2.selectbox("판매상태", ["전체", "판매중", "판매중지"])
    display_label = f3.selectbox("진열상태", ["전체", "진열", "미진열"])
    watch_label = f4.selectbox("상품 탐색", ["전체", "탐색 ON", "탐색 OFF"])

    f5, f6, f7, f8 = st.columns([1.5, 1.2, 1.2, .8])
    category = f5.selectbox("카테고리", ["전체"] + filter_values.get("categories", []))
    season = f6.selectbox("시즌", ["전체"] + filter_values.get("seasons", []))
    sourcing = f7.selectbox("제작/사입", ["전체"] + filter_values.get("sourcing_types", []))
    page_size = f8.selectbox("표시수", [50, 100, 200], index=1)

    filters = {
        "search": search,
        "selling": {"전체": None, "판매중": "T", "판매중지": "F"}[selling_label],
        "display": {"전체": None, "진열": "T", "미진열": "F"}[display_label],
        "hero_watch": {"전체": None, "탐색 ON": True, "탐색 OFF": False}[watch_label],
        "category": None if category == "전체" else category,
        "season": None if season == "전체" else season,
        "sourcing_type": None if sourcing == "전체" else sourcing,
    }

    total = count_products()
    filtered_total = count_product_master(filters)
    watch_total = count_hero_watch()
    page_count = max(1, math.ceil(filtered_total / int(page_size)))
    if "product_db_page" not in st.session_state:
        st.session_state["product_db_page"] = 1
    st.session_state["product_db_page"] = min(st.session_state["product_db_page"], page_count)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("전체 상품DB", f"{total:,}")
    m2.metric("현재 조건", f"{filtered_total:,}")
    m3.metric("상품 탐색 ON", f"{watch_total:,}")
    m4.metric("페이지", f"{st.session_state['product_db_page']} / {page_count}")

    b1, b2, _ = st.columns([1, 1, 4])
    if b1.button("◀ 이전", disabled=st.session_state["product_db_page"] <= 1, use_container_width=True):
        st.session_state["product_db_page"] -= 1
        st.rerun()
    if b2.button("다음 ▶", disabled=st.session_state["product_db_page"] >= page_count, use_container_width=True):
        st.session_state["product_db_page"] += 1
        st.rerun()

    data = product_master_page(
        (today - timedelta(days=6)).isoformat(),
        today.isoformat(),
        filters=filters,
        page=int(st.session_state["product_db_page"]),
        page_size=int(page_size),
    )
    if data.empty:
        st.info("조건에 맞는 상품이 없습니다.")
        return

    data["판매상태"] = data["selling"].apply(lambda v: _yn_flag(v, "판매중", "판매중지"))
    data["진열상태"] = data["display"].apply(lambda v: _yn_flag(v, "진열", "미진열"))
    data["상품 탐색"] = data["hero_watch"].apply(lambda v: "ON" if bool(v) else "OFF")
    data["판매가"] = data["selling_price"].apply(_money)
    if "auto_discovered" not in data.columns:
        data["auto_discovered"] = False
    if "discovery_source" not in data.columns:
        data["discovery_source"] = None

    master_cols = [
        "product_no", "product_code", "product_name", "판매가", "판매상태", "진열상태",
        "category", "상품 탐색", "launch_at", "auto_discovered", "discovery_source",
        "season", "sourcing_type", "md_owner",
    ]
    master_cols = [c for c in master_cols if c in data.columns]
    st.dataframe(
        data[master_cols].rename(
            columns={
                "product_no": "상품번호",
                "product_code": "상품코드",
                "product_name": "상품명",
                "category": "카테고리",
                "launch_at": "탐색 시작시각",
                "auto_discovered": "자동탐색",
                "discovery_source": "탐색경로",
                "season": "시즌",
                "sourcing_type": "제작/사입",
                "md_owner": "MD 담당",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.subheader("상품 운영정보 수정")
    choices = data[["product_no", "product_name"]].fillna("").to_dict("records")
    labels = {str(x["product_no"]): f"{x['product_no']} · {x['product_name']}" for x in choices}
    selected_no = st.selectbox(
        "수정할 상품",
        list(labels.keys()),
        format_func=lambda x: labels[x],
    )

    md = get_product_md(selected_no)
    selected_row = data[data["product_no"].astype(str) == str(selected_no)].iloc[0]
    now = datetime.now(KST).replace(tzinfo=None)
    launch_dt = _as_dt(md.get("launch_at")) or _as_dt(selected_row.get("launch_at")) or now
    sale_end_dt = _as_dt(md.get("sale_end_at"))

    season_options = ["", "봄", "여름", "간절기", "가을", "겨울", "사계절", "기타"]
    existing_season = str(md.get("season") or "")
    if existing_season and existing_season not in season_options:
        season_options.insert(1, existing_season)

    source_options = ["", "미샵제작", "사입", "기타"]
    existing_source = str(md.get("sourcing_type") or "")
    if existing_source and existing_source not in source_options:
        source_options.insert(1, existing_source)

    with st.form(f"product_db_edit_{selected_no}"):
        a1, a2, a3 = st.columns(3)
        watch = a1.checkbox("상품 탐색 ON", value=bool(md.get("hero_watch", False)))
        season_value = a2.selectbox(
            "시즌", season_options,
            index=season_options.index(existing_season) if existing_season in season_options else 0,
        )
        source_value = a3.selectbox(
            "제작/사입", source_options,
            index=source_options.index(existing_source) if existing_source in source_options else 0,
        )

        b1, b2, b3 = st.columns([1, 1, 1.2])
        launch_date = b1.date_input("실제 노출일", launch_dt.date())
        launch_time = b2.time_input("실제 노출시각", launch_dt.time().replace(microsecond=0))
        owner = b3.text_input("MD 담당", value=str(md.get("md_owner") or ""))

        c1, c2 = st.columns([1, 2])
        has_end = c1.checkbox("판매종료일 사용", value=bool(sale_end_dt))
        end_date = c1.date_input(
            "판매종료일",
            sale_end_dt.date() if sale_end_dt else today,
            disabled=not has_end,
        )
        note = c2.text_area("관리자 메모", value=str(md.get("md_note") or ""), height=95)

        submitted = st.form_submit_button("운영정보 저장", type="primary", use_container_width=True)
        if submitted:
            launch_at = datetime.combine(launch_date, launch_time)
            sale_end_at = (
                datetime.combine(end_date, datetime.max.time()).replace(microsecond=0)
                if has_end else None
            )
            save_product_md(
                selected_no,
                {
                    "hero_watch": watch,
                    "launch_at": launch_at,
                    "sale_end_at": sale_end_at,
                    "season": season_value or None,
                    "sourcing_type": source_value or None,
                    "md_owner": owner.strip() or None,
                    "md_note": note.strip() or None,
                },
            )
            if watch:
                try:
                    with st.spinner("첫 판매반응 데이터를 즉시 불러오는 중..."):
                        sync_launch_metrics(product_no=selected_no)
                except Exception as e:
                    st.warning(f"운영정보는 저장됐지만 첫 데이터 수집은 다음 자동수집 때 재시도됩니다. ({e})")
            st.success("저장했습니다.")
            st.rerun()


def page_data_settings():
    st.title("데이터·설정")
    st.caption("Cafe24 연결, 자동 신상품 탐색, 48시간 데이터 수집 상태를 관리합니다.")

    c1, c2, c3 = st.columns(3)
    c1.metric("DB", "연결" if DATABASE_URL else "미설정")
    c2.metric("Cafe24 Mall", CAFE24_MALL_ID or "미설정")
    c3.metric("Cafe24 토큰", "저장됨" if load_token("admin") else "없음")

    st.subheader("1. Cafe24 OAuth")
    st.caption("권장 Scope: mall.read_product mall.read_order mall.read_analytics")
    st.code(CAFE24_SCOPES, language=None)
    if CAFE24_MALL_ID and CAFE24_CLIENT_ID and CAFE24_REDIRECT_URI:
        st.link_button("Cafe24 권한 승인 열기", AdminOAuth().authorize_url())
        code = st.text_input("승인 후 code 붙여넣기", type="password")
        if st.button("Cafe24 토큰 저장") and code:
            try:
                AdminOAuth().exchange_code(code)
                st.success("Cafe24 토큰을 암호화 저장했습니다.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    st.divider()
    st.subheader("2. 자동 신상품 탐색")
    st.caption(
        "Cafe24 API가 주 기준이며 홈페이지 크롤링은 실제 노출 교차확인용입니다. "
        "기본 운영은 30분 주기로 탐색해 48시간 시작 오차를 줄입니다."
    )
    st.write(f"홈페이지: `{MISHARP_NEW_PRODUCT_URL or MISHARP_HOME_URL}`")
    if st.button("신상품 탐색 지금 실행", type="primary"):
        try:
            with st.spinner("신상품을 확인하고 상품 탐색에 자동 등록하는 중..."):
                result = discover_new_products()
                # 방금 자동등록된 상품의 첫 Analytics도 바로 수집
                sync_launch_metrics()
            st.success(
                f"후보 {result['candidates']:,}개 · 신규등록 {result['registered']:,}개 · "
                f"홈페이지 확인 {result['homepage_seen']:,}개"
            )
            if result.get("homepage_error"):
                st.warning("홈페이지 크롤링은 실패했지만 Cafe24 API 자동탐색은 정상 처리됐습니다.")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("3. 연결 테스트")
    t1, t2 = st.columns(2)
    if t1.button("Cafe24 상품 API 테스트"):
        try:
            result = Cafe24AdminClient().get("/products", {"limit": 1})
            st.success(f"상품 API 정상 · {len(result.get('products', []))}건 응답")
        except Exception as e:
            st.error(str(e))
    if t2.button("Cafe24 Analytics 테스트"):
        try:
            end_at = datetime.now(KST).replace(tzinfo=None)
            start_at = end_at - timedelta(hours=24)
            rows = Cafe24AnalyticsClient().product_views(start_at, end_at)
            st.success(f"Analytics 정상 · 상품조회 지표 {len(rows):,}건")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("4. 수동 동기화")
    a, b, c = st.columns(3)
    if a.button("Cafe24 상품 전체"):
        try:
            with st.spinner("상품 전체 동기화 중..."):
                count = sync_products_full()
            st.success(f"상품 {count:,}개 동기화")
        except Exception as e:
            st.error(str(e))
    if b.button("Cafe24 최근 상품"):
        try:
            count = sync_products_incremental(72)
            st.success(f"최근 상품 {count:,}개 동기화")
        except Exception as e:
            st.error(str(e))
    if c.button("Analytics 최근 2일"):
        try:
            count = sync_analytics_days(2)
            st.success(f"Analytics {count:,}개 상품-일 저장")
        except Exception as e:
            st.error(str(e))

    d, e = st.columns(2)
    if d.button("48시간 상품 데이터 갱신", use_container_width=True):
        try:
            count = sync_launch_metrics()
            st.success(f"48시간 데이터 {count:,}개 갱신")
        except Exception as e:
            st.error(str(e))
    if e.button("반품률 갱신", use_container_width=True):
        try:
            count = sync_return_metrics()
            st.success(f"반품률 {count:,}개 갱신")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("5. 최근 3년 비교데이터")
    st.caption(
        "전체 20년 상품DB는 보존하지만 WHY/예측 비교에는 최근 3년만 사용합니다. "
        "36개월 전체 backfill은 GitHub Actions의 별도 수동 workflow로 실행하도록 분리했습니다."
    )
    summary = history_summary()
    if not summary.empty:
        r = summary.iloc[0]
        st.write(
            f"현재 학습데이터: {int(r.get('product_count') or 0):,}개 상품 / "
            f"{int(r.get('rows_count') or 0):,}행 / "
            f"{r.get('first_month') or '-'} ~ {r.get('last_month') or '-'}"
        )
    today = datetime.now(KST)
    prev = today.replace(day=1) - timedelta(days=1)
    h1, h2 = st.columns(2)
    if h1.button(f"지난달({prev:%Y-%m}) 1개월 시험수집", use_container_width=True):
        try:
            count = sync_history_month(prev.year, prev.month, years_back=3)
            st.success(f"{prev:%Y-%m} · {count:,}개 상품 학습데이터 + 실제 카테고리 저장")
        except Exception as e:
            st.error(str(e))
    if h2.button("최근 90일 카테고리 갱신", use_container_width=True):
        try:
            result = sync_recent_categories(90)
            st.success(
                f"카테고리 {result['rows']:,}행 저장 · {result['products']:,}개 상품 확인 · "
                f"상품DB {result['updated']:,}개 반영"
            )
        except Exception as e:
            st.error(str(e))
    st.caption(
        "카테고리는 상품명으로 추정하지 않습니다. Cafe24 Analytics의 실제 상품×카테고리 성과를 저장하고, "
        "복수 카테고리는 매출→판매수량→판매건수→장바구니 순으로 대표 카테고리를 정합니다."
    )

    st.divider()
    st.subheader("6. 기존 MD 엑셀 이관")
    f = st.file_uploader("미샵 핵심업무 실행서식", type=["xlsx", "xlsm"])
    if f and st.button("MD 엑셀 가져오기"):
        suffix = Path(f.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(f.getbuffer())
            path = tmp.name
        result = import_md_excel(path)
        st.success(f"완료: {result}")

    st.divider()
    st.subheader("최근 자동수집 로그")
    logs = sync_status_df(40)
    if logs.empty:
        st.info("동기화 로그가 없습니다.")
    else:
        st.dataframe(logs, use_container_width=True, hide_index=True)

    st.info(
        "공식 판정 데이터는 Cafe24 Analytics 하나만 사용합니다. "
        "반품률은 48시간 이후 품질판단에만 사용하며 히로 점수(HERO Score)에는 넣지 않습니다."
    )


def page_guide():
    st.title("HERO ITEM OS 이용방법")
    st.caption("이 페이지는 MD팀과 제작팀이 프로그램의 목적과 일일 사용법을 동일하게 이해하기 위한 운영 매뉴얼입니다.")

    st.markdown(
        """
        ### 1. 이 프로그램의 목적
        HERO ITEM OS는 **모든 신상품을 똑같이 밀지 않기 위해** 만든 상품 의사결정 시스템입니다.
        신상품을 자동으로 발견하고, 출시 후 48시간의 실제 반응을 확인한 뒤,
        **더 밀 상품 / 보완할 상품 / 중단할 상품**을 빠르게 결정하고 후속업무를 공유합니다.

        ### 2. 전체 흐름
        **신상품 자동 탐색 → 48시간 관찰 → 상품 판정 → MD/제작 후속업무 → 미샵 DNA → 다음 신상 기획**

        <div class="mso-guide-step">
        <b>① 상품 탐색</b><br>
        Cafe24 API를 기준으로 최근 등록·판매중·진열중인 신상품을 자동으로 찾습니다.
        홈페이지 크롤링은 실제 노출 여부를 교차확인하는 보조 수단입니다.
        자동 발견된 상품은 별도 등록 없이 48시간 관찰을 시작합니다.
        </div>

        <div class="mso-guide-step">
        <b>② 첫 48시간</b><br>
        상품조회수, 장바구니, 판매건수, 판매수량, 매출,
        구매전환율(CVR), 조회당 매출(RPV)을 Cafe24 Analytics에서 자동 수집합니다.
        신규 등록 직후 첫 데이터가 바로 들어오고 이후 30분 단위로 갱신됩니다.
        </div>

        <div class="mso-guide-step">
        <b>③ 상품 판정 및 후속업무 관리</b><br>
        48시간이 끝나면 상품은 자동으로 이 메뉴로 이동합니다.
        상품등급, 자동진단, WHY, 반품률을 보고
        <b>확대 / 유지관찰 / 보완 / 중단 / 관찰종료</b> 중 하나를 결정합니다.
        </div>

        <div class="mso-guide-step">
        <b>④ MD팀업무 / 제작팀업무 / 기타 메모</b><br>
        한 사람이 개인 메모를 남기는 기능이 아니라,
        여러 직원이 같은 상품의 후속업무를 공유하는 공간입니다.
        MD팀은 노출·가격·재주문·판매전략을,
        제작팀은 추가생산·원단·납기 등을 기록합니다.
        </div>

        <div class="mso-guide-step">
        <b>⑤ WHY 읽는 법</b><br>
        자동진단은 결과만 보여주지 않습니다.
        상품조회수, 구매전환율(CVR), 조회당 매출(RPV), 판매량, 매출이
        비교집단에서 어느 수준인지 설명하고 왜 확대/보완/재검토를 추천하는지 함께 보여줍니다.
        20년 전체 상품DB는 보존하되 비교·예측에는 최근 3년 데이터를 우선 사용합니다.
        </div>

        <div class="mso-guide-step">
        <b>⑥ 반품률</b><br>
        반품률은 첫 48시간에 판매된 수량 중 이후 실제 반품완료된 비율입니다.
        초기 48시간 히로 점수에는 넣지 않고,
        '잘 팔렸지만 실제 만족도가 낮은 상품'을 걸러내는 사후 품질지표로 사용합니다.
        </div>

        ### 3. MD팀 일일 사용 루틴
        **출근 후:** 상품 탐색에서 새 상품과 반응 이상상품 확인  
        **48시간 완료 상품:** 상품 판정 및 후속업무 관리에서 판정 + MD/제작 업무 저장  
        **판단 완료:** 관찰종료 처리. 기록은 삭제되지 않고 DB에 남음

        ### 4. 지표 뜻
        - **구매전환율(CVR)**: 상품을 본 고객 중 실제 주문으로 이어진 비율
        - **조회당 매출(RPV)**: 상품조회 1회가 평균적으로 만들어낸 매출
        - **히로 점수(HERO Score)**: CVR 30 / RPV 25 / 판매수량 20 / 매출 15 / 상품조회수 10의 종합점수
        - **반품률**: 첫 48시간 판매분 중 이후 반품완료된 수량 비율

        ### 5. 미샵 DNA
        최근 3년 성과데이터에서 시기별 잘 팔린 상품의 공통점을 찾습니다.
        카테고리, 가격대, 상품명 핵심 키워드, 구매전환율(CVR), 조회당 매출(RPV), 판매수량의 공통 패턴을 바탕으로
        다음 신상품 기획에 참고할 수 있는 가이드를 제안합니다. 오래된 유행의 영향을 줄이기 위해 3년 이전 데이터는 DNA 분석에서 제외합니다.

        ### 6. 상품DB·데이터 설정
        비밀번호 잠금 없이 팀에서 함께 사용합니다.
        잘못 잡힌 노출시각 수정, 수동 상품 등록/해제, Cafe24 인증, 수집상태 확인은 이 메뉴에서 처리합니다.

        ### 7. 데이터 원칙
        **공식 판매반응 데이터는 Cafe24 Analytics 하나만 사용합니다.**
        SERA와 Sellmate 데이터는 HERO 판정에 혼합하지 않습니다.
        """,
        unsafe_allow_html=True,
    )
