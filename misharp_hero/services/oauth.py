from __future__ import annotations
import base64
from datetime import datetime, timedelta
from urllib.parse import urlencode
import requests
from sqlalchemy import select
from misharp_hero.config import (
    CAFE24_MALL_ID, CAFE24_CLIENT_ID, CAFE24_CLIENT_SECRET, CAFE24_REDIRECT_URI,
    CAFE24_SCOPES, CAFE24_ANALYTICS_CLIENT_ID, CAFE24_ANALYTICS_CLIENT_SECRET,
    CAFE24_ANALYTICS_REDIRECT_URI, CAFE24_ANALYTICS_AUTHORIZE_URL,
    CAFE24_ANALYTICS_TOKEN_URL
)
from misharp_hero.db import session_scope, get_session
from misharp_hero.models import OAuthToken
from misharp_hero.security import encrypt_text, decrypt_text

def parse_scopes(value):
    return [x for x in value.replace(",", " ").split() if x]

def _basic_header(client_id, secret):
    raw = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    return {
        "Authorization": f"Basic {raw}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

class AdminOAuth:
    @property
    def base(self):
        if not CAFE24_MALL_ID:
            raise RuntimeError("CAFE24_MALL_ID가 없습니다.")
        return f"https://{CAFE24_MALL_ID}.cafe24api.com/api/v2"

    def authorize_url(self):
        return f"{self.base}/oauth/authorize?" + urlencode({
            "response_type": "code",
            "client_id": CAFE24_CLIENT_ID,
            "redirect_uri": CAFE24_REDIRECT_URI,
            "scope": ",".join(parse_scopes(CAFE24_SCOPES)),
        })

    def exchange_code(self, code):
        r = requests.post(
            f"{self.base}/oauth/token",
            headers=_basic_header(CAFE24_CLIENT_ID, CAFE24_CLIENT_SECRET),
            data={
                "grant_type": "authorization_code",
                "code": code.strip(),
                "redirect_uri": CAFE24_REDIRECT_URI,
            },
            timeout=30,
        )
        r.raise_for_status()
        token = r.json()
        save_token("admin", token)
        return token

    def refresh(self, refresh_token):
        r = requests.post(
            f"{self.base}/oauth/token",
            headers=_basic_header(CAFE24_CLIENT_ID, CAFE24_CLIENT_SECRET),
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=30,
        )
        r.raise_for_status()
        token = r.json()
        save_token("admin", token)
        return token

class AnalyticsOAuth:
    def configured(self):
        return bool(CAFE24_MALL_ID and CAFE24_ANALYTICS_CLIENT_ID and CAFE24_ANALYTICS_CLIENT_SECRET)

    @property
    def authorize_endpoint(self):
        return CAFE24_ANALYTICS_AUTHORIZE_URL or f"https://{CAFE24_MALL_ID}.cafe24api.com/api/v2/oauth/authorize"

    @property
    def token_endpoint(self):
        return CAFE24_ANALYTICS_TOKEN_URL or f"https://{CAFE24_MALL_ID}.cafe24api.com/api/v2/oauth/token"

    def authorize_url(self):
        if not self.configured():
            raise RuntimeError("Analytics 전용 Client ID/Secret 설정이 없습니다.")
        return self.authorize_endpoint + "?" + urlencode({
            "response_type": "code",
            "client_id": CAFE24_ANALYTICS_CLIENT_ID,
            "redirect_uri": CAFE24_ANALYTICS_REDIRECT_URI,
            "scope": "mall.read_analytics",
        })

    def exchange_code(self, code):
        r = requests.post(
            self.token_endpoint,
            headers=_basic_header(CAFE24_ANALYTICS_CLIENT_ID, CAFE24_ANALYTICS_CLIENT_SECRET),
            data={
                "grant_type": "authorization_code",
                "code": code.strip(),
                "redirect_uri": CAFE24_ANALYTICS_REDIRECT_URI,
            },
            timeout=30,
        )
        r.raise_for_status()
        token = r.json()
        save_token("analytics", token)
        return token

    def refresh(self, refresh_token):
        r = requests.post(
            self.token_endpoint,
            headers=_basic_header(CAFE24_ANALYTICS_CLIENT_ID, CAFE24_ANALYTICS_CLIENT_SECRET),
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=30,
        )
        r.raise_for_status()
        token = r.json()
        save_token("analytics", token)
        return token

def save_token(provider, token):
    access = token.get("access_token")
    refresh = token.get("refresh_token")
    expires_in = int(token.get("expires_in") or 7200)
    expires_at = datetime.utcnow() + timedelta(seconds=max(60, expires_in - 120))
    with session_scope() as s:
        obj = s.scalar(select(OAuthToken).where(OAuthToken.provider == provider))
        if obj is None:
            obj = OAuthToken(provider=provider)
            s.add(obj)
        obj.access_token_enc = encrypt_text(access) if access else obj.access_token_enc
        obj.refresh_token_enc = encrypt_text(refresh) if refresh else obj.refresh_token_enc
        obj.expires_at = expires_at

def load_token(provider):
    with get_session() as s:
        obj = s.scalar(select(OAuthToken).where(OAuthToken.provider == provider))
        if obj is None:
            return None
        return {
            "access_token": decrypt_text(obj.access_token_enc),
            "refresh_token": decrypt_text(obj.refresh_token_enc),
            "expires_at": obj.expires_at,
        }

def valid_access_token(provider="admin"):
    token = load_token(provider)
    if not token:
        return None
    if token["expires_at"] and token["expires_at"] > datetime.utcnow():
        return token["access_token"]

    refresh = token.get("refresh_token")
    if not refresh:
        return token.get("access_token")

    if provider == "analytics" and AnalyticsOAuth().configured():
        new = AnalyticsOAuth().refresh(refresh)
    else:
        new = AdminOAuth().refresh(refresh)
    return new.get("access_token")
