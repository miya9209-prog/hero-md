from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
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
)
from misharp_hero.hero_score import prelaunch_score
from misharp_hero.repository import (
    action_df,
    candidate_df,
    count_products,
    count_product_master,
    count_hero_watch,
    current_launches,
    get_product_md,
    monthly_hero_df,
    product_master_filter_values,
    product_master_page,
    save_product_md,
    save_post48h_followup,
    ended_followups,
    sync_status_df,
    df,
)
from misharp_hero.services.cafe24_admin import Cafe24AdminClient, sync_products_full, sync_products_incremental
from misharp_hero.services.cafe24_analytics import Cafe24AnalyticsClient, sync_analytics_days
from misharp_hero.services.md_excel_import import import_md_excel
from misharp_hero.services.oauth import AdminOAuth, load_token
from misharp_hero.services.sync import sync_launch_metrics
from misharp_hero.services.cafe24_returns import sync_return_metrics


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
    """반품 데이터 연동 전에는 '-'를 표시하고, 향후 return_rate 컬럼이 생기면 자동 사용."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    try:
        return f"{float(v) * 100:.2f}%"
    except Exception:
        return "-"


def _page_caption(text: str):
    st.caption(text)


def _hero_os_guide():
    with st.expander("HERO ITEM OS 이용방법 · 처음 사용하는 MD는 꼭 읽어주세요", expanded=False):
        st.markdown(
            """
            <div class="mso-guide-intro">
            HERO ITEM OS는 신상품을 등록한 뒤 초기 48시간의 실제 반응을 추적하고,
            이후에도 반품률과 판매 품질을 보면서 <b>더 밀 상품 / 보완할 상품 / 종료할 상품</b>을 결정하기 위한 MD 의사결정 도구입니다.
            </div>
            <div class="mso-guide-step"><b>1. 신상품 등록</b><br>상품 마스터에서 상품을 검색한 뒤 시즌, 제작/사입, 실제 출시일시를 입력하고 <b>HERO 관찰 ON</b>으로 저장합니다.</div>
            <div class="mso-guide-step"><b>2. 48시간 자동관찰</b><br>Cafe24 Analytics 기준 상품조회수, 장바구니, 판매건수, 판매수량, 매출, 구매전환율(CVR), 조회당 매출(RPV)을 추적합니다.</div>
            <div class="mso-guide-step"><b>3. 48시간 판정</b><br>히로 점수(HERO Score)와 자동진단을 참고해 확대, 유지관찰, 보완, 중단 여부를 판단합니다.</div>
            <div class="mso-guide-step"><b>4. 48시간 이후 사후관찰</b><br>48시간이 끝난 상품은 하단의 <b>MD 사후관리</b>에서 확대 / 유지관찰 / 보완 / 중단 중 하나를 선택합니다. <b>반품률</b>은 최초 48시간 판매수량 중 이후 실제 반품완료된 수량의 비율로, 초기 판매의 품질을 확인하는 지표입니다.</div>
            <div class="mso-guide-step"><b>5. 관찰 종료</b><br>판단이 끝난 상품은 <b>관찰종료</b>를 선택합니다. 히로 레이더에서는 숨겨지지만 상품, 48시간 성과, MD 판단 이력은 DB에 그대로 보관됩니다.</div>
            <div class="mso-guide-step"><b>지표 읽는 법</b><br><b>구매전환율(CVR)</b>은 상품을 본 고객 중 주문으로 이어진 비율, <b>조회당 매출(RPV)</b>은 상품조회 1회가 평균적으로 만든 매출입니다. <b>히로 점수(HERO Score)</b>는 조회·전환·판매·매출을 종합한 100점 기준의 반응 점수입니다.</div>
            """,
            unsafe_allow_html=True,
        )


def _yn_flag(v, true_label, false_label):
    raw = str(v or "").strip().upper()
    if raw in {"T", "TRUE", "Y", "YES", "1"}:
        return true_label
    if raw in {"F", "FALSE", "N", "NO", "0"}:
        return false_label
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


def _watch_status(row, now):
    if not bool(row.get("hero_watch")):
        return "-"
    start = _as_dt(row.get("launch_at"))
    close = _as_dt(row.get("close_48h_at"))
    if not start:
        return "출시시각 필요"
    if start > now:
        return "대기"
    if close and now <= close:
        hours = max(0, (close - now).total_seconds() / 3600)
        return f"진행중 · {hours:.1f}H 남음"
    return "48H 완료"


def page_radar():
    st.title("히로 레이더")
    st.caption("신상품의 초기 판매반응을 분석해 더 밀어야 할 상품과 보완해야 할 상품을 알려드립니다. · 공식 데이터: Cafe24 Analytics")
    launches = current_launches(only_observed=True)
    actions = action_df()

    if launches.empty:
        st.info("아직 출시상품 데이터가 없습니다. 상품 스케줄 또는 기존 MD 엑셀을 먼저 등록하세요.")
        return

    now = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None)
    launch_dt = pd.to_datetime(launches["launch_at"])
    close_dt = pd.to_datetime(launches["close_48h_at"])
    active = launches[(launch_dt <= now) & (close_dt >= now)]
    hero = active[active["hero_score"].fillna(0) >= 85]
    hidden = active[active["diagnosis"].fillna("").str.contains("숨은", na=False)]
    conversion = active[active["diagnosis"].fillna("").str.contains("전환|이탈", na=False)]
    open_actions = actions[actions["status"] != "완료"] if not actions.empty else actions

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("48시간 관찰중", len(active))
    c2.metric("히로(HERO)", len(hero))
    c3.metric("숨은 히로(HERO)", len(hidden))
    c4.metric("전환 문제", len(conversion))
    c5.metric("미완료 실행", len(open_actions))

    show = launches.copy()
    show["경과(H)"] = ((now - pd.to_datetime(show["launch_at"])).dt.total_seconds() / 3600).clip(lower=0).round(1)
    show["48H 상태"] = show.apply(lambda r: _watch_status(r, now.to_pydatetime()), axis=1)
    show["구매전환율(CVR)"] = show["cvr"].apply(_pct)
    show["장바구니율"] = show["cart_rate"].apply(_pct)
    show["조회당 매출(RPV)"] = show["rpv"].apply(_money)
    show["반품률"] = show["return_rate"].apply(_return_rate) if "return_rate" in show.columns else "-"
    show["MD 사후판단"] = show["md_followup"].fillna("-") if "md_followup" in show.columns else "-"

    cols = [
        "product_name",
        "경과(H)",
        "48H 상태",
        "views",
        "cart_count",
        "장바구니율",
        "order_count",
        "qty",
        "revenue",
        "구매전환율(CVR)",
        "조회당 매출(RPV)",
        "반품률",
        "hero_score",
        "hero_grade",
        "MD 사후판단",
        "diagnosis",
    ]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(
        show[cols].rename(
            columns={
                "product_name": "상품명",
                "48H 상태": "48시간 상태",
                "views": "상품조회수",
                "cart_count": "장바구니",
                "order_count": "판매건수",
                "qty": "판매수량",
                "revenue": "매출",
                "hero_score": "히로 점수(HERO Score)",
                "hero_grade": "히로 등급",
                "diagnosis": "자동진단",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown('<div style="height:1.0rem"></div>', unsafe_allow_html=True)

    completed = show[pd.to_datetime(show["close_48h_at"]) < now].copy()
    with st.expander("48시간 이후 MD 사후관리 · 계속 밀지, 보완할지, 종료할지 결정", expanded=False):
        if completed.empty:
            st.info("아직 48시간이 완료된 관찰상품이 없습니다.")
        else:
            completed = completed.sort_values("close_48h_at", ascending=False)
            follow_labels = {
                int(r["id"]): f"{r['product_name']} · 현재 판단: {r.get('md_followup') or '미정'}"
                for _, r in completed.iterrows()
            }
            launch_id = st.selectbox(
                "판단할 상품",
                list(follow_labels.keys()),
                format_func=lambda x: follow_labels.get(x, str(x)),
                key="post48h_launch",
            )
            chosen = completed[completed["id"].astype(int) == int(launch_id)].iloc[0]
            current_decision = str(chosen.get("md_followup") or "").strip()
            decisions = ["확대", "유지관찰", "보완", "중단", "관찰종료"]
            default_idx = decisions.index(current_decision) if current_decision in decisions else 1

            st.caption(
                "확대: 집중판매 · 유지관찰: 더 지켜봄 · 보완: 상세/가격/콘텐츠 수정 · "
                "중단: 추가 노출 우선순위 제외 · 관찰종료: 레이더에서 숨김(기록은 보존)"
            )
            with st.form(f"post48h_form_{launch_id}"):
                decision = st.selectbox("MD 판단", decisions, index=default_idx)
                note = st.text_area(
                    "판단 메모",
                    value=str(chosen.get("md_followup_note") or ""),
                    placeholder="예: 전환은 좋지만 반품률 확인 후 광고 확대 예정",
                    height=90,
                )
                saved = st.form_submit_button("사후판단 저장", type="primary", use_container_width=True)
                if saved:
                    save_post48h_followup(int(launch_id), decision, note)
                    if decision == "관찰종료":
                        st.success("관찰종료 처리했습니다. 레이더에서는 숨겨지고 과거 데이터와 판단 이력은 보존됩니다.")
                    else:
                        st.success(f"MD 판단을 '{decision}'로 저장했습니다.")
                    st.rerun()

    ended = ended_followups(20)
    if not ended.empty:
        with st.expander("관찰 종료 이력 · 최근 20건", expanded=False):
            st.dataframe(
                ended[[c for c in ["product_name", "close_48h_at", "md_followup", "md_followup_note", "md_owner"] if c in ended.columns]].rename(
                    columns={
                        "product_name": "상품명",
                        "close_48h_at": "48시간 마감",
                        "md_followup": "최종 판단",
                        "md_followup_note": "판단 메모",
                        "md_owner": "MD 담당",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.caption("다시 관찰하려면 상품 마스터에서 해당 상품의 HERO 관찰을 ON으로 저장하세요.")

    _hero_os_guide()


def page_product_master():
    st.title("상품 마스터")
    st.caption("Cafe24 상품정보와 MD 운영정보를 분리 관리하고, 관찰상품을 48시간 판정으로 자동 연결합니다.")

    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    filter_values = product_master_filter_values()

    # 기간 성과 범위
    d1, d2 = st.columns(2)
    start_date = d1.date_input("통계 시작일", today - timedelta(days=6), key="pm_start")
    end_date = d2.date_input("통계 종료일", today, key="pm_end")

    # 1차 필터
    f1, f2, f3, f4 = st.columns([2.2, 1, 1, 1])
    search = f1.text_input("상품 검색", placeholder="상품명 / 상품코드 / 상품번호", key="pm_search")
    selling_label = f2.selectbox("판매상태", ["전체", "판매중", "판매중지"], key="pm_selling")
    display_label = f3.selectbox("진열상태", ["전체", "진열", "미진열"], key="pm_display")
    watch_label = f4.selectbox("HERO 관찰", ["전체", "관찰 ON", "관찰 OFF"], key="pm_watch")

    # 2차 필터
    f5, f6, f7, f8 = st.columns([1.5, 1.2, 1.2, 0.8])
    category = f5.selectbox("카테고리", ["전체"] + filter_values.get("categories", []), key="pm_category")
    season = f6.selectbox("시즌", ["전체"] + filter_values.get("seasons", []), key="pm_season")
    sourcing = f7.selectbox("제작/사입", ["전체"] + filter_values.get("sourcing_types", []), key="pm_sourcing")
    page_size = f8.selectbox("표시수", [50, 100, 200], index=1, key="pm_page_size")

    filters = {
        "search": search,
        "selling": {"전체": None, "판매중": "T", "판매중지": "F"}[selling_label],
        "display": {"전체": None, "진열": "T", "미진열": "F"}[display_label],
        "hero_watch": {"전체": None, "관찰 ON": True, "관찰 OFF": False}[watch_label],
        "category": None if category == "전체" else category,
        "season": None if season == "전체" else season,
        "sourcing_type": None if sourcing == "전체" else sourcing,
    }

    total = count_products()
    filtered_total = count_product_master(filters)
    watch_total = count_hero_watch()
    page_count = max(1, math.ceil(filtered_total / int(page_size)))
    if st.session_state.get("pm_page", 1) > page_count:
        st.session_state["pm_page"] = page_count
    if "pm_page" not in st.session_state:
        st.session_state["pm_page"] = 1

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cafe24 전체 상품", f"{total:,}")
    m2.metric("현재 조건", f"{filtered_total:,}")
    m3.metric("HERO 관찰 ON", f"{watch_total:,}")
    m4.metric("페이지", f"{st.session_state['pm_page']} / {page_count}")

    p1, p2, p3 = st.columns([1, 1, 4])
    if p1.button("◀ 이전", disabled=st.session_state["pm_page"] <= 1, use_container_width=True):
        st.session_state["pm_page"] -= 1
        st.rerun()
    if p2.button("다음 ▶", disabled=st.session_state["pm_page"] >= page_count, use_container_width=True):
        st.session_state["pm_page"] += 1
        st.rerun()
    page = int(st.session_state["pm_page"])

    data = product_master_page(
        start_date.isoformat(),
        end_date.isoformat(),
        filters=filters,
        page=page,
        page_size=int(page_size),
    )
    if data.empty:
        st.info("조건에 맞는 상품이 없습니다.")
        return

    # 없는 지표 컬럼 기본값
    for c in ["views", "cart_count", "order_count", "qty", "revenue", "sellmate_stock_qty"]:
        if c not in data.columns:
            data[c] = 0
    for c in ["cvr", "cart_rate", "rpv"]:
        if c not in data.columns:
            data[c] = 0.0

    now = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
    data["판매상태"] = data["selling"].apply(lambda v: _yn_flag(v, "판매중", "판매중지"))
    data["진열상태"] = data["display"].apply(lambda v: _yn_flag(v, "진열", "미진열"))
    data["HERO 관찰"] = data["hero_watch"].apply(lambda v: "ON" if bool(v) else "OFF")
    data["48H 상태"] = data.apply(lambda r: _watch_status(r, now), axis=1)
    data["판매가"] = data["selling_price"].apply(_money)
    data["소비자가"] = data["retail_price"].apply(_money) if "retail_price" in data else "-"
    data["반품률"] = data["return_rate"].apply(_return_rate) if "return_rate" in data.columns else "-"
    data["구매전환율(CVR)"] = data["cvr"].apply(_pct)
    data["장바구니율"] = data["cart_rate"].apply(_pct)
    data["조회당 매출(RPV)"] = data["rpv"].apply(_money)

    tab1, tab2 = st.tabs(["운영 마스터", "기간 성과"])
    with tab1:
        master_cols = [
            "product_no", "product_code", "product_name", "판매가", "소비자가",
            "판매상태", "진열상태", "category", "sourcing_type", "season",
            "HERO 관찰", "launch_at", "48H 상태", "hero_score", "hero_grade",
            "반품률", "md_owner",
        ]
        master_cols = [c for c in master_cols if c in data.columns]
        st.dataframe(
            data[master_cols].rename(columns={
                "product_no": "상품번호",
                "product_code": "상품코드",
                "product_name": "상품명",
                "category": "카테고리",
                "sourcing_type": "제작/사입",
                "season": "시즌",
                "launch_at": "출시시각",
                "48H 상태": "48시간 상태",
                "hero_score": "히로 점수(HERO Score)",
                "hero_grade": "히로 등급",
                "md_owner": "MD 담당",
            }),
            use_container_width=True,
            hide_index=True,
        )

    with tab2:
        perf_cols = [
            "product_no", "product_name", "views", "cart_count", "장바구니율",
            "order_count", "qty", "revenue", "구매전환율(CVR)", "조회당 매출(RPV)", "반품률",
        ]
        perf_cols = [c for c in perf_cols if c in data.columns]
        st.dataframe(
            data[perf_cols].rename(columns={
                "product_no": "상품번호",
                "product_name": "상품명",
                "views": "상품조회수",
                "cart_count": "장바구니",
                "order_count": "판매건수",
                "qty": "판매수량",
                "revenue": "매출",
            }),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader("MD 운영정보 수정")
    st.caption("여기서 저장한 값은 Cafe24 재동기화와 분리됩니다. HERO 관찰 ON + 출시시각 저장 시 48H 관찰건이 자동 생성됩니다.")

    choices = data[["product_no", "product_name"]].fillna("").to_dict("records")
    labels = {str(x["product_no"]): f"{x['product_no']} · {x['product_name']}" for x in choices}
    selected_no = st.selectbox(
        "수정할 상품",
        list(labels.keys()),
        format_func=lambda x: labels.get(x, x),
        key="pm_edit_product",
    )
    md = get_product_md(selected_no)
    selected_row = data[data["product_no"].astype(str) == str(selected_no)].iloc[0]
    launch_dt = _as_dt(md.get("launch_at")) or _as_dt(selected_row.get("launch_at")) or now
    sale_end_dt = _as_dt(md.get("sale_end_at"))

    existing_season = str(md.get("season") or "").strip()
    season_options = ["", "봄", "여름", "간절기", "가을", "겨울", "사계절", "기타"]
    if existing_season and existing_season not in season_options:
        season_options.insert(1, existing_season)

    existing_source = str(md.get("sourcing_type") or "").strip()
    source_options = ["", "미샵제작", "사입", "기타"]
    if existing_source and existing_source not in source_options:
        source_options.insert(1, existing_source)

    with st.form(f"pm_md_form_{selected_no}"):
        a1, a2, a3 = st.columns(3)
        hero_watch = a1.checkbox("HERO 관찰 ON", value=bool(md.get("hero_watch", False)))
        season_value = a2.selectbox(
            "시즌",
            season_options,
            index=season_options.index(existing_season) if existing_season in season_options else 0,
        )
        source_value = a3.selectbox(
            "제작/사입",
            source_options,
            index=source_options.index(existing_source) if existing_source in source_options else 0,
        )

        b1, b2, b3 = st.columns([1, 1, 1.2])
        launch_date = b1.date_input("출시일", launch_dt.date())
        launch_time = b2.time_input("출시시각", launch_dt.time().replace(microsecond=0))
        md_owner = b3.text_input("MD 담당", value=str(md.get("md_owner") or ""))

        c1, c2 = st.columns([1, 2])
        has_end = c1.checkbox("판매종료일 사용", value=bool(sale_end_dt))
        end_date_value = c1.date_input("판매종료일", sale_end_dt.date() if sale_end_dt else today, disabled=not has_end)
        md_note = c2.text_area("MD 메모", value=str(md.get("md_note") or ""), height=100)

        submitted = st.form_submit_button("운영정보 저장", type="primary", use_container_width=True)
        if submitted:
            launch_at = datetime.combine(launch_date, launch_time)
            sale_end_at = datetime.combine(end_date_value, datetime.max.time()).replace(microsecond=0) if has_end else None
            result = save_product_md(
                selected_no,
                {
                    "hero_watch": hero_watch,
                    "launch_at": launch_at,
                    "sale_end_at": sale_end_at,
                    "season": season_value or None,
                    "sourcing_type": source_value or None,
                    "md_owner": md_owner.strip() or None,
                    "md_note": md_note.strip() or None,
                },
            )
            if hero_watch:
                # 신규 HERO 관찰상품은 저장 직후 첫 Analytics 데이터를 즉시 수집합니다.
                # 이후 갱신은 GitHub Actions가 30분 간격으로 이어서 수행합니다.
                try:
                    with st.spinner("첫 판매반응 데이터를 불러오는 중입니다..."):
                        immediate_count = sync_launch_metrics(product_no=selected_no)
                    if immediate_count:
                        st.toast("HERO 관찰 등록 · 첫 데이터까지 바로 갱신했습니다.", icon="✅")
                    else:
                        st.toast("HERO 관찰 등록 완료 · 출시 전 상품은 출시 후 자동 수집됩니다.", icon="✅")
                except Exception as e:
                    # 운영정보 저장 자체는 성공 상태로 유지하고, 수집 실패만 안내합니다.
                    st.warning(f"HERO 관찰 등록은 완료됐지만 첫 데이터 수집은 잠시 후 자동 재시도됩니다. ({e})")
            else:
                st.success("저장 완료 · HERO 관찰 OFF")
            st.rerun()

    st.info("Cafe24 상품 재동기화는 MD 운영정보를 덮어쓰지 않습니다. 반품률은 주문·반품 데이터 연동 후 자동 표시됩니다.")



def page_schedule():
    st.title("상품 스케줄")
    st.caption("출시 전 집중상품(FOCUS) · 과거 히로 특성(HERO DNA) · MD 평가와 노출일정을 관리합니다.")
    data = candidate_df()
    if data.empty:
        st.info("등록된 후보상품이 없습니다.")
    else:
        show = data.copy()
        if "focus_candidate" in show:
            show["focus_candidate"] = show["focus_candidate"].map({True: "O", False: "X"})
        cols = [
            c
            for c in [
                "exposure_plan_at",
                "supplier_product_name",
                "supply_price",
                "tentative_name",
                "focus_candidate",
                "hero_dna",
                "supplier_name",
                "order_plan_at",
                "status",
                "prelaunch_score",
                "product_no",
                "cafe24_product_name",
            ]
            if c in show.columns
        ]
        st.dataframe(
            show[cols].rename(
                columns={
                    "exposure_plan_at": "노출예정",
                    "supplier_product_name": "공급사상품명",
                    "supply_price": "공급가",
                    "tentative_name": "가칭상품명",
                    "focus_candidate": "집중상품(FOCUS)",
                    "hero_dna": "과거 히로 특성(HERO DNA)",
                    "supplier_name": "소싱처",
                    "order_plan_at": "발주예정",
                    "status": "상태",
                    "prelaunch_score": "예상 히로 점수(HERO Score)",
                    "product_no": "Cafe24 상품번호",
                    "cafe24_product_name": "Cafe24 상품명",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    with st.expander("신상품 후보 추가"):
        name = st.text_input("공급사상품명")
        tentative = st.text_input("가칭상품명")
        exposure = st.date_input("노출예정일")
        focus = st.checkbox("집중상품(FOCUS) 후보")
        dna = st.text_input("과거 히로 특성(HERO DNA)")
        md = st.slider("MD 평가", 0, 100, 50)
        season = st.slider("시즌 적합도", 0, 100, 50)
        reorder = st.slider("재주문 가능성", 0, 100, 50)
        content = st.slider("콘텐츠 확장성", 0, 100, 50)
        if st.button("후보 추가", type="primary") and name:
            from misharp_hero.repository import upsert_product, add_candidate

            score = prelaunch_score(
                focus=focus,
                md_score=md,
                season_score=season,
                reorder_score=reorder,
                content_score=content,
            )
            pid = upsert_product({"supplier_product_name": name, "product_name": tentative or name})
            add_candidate(
                {
                    "product_id": pid,
                    "supplier_product_name": name,
                    "tentative_name": tentative,
                    "exposure_plan_at": datetime.combine(exposure, datetime.min.time()),
                    "focus_candidate": focus,
                    "hero_dna": dna,
                    "md_score": md,
                    "season_score": season,
                    "reorder_score": reorder,
                    "content_score": content,
                    "prelaunch_score": score,
                    "status": "후보",
                }
            )
            st.success(f"추가 완료 · 예상 히로 점수(HERO Score) {score}")
            st.rerun()



def page_48h():
    st.title("48시간 판정")
    st.caption("실제 출시시각부터 정확히 48시간 동안 Cafe24 Analytics를 기준으로 상품 반응을 판정합니다.")
    data = current_launches()
    if data.empty:
        st.info("출시상품이 없습니다.")
        return
    show = data.copy()
    show["48시간 마감"] = pd.to_datetime(show["close_48h_at"])
    show["구매전환율(CVR)"] = show["cvr"].apply(_pct)
    show["장바구니율"] = show["cart_rate"].apply(_pct)
    show["조회당 매출(RPV)"] = show["rpv"].apply(_money)
    show["반품률"] = show["return_rate"].apply(_return_rate) if "return_rate" in show.columns else "-"
    show["MD 사후판단"] = show["md_followup"].fillna("-") if "md_followup" in show.columns else "-"
    cols = [
        "product_name",
        "launch_at",
        "48시간 마감",
        "views",
        "cart_count",
        "장바구니율",
        "order_count",
        "qty",
        "구매전환율(CVR)",
        "조회당 매출(RPV)",
        "revenue",
        "반품률",
        "hero_score",
        "hero_grade",
        "diagnosis",
        "hero_manual",
        "MD 사후판단",
    ]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(
        show[cols].rename(
            columns={
                "product_name": "상품명",
                "launch_at": "출시시각",
                "views": "상품조회수",
                "cart_count": "장바구니",
                "order_count": "판매건수",
                "qty": "판매수량",
                "revenue": "매출",
                "hero_score": "히로 점수(HERO Score)",
                "hero_grade": "자동 등급",
                "diagnosis": "자동진단",
                "hero_manual": "MD 히로(HERO)",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )



def page_hero_list():
    st.title("월간 HERO")
    data = monthly_hero_df()
    if data.empty:
        st.info("월간 HERO 데이터가 없습니다.")
        return
    months = ["전체"] + sorted(data["month"].dropna().unique().tolist(), reverse=True)
    m = st.selectbox("월", months)
    show = data if m == "전체" else data[data["month"] == m]
    st.dataframe(
        show.rename(
            columns={
                "month": "월",
                "product_name": "상품명",
                "supplier_product_name": "공급사상품명",
                "hero_status": "히로(HERO)",
                "qty": "판매수량",
                "revenue": "매출",
                "margin_rate": "공헌이익률",
                "gross_profit": "공헌이익액",
                "keep_status": "유지여부",
                "revenue_rank": "매출순위",
                "profit_rank": "이익순위",
                "margin_rank": "이익률순위",
                "note": "비고",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )



def page_actions():
    st.title("MD 실행")
    data = action_df()
    if not data.empty:
        st.dataframe(
            data.rename(
                columns={
                    "product_name": "상품명",
                    "issue_type": "이슈",
                    "action_text": "조치",
                    "owner": "담당",
                    "due_at": "기한",
                    "status": "상태",
                    "team": "팀",
                    "note": "메모",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    st.divider()
    with st.form("action_add"):
        product = st.text_input("상품명")
        issue = st.selectbox("이슈", ["HERO 확대", "숨은 HERO", "전환 문제", "반품", "콘텐츠", "주간회의", "기타"])
        action = st.text_area("조치내용")
        owner = st.text_input("담당")
        team = st.selectbox("팀", ["MD", "제작", "마케팅", "기타"])
        submitted = st.form_submit_button("실행 추가")
        if submitted and action:
            from misharp_hero.repository import add_action

            add_action(
                {
                    "product_name": product,
                    "issue_type": issue,
                    "action_text": action,
                    "owner": owner,
                    "team": team,
                    "status": "대기",
                }
            )
            st.success("추가했습니다.")
            st.rerun()



def page_data_settings():
    st.title("데이터·설정")
    st.caption("Cafe24 상품과 Cafe24 Analytics를 연결합니다. HERO 판정의 공식 성과 데이터는 Cafe24 Analytics입니다.")

    c1, c2, c3 = st.columns(3)
    c1.metric("DB", "연결" if DATABASE_URL else "미설정")
    c2.metric("Cafe24 Mall", CAFE24_MALL_ID or "미설정")
    c3.metric("Cafe24 토큰", "저장됨" if load_token("admin") else "없음")

    st.subheader("1. Cafe24 OAuth")
    st.caption("상품 + 주문 + 접속통계 권한을 한 번에 승인합니다. 권장 Scope: mall.read_product mall.read_order mall.read_analytics")
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
    st.subheader("2. 연결 테스트")
    t1, t2 = st.columns(2)
    if t1.button("Cafe24 상품 API 테스트"):
        try:
            result = Cafe24AdminClient().get("/products", {"limit": 1})
            st.success(f"상품 API 정상 · {len(result.get('products', []))}건 응답")
        except Exception as e:
            st.error(str(e))
    if t2.button("Cafe24 Analytics 테스트"):
        try:
            end_at = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
            start_at = end_at - timedelta(hours=24)
            rows = Cafe24AnalyticsClient().product_views(start_at, end_at)
            st.success(f"Analytics 정상 · 상품조회 지표 {len(rows):,}건")
        except Exception as e:
            st.error(str(e))


    st.divider()
    st.subheader("3. 수동 동기화")
    s1, s2, s3 = st.columns(3)
    if s1.button("Cafe24 상품 전체"):
        try:
            with st.spinner("상품 전체 동기화 중..."):
                count = sync_products_full()
            st.success(f"상품 {count:,}개 동기화")
        except Exception as e:
            st.error(str(e))
    if s2.button("Cafe24 상품 최근 48H"):
        try:
            count = sync_products_incremental(48)
            st.success(f"최근 수정상품 {count:,}개 동기화")
        except Exception as e:
            st.error(str(e))
    if s3.button("Analytics 최근 2일"):
        try:
            with st.spinner("조회·장바구니·판매 통계 동기화 중..."):
                count = sync_analytics_days(2)
            st.success(f"Analytics {count:,}개 상품-일 지표 저장")
        except Exception as e:
            st.error(str(e))


    r1, r2 = st.columns(2)
    if r1.button("48시간 HERO 다시 계산", type="primary", use_container_width=True):
        try:
            with st.spinner("48H 지표 계산 중..."):
                count = sync_launch_metrics()
            st.success(f"48시간 HERO {count:,}개 갱신")
        except Exception as e:
            st.error(str(e))

    if r2.button("반품률 갱신", use_container_width=True):
        try:
            with st.spinner("48시간 완료상품의 반품완료 데이터를 확인하는 중..."):
                count = sync_return_metrics()
            st.success(f"반품률 {count:,}개 상품 갱신")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("4. 기존 MD 엑셀 이관")
    f = st.file_uploader("미샵 핵심업무 실행서식", type=["xlsx", "xlsm"], key="md")
    if f and st.button("MD 엑셀 가져오기"):
        suffix = Path(f.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(f.getbuffer())
            path = tmp.name
        result = import_md_excel(path)
        st.success(f"완료: {result}")

    st.divider()
    st.subheader("최근 자동수집 로그")
    logs = sync_status_df(30)
    if logs.empty:
        st.info("동기화 로그가 없습니다.")
    else:
        st.dataframe(logs, use_container_width=True, hide_index=True)

    st.info("HERO 판정의 공식 성과 데이터는 Cafe24 Analytics입니다. 반품률은 최초 48시간 판매분의 실제 반품완료 비율이며 HERO Score에는 넣지 않고 사후 품질판단에 사용합니다.")
