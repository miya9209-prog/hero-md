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
    SELLMATE_ENABLED,
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
    sync_status_df,
    df,
)
from misharp_hero.services.cafe24_admin import Cafe24AdminClient, sync_products_full, sync_products_incremental
from misharp_hero.services.cafe24_analytics import Cafe24AnalyticsClient, sync_analytics_days
from misharp_hero.services.md_excel_import import import_md_excel
from misharp_hero.services.oauth import AdminOAuth, load_token
from misharp_hero.services.sellmate import SellmateClient, sync_inventory
from misharp_hero.services.sera_import import import_sera_excel
from misharp_hero.services.sync import sync_launch_metrics


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
    st.caption("Cafe24 Analytics + SERA + Sellmate 재고를 결합한 48H 의사결정 화면")
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
    c1.metric("48H 관찰중", len(active))
    c2.metric("HERO", len(hero))
    c3.metric("숨은 HERO", len(hidden))
    c4.metric("전환문제", len(conversion))
    c5.metric("미완료 실행", len(open_actions))

    show = launches.copy()
    show["경과(H)"] = ((now - pd.to_datetime(show["launch_at"])).dt.total_seconds() / 3600).clip(lower=0).round(1)
    show["48H 상태"] = show.apply(lambda r: _watch_status(r, now.to_pydatetime()), axis=1)
    show["CVR"] = show["cvr"].apply(_pct)
    show["장바구니율"] = show["cart_rate"].apply(_pct)
    show["RPV"] = show["rpv"].apply(_money)
    show["셀메이트재고"] = show["sellmate_stock_qty"].apply(_intfmt)

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
        "CVR",
        "RPV",
        "셀메이트재고",
        "hero_score",
        "hero_grade",
        "diagnosis",
    ]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(
        show[cols].rename(
            columns={
                "product_name": "상품명",
                "views": "조회",
                "cart_count": "장바구니",
                "order_count": "판매건수",
                "qty": "판매수량",
                "revenue": "매출",
                "hero_score": "HERO Score",
                "hero_grade": "등급",
                "diagnosis": "자동진단",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )



def page_product_master():
    st.title("상품 마스터")
    st.caption("Cafe24 원본정보와 MD 운영정보를 분리 관리하고, HERO 관찰상품을 48H 판정으로 자동 연결합니다.")

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
    data["Sellmate 재고"] = data["sellmate_stock_qty"].apply(_intfmt)
    data["CVR"] = data["cvr"].apply(_pct)
    data["장바구니율"] = data["cart_rate"].apply(_pct)
    data["RPV"] = data["rpv"].apply(_money)

    tab1, tab2 = st.tabs(["운영 마스터", "기간 성과"])
    with tab1:
        master_cols = [
            "product_no", "product_code", "product_name", "판매가", "소비자가",
            "판매상태", "진열상태", "category", "sourcing_type", "season",
            "HERO 관찰", "launch_at", "48H 상태", "hero_score", "hero_grade",
            "Sellmate 재고", "md_owner",
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
                "hero_score": "HERO Score",
                "hero_grade": "HERO 등급",
                "md_owner": "MD 담당",
            }),
            use_container_width=True,
            hide_index=True,
        )

    with tab2:
        perf_cols = [
            "product_no", "product_name", "views", "cart_count", "장바구니율",
            "order_count", "qty", "revenue", "CVR", "RPV",
            "sera_opv", "sera_espv", "sera_click_value",
        ]
        perf_cols = [c for c in perf_cols if c in data.columns]
        st.dataframe(
            data[perf_cols].rename(columns={
                "product_no": "상품번호",
                "product_name": "상품명",
                "views": "조회",
                "cart_count": "장바구니",
                "order_count": "판매건수",
                "qty": "판매수량",
                "revenue": "매출",
                "sera_opv": "SERA OpV",
                "sera_espv": "SERA ESpV",
                "sera_click_value": "SERA 클릭가치",
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
                st.success(f"저장 완료 · 48H 관찰 연결 #{result.get('launch_id')}")
            else:
                st.success("저장 완료 · HERO 관찰 OFF")
            st.rerun()

    st.info("실제 재고의 단일 기준은 Sellmate입니다. Cafe24 상품 재동기화는 MD 운영정보를 덮어쓰지 않습니다.")



def page_schedule():
    st.title("상품 스케줄")
    st.caption("출시 전 FOCUS · HERO DNA · MD 평가와 노출일정을 관리합니다.")
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
                    "focus_candidate": "FOCUS",
                    "hero_dna": "HERO DNA",
                    "supplier_name": "소싱처",
                    "order_plan_at": "발주예정",
                    "status": "상태",
                    "prelaunch_score": "예상 HERO Score",
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
        focus = st.checkbox("FOCUS 후보")
        dna = st.text_input("과거 HERO DNA")
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
            st.success(f"추가 완료 · 예상 HERO Score {score}")
            st.rerun()



def page_48h():
    st.title("48H 판정")
    st.caption("노출시각 기준 정확한 48시간 동안 Analytics·SERA·Sellmate를 결합합니다.")
    data = current_launches()
    if data.empty:
        st.info("출시상품이 없습니다.")
        return
    show = data.copy()
    show["48H 마감"] = pd.to_datetime(show["close_48h_at"])
    show["CVR"] = show["cvr"].apply(_pct)
    show["장바구니율"] = show["cart_rate"].apply(_pct)
    show["RPV"] = show["rpv"].apply(_money)
    show["Sellmate 재고"] = show["sellmate_stock_qty"].apply(_intfmt)
    cols = [
        "product_name",
        "launch_at",
        "48H 마감",
        "views",
        "cart_count",
        "장바구니율",
        "order_count",
        "qty",
        "CVR",
        "RPV",
        "revenue",
        "Sellmate 재고",
        "sera_opv",
        "sera_espv",
        "sera_click_value",
        "hero_score",
        "hero_grade",
        "diagnosis",
        "hero_manual",
        "review_manual",
    ]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(
        show[cols].rename(
            columns={
                "product_name": "상품명",
                "launch_at": "노출시각",
                "views": "조회",
                "cart_count": "장바구니",
                "order_count": "판매건수",
                "qty": "판매수량",
                "revenue": "매출",
                "sera_opv": "SERA OpV",
                "sera_espv": "SERA ESpV",
                "sera_click_value": "SERA 클릭가치",
                "hero_score": "HERO Score",
                "hero_grade": "자동등급",
                "diagnosis": "자동진단",
                "hero_manual": "MD HERO",
                "review_manual": "재검토",
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
                "hero_status": "HERO",
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
        issue = st.selectbox("이슈", ["HERO 확대", "숨은 HERO", "전환문제", "재고", "콘텐츠", "주간회의", "기타"])
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
    st.caption("Cafe24 상품/Analytics · Sellmate 실제 재고 · SERA 보고서를 연결합니다.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("DB", "연결" if DATABASE_URL else "미설정")
    c2.metric("Cafe24 Mall", CAFE24_MALL_ID or "미설정")
    c3.metric("Cafe24 토큰", "저장됨" if load_token("admin") else "없음")
    c4.metric("Sellmate", "설정됨" if SellmateClient().configured() else "대기")

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
    t1, t2, t3 = st.columns(3)
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
    if t3.button("Sellmate 재고 API 테스트"):
        try:
            rows = SellmateClient().inventory_rows(max_pages=1)
            st.success(f"Sellmate 정상 · 첫 페이지 {len(rows):,}건")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("3. 수동 동기화")
    s1, s2, s3, s4 = st.columns(4)
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
    if s4.button("Sellmate 실제 재고"):
        try:
            with st.spinner("Sellmate 재고 동기화 중..."):
                count, mapped = sync_inventory()
            st.success(f"Sellmate {count:,} SKU · Cafe24 상품 매핑 {mapped:,}건")
        except Exception as e:
            st.error(str(e))

    if st.button("48H HERO 다시 계산", type="primary"):
        try:
            with st.spinner("48H 지표 계산 중..."):
                count = sync_launch_metrics()
            st.success(f"48H HERO {count:,}개 갱신")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("4. SERA 데이터")
    s = st.file_uploader("SERA 엑셀 업로드", type=["xlsx", "xlsm"], key="sera")
    if s and st.button("SERA 가져오기"):
        suffix = Path(s.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(s.getbuffer())
            path = tmp.name
        count = import_sera_excel(path)
        st.success(f"SERA {count:,}행 적재")

    st.divider()
    st.subheader("5. 기존 MD 엑셀 이관")
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

    st.info("실제 재고의 단일 기준(Source of Truth)은 Sellmate입니다. Cafe24 Admin 재고는 의사결정 지표에 사용하지 않습니다.")
