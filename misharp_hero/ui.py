from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
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
    current_launches,
    monthly_hero_df,
    product_master_df,
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


def page_radar():
    st.title("히로 레이더")
    st.caption("Cafe24 Analytics + SERA + Sellmate 재고를 결합한 48H 의사결정 화면")
    launches = current_launches()
    actions = action_df()

    if launches.empty:
        st.info("아직 출시상품 데이터가 없습니다. 상품 스케줄 또는 기존 MD 엑셀을 먼저 등록하세요.")
        return

    now = pd.Timestamp.now()
    launch_dt = pd.to_datetime(launches["launch_at"])
    close_dt = pd.to_datetime(launches["close_48h_at"])
    active = launches[(launch_dt <= now) & (close_dt >= now)]
    hero = launches[launches["hero_score"].fillna(0) >= 85]
    hidden = launches[launches["diagnosis"].fillna("").str.contains("숨은", na=False)]
    conversion = launches[launches["diagnosis"].fillna("").str.contains("전환|이탈", na=False)]
    open_actions = actions[actions["status"] != "완료"] if not actions.empty else actions

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("48H 관찰중", len(active))
    c2.metric("HERO", len(hero))
    c3.metric("숨은 HERO", len(hidden))
    c4.metric("전환문제", len(conversion))
    c5.metric("미완료 실행", len(open_actions))

    show = launches.copy()
    show["경과(H)"] = ((now - pd.to_datetime(show["launch_at"])).dt.total_seconds() / 3600).clip(lower=0).round(1)
    show["CVR"] = show["cvr"].apply(_pct)
    show["장바구니율"] = show["cart_rate"].apply(_pct)
    show["RPV"] = show["rpv"].apply(_money)
    show["셀메이트재고"] = show["sellmate_stock_qty"].apply(_intfmt)

    cols = [
        "product_name",
        "경과(H)",
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
    st.caption("Cafe24 상품 마스터 + Cafe24 Analytics 통계 + SERA 보완지표 + Sellmate 실제 재고")

    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    c1, c2, c3 = st.columns([1, 1, 2])
    start = c1.date_input("통계 시작일", today - timedelta(days=6))
    end = c2.date_input("통계 종료일", today)
    search = c3.text_input("상품 검색", placeholder="상품명 / 상품코드 / 상품번호")

    data = product_master_df(start.isoformat(), end.isoformat(), search=search, limit=2500)
    total = count_products()
    st.caption(f"Cafe24 상품 마스터 총 {total:,}개 · 현재 화면 {len(data):,}개")
    if data.empty:
        st.info("조건에 맞는 상품이 없습니다.")
        return

    for c in ["views", "cart_count", "order_count", "qty", "revenue", "sellmate_stock_qty"]:
        if c not in data.columns:
            data[c] = 0
    for c in ["cvr", "cart_rate", "rpv"]:
        if c not in data.columns:
            data[c] = 0.0

    data["CVR"] = data["cvr"].apply(_pct)
    data["장바구니율"] = data["cart_rate"].apply(_pct)
    data["RPV"] = data["rpv"].apply(_money)
    data["판매가"] = data["selling_price"].apply(_money)
    data["Sellmate 재고"] = data["sellmate_stock_qty"].apply(_intfmt)

    cols = [
        "product_no",
        "product_code",
        "product_name",
        "판매가",
        "Sellmate 재고",
        "views",
        "cart_count",
        "장바구니율",
        "order_count",
        "qty",
        "revenue",
        "CVR",
        "RPV",
        "sera_opv",
        "sera_espv",
        "sera_click_value",
    ]
    cols = [c for c in cols if c in data.columns]
    st.dataframe(
        data[cols].rename(
            columns={
                "product_no": "상품번호",
                "product_code": "상품코드",
                "product_name": "상품명",
                "views": "조회",
                "cart_count": "장바구니",
                "order_count": "판매건수",
                "qty": "판매수량",
                "revenue": "매출",
                "sera_opv": "SERA OpV",
                "sera_espv": "SERA ESpV",
                "sera_click_value": "SERA 클릭가치",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.info("재고 기준은 Sellmate입니다. Cafe24 Admin 재고수량은 이 화면과 HERO 판정에 사용하지 않습니다.")



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
            end_at = datetime.now()
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
