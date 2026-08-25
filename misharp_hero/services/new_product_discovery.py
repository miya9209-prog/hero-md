from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests

from misharp_hero.config import (
    MISHARP_HOME_URL,
    MISHARP_NEW_PRODUCT_URL,
    NEW_PRODUCT_DISCOVERY_LOOKBACK_HOURS,
    HOME_CRAWL_MAX_AGE_DAYS,
)
from misharp_hero.repository import (
    auto_register_exploration,
    log_sync,
    recent_products_for_discovery,
)
from misharp_hero.services.cafe24_admin import sync_products_incremental


KST = ZoneInfo("Asia/Seoul")


_PRODUCT_PATTERNS = [
    re.compile(r"[?&]product_no=(\d+)", re.I),
    re.compile(r"/product/[^/\"'?#]+/(\d+)(?:/|[?#\"'])", re.I),
    re.compile(r"/product/detail\.html[^\"']*?product_no=(\d+)", re.I),
]


def extract_product_nos(html: str) -> set[str]:
    """Cafe24 상품 URL에서 product_no를 추출한다."""
    text = html or ""
    found: set[str] = set()
    for pattern in _PRODUCT_PATTERNS:
        found.update(pattern.findall(text))
    return {str(x).strip() for x in found if str(x).strip()}


def crawl_homepage_product_nos(url: str | None = None) -> set[str]:
    """홈페이지/신상품 페이지에 실제 노출된 product_no를 보조 확인한다.

    크롤링은 보조 신호이며 실패해도 Cafe24 API 자동탐색은 계속 동작한다.
    """
    target = (url or MISHARP_NEW_PRODUCT_URL or MISHARP_HOME_URL or "").strip()
    if not target:
        return set()

    r = requests.get(
        target,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MISHARP-HERO-ITEM-OS/3.0)",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        },
        timeout=25,
    )
    r.raise_for_status()
    return extract_product_nos(r.text)


def discover_new_products(lookback_hours: int | None = None):
    """신상품 자동탐색.

    1) Cafe24 최근 상품정보를 갱신한다.
    2) 최근 등록 + 판매중 + 진열중 상품을 후보로 잡는다.
    3) 홈페이지 크롤링 결과는 '실제 노출 확인' 보조 신호로 사용한다.
    4) 새 상품은 상품 탐색에 자동 등록하고 그 시각부터 48H 관찰을 시작한다.

    중요한 원칙:
    - 홈페이지 크롤링만으로 자동등록하지 않는다. 과거 인기상품/기획전 노출 오탐을 막기 위해
      반드시 최근 Cafe24 등록상품 조건과 교차한다.
    - 탐색 주기는 30분을 권장한다. '매일 자동탐색' 요구를 충족하면서 48H 시작 오차도 줄인다.
    """
    hours = int(lookback_hours or NEW_PRODUCT_DISCOVERY_LOOKBACK_HOURS or 72)
    now = datetime.now(KST).replace(tzinfo=None)
    cutoff = now - timedelta(hours=hours)

    # API DB 최신화. 실패하면 탐색 전체를 실패시켜 로그에서 바로 알 수 있게 한다.
    sync_products_incremental(max(hours, 48))

    homepage_nos: set[str] = set()
    homepage_error = None
    try:
        homepage_nos = crawl_homepage_product_nos()
    except Exception as e:
        homepage_error = str(e)

    candidates = recent_products_for_discovery(cutoff)
    if candidates.empty:
        msg = "신상품 후보 0개"
        if homepage_error:
            msg += f" · 홈페이지 확인 실패(보조): {homepage_error[:120]}"
        log_sync("신상품 자동탐색", "성공", msg)
        return {"candidates": 0, "registered": 0, "homepage_seen": 0}

    max_age_cutoff = now - timedelta(days=int(HOME_CRAWL_MAX_AGE_DAYS or 14))
    registered = 0
    homepage_seen_count = 0

    for _, row in candidates.iterrows():
        pno = str(row.get("product_no") or "").strip()
        if not pno:
            continue

        created_at = row.get("cafe24_created_at")
        if created_at is not None:
            try:
                created_at = created_at.to_pydatetime() if hasattr(created_at, "to_pydatetime") else created_at
            except Exception:
                created_at = None

        on_homepage = pno in homepage_nos
        if on_homepage:
            homepage_seen_count += 1

        # 홈페이지에 오래된 기획상품이 노출되는 경우를 막기 위한 안전장치.
        if on_homepage and created_at and created_at < max_age_cutoff:
            continue

        source = "Cafe24 API + 홈페이지" if on_homepage else "Cafe24 API"
        result = auto_register_exploration(
            pno,
            detected_at=now,
            source=source,
            homepage_seen_at=now if on_homepage else None,
        )
        if result.get("created"):
            registered += 1

    msg = f"후보 {len(candidates)}개 · 신규등록 {registered}개 · 홈페이지확인 {homepage_seen_count}개"
    if homepage_error:
        msg += f" · 홈페이지 확인 실패(보조): {homepage_error[:120]}"
    log_sync("신상품 자동탐색", "성공", msg)
    return {
        "candidates": int(len(candidates)),
        "registered": int(registered),
        "homepage_seen": int(homepage_seen_count),
        "homepage_error": homepage_error,
    }
