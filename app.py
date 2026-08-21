import streamlit as st

from misharp_hero.db import init_db
from misharp_hero.ui import (
    page_radar,
    page_product_master,
    page_schedule,
    page_48h,
    page_hero_list,
    page_actions,
    page_data_settings,
)

st.set_page_config(
    page_title="MISHARP HERO ITEM OS",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

init_db()

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {display:none;}
    .block-container {padding-top: 1.2rem; padding-bottom: 3rem;}
    .hero-os-title {font-size: 2rem; font-weight: 800; letter-spacing: -0.03em; margin-bottom: 0.1rem;}
    .hero-os-sub {color: #6b7280; margin-bottom: 0.8rem;}
    </style>
    <div class="hero-os-title">MISHARP HERO ITEM OS</div>
    <div class="hero-os-sub">상품 발굴 → 노출 → 48H 판정 → 확대/중단 → 재고·실행관리</div>
    """,
    unsafe_allow_html=True,
)

pages = [
    st.Page(page_radar, title="히로 레이더", default=True),
    st.Page(page_product_master, title="상품 마스터"),
    st.Page(page_schedule, title="상품 스케줄"),
    st.Page(page_48h, title="48H 판정"),
    st.Page(page_hero_list, title="월간 HERO"),
    st.Page(page_actions, title="MD 실행"),
    st.Page(page_data_settings, title="데이터·설정"),
]

pg = st.navigation(pages, position="top")
pg.run()
