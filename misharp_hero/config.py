import json
import os
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


def get_bool(name, default=False):
    raw = get_setting(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def get_int(name, default):
    try:
        return int(get_setting(name, str(default)))
    except Exception:
        return int(default)


def get_json(name, default=None):
    raw = get_setting(name, "")
    if not raw:
        return {} if default is None else default
    try:
        return json.loads(raw)
    except Exception:
        return {} if default is None else default


DATABASE_URL = get_setting("DATABASE_URL", "sqlite:///misharp_hero.db")
TOKEN_ENCRYPTION_KEY = get_setting("TOKEN_ENCRYPTION_KEY", "")

# Cafe24 Admin + Analytics: 동일 EC Admin OAuth 토큰 사용
CAFE24_MALL_ID = get_setting("CAFE24_MALL_ID", "")
CAFE24_CLIENT_ID = get_setting("CAFE24_CLIENT_ID", "")
CAFE24_CLIENT_SECRET = get_setting("CAFE24_CLIENT_SECRET", "")
CAFE24_REDIRECT_URI = get_setting("CAFE24_REDIRECT_URI", "http://localhost:8501/")
CAFE24_SCOPES = get_setting(
    "CAFE24_SCOPES",
    "mall.read_product mall.read_order mall.read_analytics",
)
CAFE24_API_VERSION = get_setting("CAFE24_API_VERSION", "2026-03-01")
CAFE24_SHOP_NO = get_int("CAFE24_SHOP_NO", 1)

# Sellmate API: 셀메이트에서 발급받은 실제 API 문서/키 값을 넣는다.
# 공개 웹에서 엔드포인트 세부 스펙을 추정하지 않고 설정으로 주입하는 구조.
SELLMATE_ENABLED = get_bool("SELLMATE_ENABLED", False)
SELLMATE_API_BASE_URL = get_setting("SELLMATE_API_BASE_URL", "")
SELLMATE_API_TOKEN = get_setting("SELLMATE_API_TOKEN", "")
SELLMATE_INVENTORY_PATH = get_setting("SELLMATE_INVENTORY_PATH", "")
SELLMATE_INVENTORY_METHOD = get_setting("SELLMATE_INVENTORY_METHOD", "GET").upper()
SELLMATE_AUTH_HEADER = get_setting("SELLMATE_AUTH_HEADER", "Authorization")
SELLMATE_AUTH_PREFIX = get_setting("SELLMATE_AUTH_PREFIX", "Bearer")
SELLMATE_PAGE_MODE = get_setting("SELLMATE_PAGE_MODE", "page").lower()  # page | offset | none
SELLMATE_PAGE_PARAM = get_setting("SELLMATE_PAGE_PARAM", "page")
SELLMATE_OFFSET_PARAM = get_setting("SELLMATE_OFFSET_PARAM", "offset")
SELLMATE_PAGE_SIZE_PARAM = get_setting("SELLMATE_PAGE_SIZE_PARAM", "limit")
SELLMATE_PAGE_SIZE = get_int("SELLMATE_PAGE_SIZE", 100)
SELLMATE_RESPONSE_LIST_KEY = get_setting("SELLMATE_RESPONSE_LIST_KEY", "data")
SELLMATE_EXTRA_PARAMS = get_json("SELLMATE_EXTRA_PARAMS_JSON", {})
SELLMATE_PRODUCT_NO_FIELD = get_setting("SELLMATE_PRODUCT_NO_FIELD", "product_no")
SELLMATE_PRODUCT_CODE_FIELD = get_setting("SELLMATE_PRODUCT_CODE_FIELD", "product_code")
SELLMATE_VARIANT_CODE_FIELD = get_setting("SELLMATE_VARIANT_CODE_FIELD", "variant_code")
SELLMATE_STOCK_FIELD = get_setting("SELLMATE_STOCK_FIELD", "stock_qty")
SELLMATE_AVAILABLE_FIELD = get_setting("SELLMATE_AVAILABLE_FIELD", "available_qty")
SELLMATE_WAREHOUSE_FIELD = get_setting("SELLMATE_WAREHOUSE_FIELD", "warehouse")

# SERA: 기본은 엑셀 업로드. 직접 다운로드 URL을 제공받은 경우 자동 수집 가능.
SERA_REPORT_URL = get_setting("SERA_REPORT_URL", "")
SERA_AUTH_HEADER = get_setting("SERA_AUTH_HEADER", "")
SERA_AUTH_TOKEN = get_setting("SERA_AUTH_TOKEN", "")
