from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

import requests
from sqlalchemy import select

from misharp_hero.config import (
    CAFE24_MALL_ID,
    CAFE24_CLIENT_ID,
    CAFE24_CLIENT_SECRET,
    CAFE24_REDIRECT_URI,
    CAFE24_SCOPES,
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
        return f"{self.base}/oauth/authorize?" + urlencode(
            {
                "response_type": "code",
                "client_id": CAFE24_CLIENT_ID,
                "redirect_uri": CAFE24_REDIRECT_URI,
                "scope": ",".join(parse_scopes(CAFE24_SCOPES)),
            }
        )

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
        if not r.ok:
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise RuntimeError(f"Cafe24 토큰 발급 실패 ({r.status_code}): {detail}")
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
        if not r.ok:
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise RuntimeError(f"Cafe24 토큰 갱신 실패 ({r.status_code}): {detail}")
        token = r.json()
        save_token("admin", token)
        return token


def _token_expiry(token):
    """Return a conservative UTC-naive expiry timestamp.

    Cafe24 may return both expires_in and expires_at. expires_in is preferred
    because it is timezone-independent. A safety margin is subtracted so that
    API calls never intentionally use a token near expiry.
    """
    now_utc = datetime.now(timezone.utc)

    raw_expires_in = token.get("expires_in")
    if raw_expires_in not in (None, ""):
        try:
            seconds = int(float(raw_expires_in))
            return (now_utc + timedelta(seconds=max(60, seconds - 180))).replace(tzinfo=None)
        except Exception:
            pass

    raw_expires_at = token.get("expires_at")
    if raw_expires_at:
        try:
            parsed = datetime.fromisoformat(str(raw_expires_at).replace("Z", "+00:00"))
            # Cafe24 responses can contain a timezone-less local timestamp.
            # Treat it as Korea time for this mall, then normalize to UTC.
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
            parsed = parsed.astimezone(timezone.utc) - timedelta(minutes=3)
            return parsed.replace(tzinfo=None)
        except Exception:
            pass

    # Conservative fallback. A 90-minute local lifetime guarantees a refresh
    # well before a typical two-hour token expiry.
    return (now_utc + timedelta(minutes=90)).replace(tzinfo=None)


def save_token(provider, token):
    access = token.get("access_token")
    refresh = token.get("refresh_token")
    expires_at = _token_expiry(token)

    with session_scope() as s:
        obj = s.scalar(select(OAuthToken).where(OAuthToken.provider == provider))
        if obj is None:
            obj = OAuthToken(provider=provider)
            s.add(obj)
        obj.access_token_enc = encrypt_text(access) if access else obj.access_token_enc
        # Cafe24 may rotate the refresh token. Keep the old one only when the
        # response truly omits a new value.
        obj.refresh_token_enc = encrypt_text(refresh) if refresh else obj.refresh_token_enc
        obj.expires_at = expires_at


def load_token(provider="admin"):
    with get_session() as s:
        obj = s.scalar(select(OAuthToken).where(OAuthToken.provider == provider))
        if obj is None:
            return None
        return {
            "access_token": decrypt_text(obj.access_token_enc),
            "refresh_token": decrypt_text(obj.refresh_token_enc),
            "expires_at": obj.expires_at,
        }


def valid_access_token(provider="admin", force_refresh=False):
    """Return a usable access token, refreshing automatically when needed.

    force_refresh=True is used after an API returns HTTP 401. This protects
    against clock/timezone differences or server-side early invalidation.
    """
    token = load_token(provider)
    if not token:
        return None

    refresh = token.get("refresh_token")
    if force_refresh:
        if not refresh:
            return token.get("access_token")
        new = AdminOAuth().refresh(refresh)
        return new.get("access_token")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = token.get("expires_at")
    if token.get("access_token") and expires_at and expires_at > now + timedelta(seconds=30):
        return token["access_token"]

    if refresh:
        new = AdminOAuth().refresh(refresh)
        return new.get("access_token")

    return token.get("access_token")
