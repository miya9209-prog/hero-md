import streamlit as st
from misharp_hero.db import init_db
from misharp_hero.ui import (
    page_radar, page_schedule, page_48h, page_hero_list,
    page_actions, page_import, page_settings
)

st.set_page_config(
    page_title="미샵 히로 MD",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

st.sidebar.title("미샵 히로 MD")
st.sidebar.caption("히로상품 예측 · 48H 판정 · 실행관리")

menu = st.sidebar.radio(
    "메뉴",
    [
        "오늘의 히로 레이더",
        "상품 스케줄",
        "48H 상품체크",
        "월간 HERO",
        "MD Action",
        "데이터 가져오기",
        "설정·연동",
    ],
)

if menu == "오늘의 히로 레이더":
    page_radar()
elif menu == "상품 스케줄":
    page_schedule()
elif menu == "48H 상품체크":
    page_48h()
elif menu == "월간 HERO":
    page_hero_list()
elif menu == "MD Action":
    page_actions()
elif menu == "데이터 가져오기":
    page_import()
else:
    page_settings()
