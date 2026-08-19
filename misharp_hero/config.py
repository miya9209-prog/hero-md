import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def _streamlit_secret(name):
    try:
        import streamlit as st
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return None

def get_setting(name, default=""):
    value = _streamlit_secret(name)
    if value not in (None, ""):
        return str(value)
    return os.getenv(name, default)

DATABASE_URL = get_setting("DATABASE_URL", "sqlite:///misharp_hero.db")
TOKEN_ENCRYPTION_KEY = get_setting("TOKEN_ENCRYPTION_KEY", "")

CAFE24_MALL_ID = get_setting("CAFE24_MALL_ID", "")
CAFE24_CLIENT_ID = get_setting("CAFE24_CLIENT_ID", "")
CAFE24_CLIENT_SECRET = get_setting("CAFE24_CLIENT_SECRET", "")
CAFE24_REDIRECT_URI = get_setting("CAFE24_REDIRECT_URI", "http://localhost:8501/")
CAFE24_SCOPES = get_setting(
    "CAFE24_SCOPES",
    "mall.read_product mall.read_order",
)
CAFE24_API_VERSION = get_setting("CAFE24_API_VERSION", "2026-03-01")

CAFE24_ANALYTICS_CLIENT_ID = get_setting("CAFE24_ANALYTICS_CLIENT_ID", "")
CAFE24_ANALYTICS_CLIENT_SECRET = get_setting("CAFE24_ANALYTICS_CLIENT_SECRET", "")
CAFE24_ANALYTICS_REDIRECT_URI = get_setting(
    "CAFE24_ANALYTICS_REDIRECT_URI", CAFE24_REDIRECT_URI
)
CAFE24_ANALYTICS_AUTHORIZE_URL = get_setting("CAFE24_ANALYTICS_AUTHORIZE_URL", "")
CAFE24_ANALYTICS_TOKEN_URL = get_setting("CAFE24_ANALYTICS_TOKEN_URL", "")
