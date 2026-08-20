from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import pandas as pd
import streamlit as st
from sqlalchemy import select

from misharp_hero.db import session_scope, get_session
from misharp_hero.models import Candidate, Product, ActionItem
from misharp_hero.repository import (
    current_launches, candidate_df, monthly_hero_df, action_df, df
)
from misharp_hero.hero_score import prelaunch_score
from misharp_hero.services.md_excel_import import import_md_excel
from misharp_hero.services.sera_import import import_sera_excel
from misharp_hero.services.oauth import AdminOAuth, AnalyticsOAuth, load_token
from misharp_hero.services.cafe24_admin import Cafe24AdminClient, sync_products
from misharp_hero.config import (
    DATABASE_URL, CAFE24_MALL_ID, CAFE24_CLIENT_ID, CAFE24_REDIRECT_URI,
    CAFE24_ANALYTICS_AUTHORIZE_URL
)


def _pct(v):
    try:
        return f"{float(v)*100:.2f}%"
    except Exception:
        return "-"


def _money(v):
    try:
        return f"{float(v):,.0f}원"
    except Exception:
        return "-"


def page_radar():
    st.title("오늘의 히로 레이더")
    launches = current_launches()
    actions = action_df()

    if launches.empty:
        st.info("아직 출시상품 데이터가 없습니다. 기존 MD 엑셀을 먼저 가져오세요.")
        return

    now = pd.Timestamp.now()
    launch_dt = pd.to_datetime(launches["launch_at"])
    close_dt = pd.to_datetime(launches["close_48h_at"])
    active = launches[(launch_dt <= now) & (close_dt >= now)]
    hero = launches[launches["hero_score"].fillna(0) >= 85]
    hidden = launches[launches["diagnosis"].fillna("").str.contains("숨은", na=False)]
    conversion = launches[launches["diagnosis"].fillna("").str.contains("전환 문제", na=False)]
    open_actions = actions[actions["status"] != "완료"] if not actions.empty else actions

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("48H 관찰중", len(active))
    c2.metric("HERO", len(hero))
    c3.metric("숨은 HERO", len(hidden))
    c4.metric("전환문제", len(conversion))
    c5.metric("미완료 Action", len(open_actions))

    show = launches.copy()
    show["경과"] = (
        (now - pd.to_datetime(show["launch_at"])).dt.total_seconds() / 3600
    ).clip(lower=0).round(1)
    show["CVR"] = show["cvr"].apply(_pct)
    show["RPV"] = show["rpv"].apply(_money)

    cols = [
        "product_name", "경과", "views", "order_count", "qty", "revenue",
        "CVR", "RPV", "hero_score", "hero_grade", "diagnosis"
    ]

    st.subheader("상품 현황")
    st.dataframe(
        show[cols].rename(columns={
            "product_name": "상품명",
            "views": "조회",
            "order_count": "판매건수",
            "qty": "판매수량",
            "revenue": "매출",
            "hero_score": "HERO Score",
            "hero_grade": "등급",
            "diagnosis": "자동진단",
        }),
        use_container_width=True,
        hide_index=True,
    )


def page_schedule():
    st.title("상품 스케줄")
    st.caption("출시 전 FOCUS · HERO DNA · MD 평가와 노출일정을 관리합니다.")

    data = candidate_df()

    if data.empty:
        st.info("등록된 후보상품이 없습니다.")
    else:
        show = data.copy()

        for c in ["focus_candidate"]:
            if c in show:
                show[c] = show[c].map({True: "O", False: "X"})

        cols = [
            c for c in [
                "exposure_plan_at", "supplier_product_name", "supply_price",
                "tentative_name", "focus_candidate", "hero_dna", "supplier_name",
                "order_plan_at", "status", "prelaunch_score", "product_no",
                "cafe24_product_name"
            ]
            if c in show.columns
        ]

        st.dataframe(
            show[cols].rename(columns={
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
            }),
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
            score = prelaunch_score(
                focus=focus,
                md_score=md,
                season_score=season,
                reorder_score=reorder,
                content_score=content,
            )

            from misharp_hero.repository import upsert_product, add_candidate

            pid = upsert_product({
                "supplier_product_name": name,
                "product_name": tentative or name,
            })

            add_candidate({
                "product_id": pid,
                "supplier_product_name": name,
                "tentative_name": tentative,
                "exposure_plan_at": datetime.combine(
                    exposure, datetime.min.time()
                ),
                "focus_candidate": focus,
                "hero_dna": dna,
                "md_score": md,
                "season_score": season,
                "reorder_score": reorder,
                "content_score": content,
                "prelaunch_score": score,
                "status": "후보",
            })

            st.success(f"추가 완료 · 예상 HERO Score {score}")
            st.rerun()


def page_48h():
    st.title("48H 상품체크")
    data = current_launches()

    if data.empty:
        st.info("출시상품이 없습니다.")
        return

    show = data.copy()
    show["48H 마감"] = pd.to_datetime(show["close_48h_at"])
    show["CVR"] = show["cvr"].apply(_pct)
    show["수량전환율"] = show["qty_cvr"].apply(_pct)
    show["RPV"] = show["rpv"].apply(_money)

    cols = [
        "product_name", "launch_at", "48H 마감", "views", "order_count",
        "qty", "CVR", "수량전환율", "RPV", "revenue", "hero_score",
        "hero_grade", "diagnosis", "hero_manual", "review_manual"
    ]

    st.dataframe(
        show[cols].rename(columns={
            "product_name": "상품명",
            "launch_at": "노출시각",
            "views": "조회",
            "order_count": "판매건수",
            "qty": "판매수량",
            "revenue": "매출",
            "hero_score": "HERO Score",
            "hero_grade": "자동등급",
            "diagnosis": "자동진단",
            "hero_manual": "MD HERO",
            "review_manual": "재검토",
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "API 연동 전 엑셀 이관값의 판매건수는 판매수량을 임시 대체값으로 사용합니다. "
        "Analytics 연동 후 정확한 판매건수로 갱신됩니다."
    )


def page_hero_list():
    st.title("월간 HERO")
    data = monthly_hero_df()

    if data.empty:
        st.info("월간 HERO 데이터가 없습니다.")
        return

    months = ["전체"] + sorted(
        data["month"].dropna().unique().tolist(),
        reverse=True,
    )

    m = st.selectbox("월", months)
    show = data if m == "전체" else data[data["month"] == m]

    st.dataframe(
        show.rename(columns={
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
        }),
        use_container_width=True,
        hide_index=True,
    )


def page_actions():
    st.title("MD Action")
    data = action_df()

    if not data.empty:
        st.dataframe(
            data.rename(columns={
                "product_name": "상품명",
                "issue_type": "이슈",
                "action_text": "조치",
                "owner": "담당",
                "due_at": "기한",
                "status": "상태",
                "team": "팀",
                "note": "메모",
            }),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    with st.form("action_add"):
        product = st.text_input("상품명")
        issue = st.selectbox(
            "이슈",
            ["HERO 확대", "숨은 HERO", "전환문제", "재고", "콘텐츠", "주간회의", "기타"],
        )
        action = st.text_area("조치내용")
        owner = st.text_input("담당")
        team = st.selectbox("팀", ["MD", "제작", "마케팅", "기타"])
        submitted = st.form_submit_button("Action 추가")

        if submitted and action:
            from misharp_hero.repository import add_action

            add_action({
                "product_name": product,
                "issue_type": issue,
                "action_text": action,
                "owner": owner,
                "team": team,
                "status": "대기",
            })

            st.success("추가했습니다.")
            st.rerun()


def page_import():
    st.title("데이터 가져오기")

    st.subheader("기존 MD 엑셀")
    f = st.file_uploader(
        "미샵 핵심업무 실행서식 업로드",
        type=["xlsx", "xlsm"],
        key="md",
    )

    if f and st.button("MD 엑셀 가져오기"):
        suffix = Path(f.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(f.getbuffer())
            p = tmp.name

        result = import_md_excel(p)
        st.success(f"완료: {result}")

    st.divider()
    st.subheader("SERA 보고서")

    s = st.file_uploader(
        "SERA 엑셀 업로드",
        type=["xlsx", "xlsm"],
        key="sera",
    )

    if s and st.button("SERA 가져오기"):
        suffix = Path(s.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(s.getbuffer())
            p = tmp.name

        count = import_sera_excel(p)
        st.success(f"SERA {count}행을 적재했습니다.")

    sera = df(
        "SELECT report_name, product_no, product_name, views, orders, qty, "
        "revenue, opv, espv, imported_at "
        "FROM sera_metrics "
        "ORDER BY imported_at DESC "
        "LIMIT 100"
    )

    if not sera.empty:
        st.subheader("최근 SERA 적재")
        st.dataframe(
            sera,
            use_container_width=True,
            hide_index=True,
        )


def page_settings():
    st.title("설정·연동")

    c1, c2, c3 = st.columns(3)
    c1.metric("DB", "연결" if DATABASE_URL else "미설정")
    c2.metric("Cafe24 Mall", CAFE24_MALL_ID or "미설정")
    c3.metric("Admin 토큰", "저장됨" if load_token("admin") else "없음")

    st.caption("민감정보는 이 화면에서 공개하지 않습니다.")

    st.subheader("Cafe24 Admin OAuth")

    if CAFE24_MALL_ID and CAFE24_CLIENT_ID and CAFE24_REDIRECT_URI:
        try:
            st.link_button(
                "Cafe24 Admin 권한 승인 열기",
                AdminOAuth().authorize_url(),
            )
        except Exception as e:
            st.error(str(e))

        code = st.text_input(
            "승인 후 Admin code 붙여넣기",
            type="password",
        )

        if st.button("Admin 토큰 저장") and code:
            try:
                AdminOAuth().exchange_code(code)
                st.success("Admin 토큰을 암호화 저장했습니다.")
            except Exception as e:
                st.error(f"실패: {e}")

    else:
        st.warning(
            "CAFE24_MALL_ID / CLIENT_ID / REDIRECT_URI를 먼저 설정하세요."
        )

    st.divider()
    st.subheader("Cafe24 Analytics OAuth")

    if AnalyticsOAuth().configured():
        st.link_button(
            "Analytics 권한 승인 열기",
            AnalyticsOAuth().authorize_url(),
        )

        acode = st.text_input(
            "승인 후 Analytics code 붙여넣기",
            type="password",
        )

        if st.button("Analytics 토큰 저장") and acode:
            try:
                AnalyticsOAuth().exchange_code(acode)
                st.success("Analytics 토큰을 암호화 저장했습니다.")
            except Exception as e:
                st.error(f"실패: {e}")

    else:
        st.info(
            "Analytics 전용 앱을 사용하지 않는 경우 비워둘 수 있습니다. "
            "별도 앱이 필요하면 Setup Guide의 Analytics 절차를 따라 "
            "URL과 Client 정보를 입력하세요."
        )

    st.divider()
    st.subheader("연결 테스트")

    if st.button("설정 진단"):
        issues = []

        if not DATABASE_URL:
            issues.append("DATABASE_URL")

        if not CAFE24_MALL_ID:
            issues.append("CAFE24_MALL_ID")

        if not CAFE24_CLIENT_ID:
            issues.append("CAFE24_CLIENT_ID")

        if issues:
            st.warning("미설정: " + ", ".join(issues))

        elif not load_token("admin"):
            st.warning("Cafe24 관리자 토큰이 없습니다.")

        else:
            try:
                client = Cafe24AdminClient()
                result = client.get(
                    "/products",
                    {"limit": 1},
                )

                products = result.get("products", [])

                st.success(
                    f"Cafe24 관리자 API 연결 정상 · "
                    f"상품 조회 응답 {len(products)}개 확인"
                )

            except Exception as e:
                st.error(
                    f"Cafe24 관리자 API 연결 실패: {e}"
                )

    st.divider()
    st.subheader("Cafe24 상품 동기화")
    st.caption(
        "Cafe24의 상품번호, 상품코드, 상품명, 판매가, 재고 등 "
        "기본 상품정보를 Supabase에 저장합니다."
    )

    if st.button("Cafe24 상품 동기화", type="primary"):
        if not load_token("admin"):
            st.warning("먼저 Cafe24 관리자 인증을 완료하세요.")
        else:
            try:
                with st.spinner("Cafe24 상품을 가져오는 중입니다..."):
                    count = sync_products()

                st.success(
                    f"Cafe24 상품 동기화 완료 · {count:,}개 상품 저장"
                )

            except Exception as e:
                st.error(
                    f"Cafe24 상품 동기화 실패: {e}"
                )
