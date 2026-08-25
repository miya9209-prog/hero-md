import html

import streamlit as st

from misharp_hero.db import init_db
from misharp_hero.ui import (
    page_explore,
    page_judgment_followup,
    page_misharp_dna,
    page_product_db,
    page_data_settings,
    page_guide,
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
    :root {
      --mso-text: #202124;
      --mso-muted: #747b86;
      --mso-line: #dedfe3;
      --mso-soft: #f5f6f8;
      --mso-active: #e7ebef;
      --mso-alert: #d93025;
    }

    [data-testid="stSidebar"] {display:none;}
    [data-testid="stHeader"] {background: rgba(255,255,255,.94);}
    .block-container {
      max-width: 1640px;
      padding-top: 2.1rem;
      padding-bottom: 5rem;
      padding-left: 3.4rem;
      padding-right: 3.4rem;
    }

    .mso-brand-wrap {margin:0; padding:.2rem 0 1.15rem 0;}
    .mso-brand {
      color:#050505;
      font-size:clamp(2.15rem,3vw,3.5rem);
      font-weight:900;
      letter-spacing:-0.052em;
      line-height:1.02;
      margin:0;
    }
    .mso-brand-sub {
      margin-top:.62rem;
      color:var(--mso-muted);
      font-size:.88rem;
      letter-spacing:-0.02em;
    }

    .mso-nav {
      display:flex;
      flex-wrap:wrap;
      align-items:center;
      gap:.12rem;
      padding:.15rem 0 .72rem 0;
      margin:0 0 1.55rem 0;
      border-bottom:1px solid #202124;
    }
    .mso-nav a {
      display:inline-block;
      text-decoration:none !important;
      color:#2b3036 !important;
      font-size:.92rem;
      font-weight:680;
      letter-spacing:-0.025em;
      padding:.42rem .72rem;
      border-radius:6px;
    }
    .mso-nav a:hover {background:#f1f3f5;}
    .mso-nav a.active {
      background:var(--mso-active);
      color:#151515 !important;
      font-weight:850;
    }
    .mso-nav a.guide {
      margin-left:auto;
      color:#5f6670 !important;
      font-weight:700;
    }

    h1 {
      font-weight:860 !important;
      font-size:clamp(2.05rem,2.6vw,3rem) !important;
      letter-spacing:-0.05em !important;
      color:var(--mso-text) !important;
      margin-top:.7rem !important;
      margin-bottom:.35rem !important;
    }
    h2,h3 {letter-spacing:-0.035em !important;}

    [data-testid="stMetric"] {padding:.35rem 0 .5rem 0;}
    [data-testid="stMetricLabel"] {
      color:#555c66;
      font-weight:650;
      letter-spacing:-0.02em;
    }
    [data-testid="stMetricValue"] {
      color:#202124;
      font-weight:700;
      letter-spacing:-0.035em;
    }

    .stButton > button, .stDownloadButton > button {
      border-radius:6px;
      font-weight:650;
    }
    [data-baseweb="input"] > div,
    [data-baseweb="select"] > div {border-radius:6px !important;}

    [data-testid="stDataFrame"] {
      border:1px solid var(--mso-line);
      border-radius:4px;
      overflow:hidden;
    }

    .mso-why {
      padding:.85rem 1rem;
      border:1px solid #e7e9ed;
      background:#fafbfc;
      border-radius:8px;
      line-height:1.65;
      color:#343a40;
    }
    .mso-why b {color:#111;}

    .mso-admin-note {
      color:#6d7480;
      font-size:.82rem;
      margin-top:.25rem;
    }

    .mso-guide-step {
      padding:.85rem 0;
      border-bottom:1px solid #eef0f3;
      line-height:1.75;
    }
    .mso-guide-step:last-child {border-bottom:0;}

    .mso-footer {
      margin-top:5rem;
      padding:1.7rem 0 .4rem 0;
      border-top:1px solid var(--mso-line);
      color:#8a9099;
      font-size:.76rem;
      line-height:1.75;
      letter-spacing:-0.015em;
    }
    .mso-footer strong {color:#5f6670;font-weight:700;}

    @media (max-width:900px) {
      .block-container {padding-left:1.15rem;padding-right:1.15rem;}
      .mso-brand {font-size:2rem;}
      .mso-nav a {font-size:.82rem;padding:.36rem .48rem;}
      .mso-nav a.guide {margin-left:0;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

NAV = [
    ("explore", "상품 탐색", page_explore),
    ("judgment", "상품 판정 및 후속업무 관리", page_judgment_followup),
    ("dna", "미샵 DNA", page_misharp_dna),
    ("product-db", "상품DB", page_product_db),
    ("settings", "데이터·설정", page_data_settings),
]
PAGE_MAP = {key: func for key, _, func in NAV}
PAGE_MAP["guide"] = page_guide

raw_page = st.query_params.get("page", "explore")
if isinstance(raw_page, list):
    raw_page = raw_page[0] if raw_page else "explore"
page_key = str(raw_page or "explore")
if page_key not in PAGE_MAP:
    page_key = "explore"

st.markdown(
    """
    <div class="mso-brand-wrap">
      <div class="mso-brand">MISHARP HERO ITEM OS</div>
      <div class="mso-brand-sub">신상품 자동 탐색 → 48시간 판매반응 관찰 → 상품 판정 → 미샵 DNA → 다음 신상 기획</div>
    </div>
    """,
    unsafe_allow_html=True,
)

nav_links = []
for key, label, _ in NAV:
    active = " active" if key == page_key else ""
    nav_links.append(
        f'<a class="mso-nav-item{active}" href="?page={html.escape(key)}" target="_self">{html.escape(label)}</a>'
    )
guide_active = " active" if page_key == "guide" else ""
nav_links.append(
    f'<a class="mso-nav-item guide{guide_active}" href="?page=guide" target="_self">이용방법</a>'
)
st.markdown(f'<nav class="mso-nav">{"".join(nav_links)}</nav>', unsafe_allow_html=True)

PAGE_MAP[page_key]()

st.markdown(
    """
    <div class="mso-footer">
      <strong>© MISHARP COMPANY. All rights reserved.</strong><br>
      본 시스템 및 콘텐츠의 저작권은 MISHARP COMPANY에 있으며, 무단 복제·배포·전재·상업적 사용을 금합니다.<br>
      This system and its contents are proprietary to MISHARP COMPANY. Unauthorized copying, reproduction or distribution is prohibited.<br>
      Creator: <strong>MISHARP COMPANY PARK HYUNG JOON</strong>
    </div>
    """,
    unsafe_allow_html=True,
)
