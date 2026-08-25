from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
from zoneinfo import ZoneInfo

import requests

from misharp_hero.config import MISHARP_NEW_PRODUCT_URL
from misharp_hero.repository import (
    auto_register_exploration,
    latest_new_product_snapshot,
    log_sync,
    mark_homepage_exit,
    mark_homepage_seen,
    product_rows_for_discovery,
    save_new_product_snapshot,
)
from misharp_hero.services.cafe24_admin import sync_products_incremental


KST = ZoneInfo("Asia/Seoul")
NEW_PRODUCT_URL = (
    MISHARP_NEW_PRODUCT_URL
    or "https://misharp.co.kr/product/list.html?cate_no=541"
)

_PRODUCT_PATTERNS = [
    re.compile(r"[?&]product_no=(\d+)", re.I),
    re.compile(r"/product/[^/\"'?#]+/(\d+)(?:/|[?#\"'])", re.I),
    re.compile(r"/product/detail\.html[^\"']*?product_no=(\d+)", re.I),
]


def extract_product_nos(html: str) -> set[str]:
    text = html or ""
    found: set[str] = set()
    for pattern in _PRODUCT_PATTERNS:
        found.update(pattern.findall(text))
    return {str(x).strip() for x in found if str(x).strip()}


def _url_with_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    q["page"] = str(int(page))
    return urlunparse(parsed._replace(query=urlencode(q)))


def crawl_new_product_page(url: str | None = None, max_pages: int = 10) -> set[str]:
    """cate_no=541의 현재 노출 상품을 여러 페이지에 걸쳐 전부 수집한다."""
    base = (url or NEW_PRODUCT_URL).strip()
    if not base:
        raise RuntimeError("미샵 신상페이지 URL이 없습니다.")

    all_nos: set[str] = set()
    previous_page_set: set[str] | None = None

    for page in range(1, max(1, int(max_pages)) + 1):
        target = _url_with_page(base, page)
        r = requests.get(
            target,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MISHARP-HERO-ITEM-OS/3.3)",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
                "Cache-Control": "no-cache",
            },
            timeout=25,
        )
        r.raise_for_status()
        current = extract_product_nos(r.text)

        if not current:
            break
        # Cafe24가 마지막 페이지를 넘어가면 동일 목록을 반복하는 경우 방지
        if previous_page_set is not None and current == previous_page_set:
            break

        new_ids = current - all_nos
        if not new_ids:
            break

        all_nos.update(current)
        previous_page_set = current

    return all_nos


def _flag_true(v) -> bool:
    return str(v or "").strip().upper() in {"T", "TRUE", "Y", "YES", "1"}


def _canonical_launch_at(detected_at: datetime) -> datetime:
    """평일 낮 12시 신상 오픈을 실제 48H 시작시각으로 보정한다."""
    # 월~금, 11:30~15:00 사이 첫 감지면 당일 12:00를 출시시각으로 사용
    if detected_at.weekday() < 5:
        t = detected_at.time()
        if time(11, 30) <= t <= time(15, 0):
            return detected_at.replace(hour=12, minute=0, second=0, microsecond=0)
    return detected_at


def discover_new_products():
    """미샵 신상품 자동탐색 v2.

    출시 판정의 기준은 Cafe24 상품 생성일이 아니라
    'cate_no=541 신상페이지에 직전 스냅샷에는 없던 product_no가 새로 등장했는가'이다.

    Cafe24 API는 신규/기존 재오픈 상품 모두의 상품정보, 판매/진열 상태를 검증하는 용도로 사용한다.
    """
    now = datetime.now(KST).replace(tzinfo=None)

    # 기존 상품 재오픈도 잡아야 하므로 최근 수정상품을 넉넉히 갱신한다.
    sync_products_incremental(24 * 14)

    current = crawl_new_product_page()
    previous = latest_new_product_snapshot()

    # 첫 실행은 오탐 방지를 위해 현재 페이지를 기준선으로만 저장한다.
    if previous is None:
        save_new_product_snapshot(now, NEW_PRODUCT_URL, current, set(), set())
        mark_homepage_seen(current, now)
        msg = f"기준선 생성 · 541 현재상품 {len(current)}개 · 신규등록 0개"
        log_sync("신상품 자동탐색", "성공", msg)
        return {
            "baseline": True,
            "current": len(current),
            "added": 0,
            "removed": 0,
            "registered": 0,
        }

    previous_set = set(previous.get("product_nos") or set())
    added = current - previous_set
    removed = previous_set - current

    # 현재 노출상품 last_seen 갱신 / 이탈상품 상태 기록
    mark_homepage_seen(current, now)
    if removed:
        # API 상태를 가능한 최신으로 맞춘 뒤 이탈 사유 기록
        sync_products_incremental(24 * 14)
        mark_homepage_exit(removed, now)

    registered = 0
    skipped = []
    if added:
        rows = product_rows_for_discovery(added)
        row_map = {
            str(r.get("product_no")): r
            for _, r in rows.iterrows()
        } if not rows.empty else {}

        launch_at = _canonical_launch_at(now)
        for pno in sorted(added):
            row = row_map.get(str(pno))
            if row is None:
                skipped.append((pno, "Cafe24 상품DB 미확인"))
                continue

            # 541에 실제 노출 + Cafe24 API에서 판매/진열중인 경우만 출시 확정
            if not _flag_true(row.get("display")) or not _flag_true(row.get("selling")):
                skipped.append((pno, "Cafe24 판매/진열 상태 미확인"))
                continue

            result = auto_register_exploration(
                pno,
                detected_at=now,
                source="541 신상페이지 신규등장 + Cafe24 API 확인",
                homepage_seen_at=now,
                launch_at=launch_at,
            )
            if result.get("created"):
                registered += 1
            else:
                skipped.append((pno, result.get("reason") or "기존 관찰"))

    save_new_product_snapshot(now, NEW_PRODUCT_URL, current, added, removed)

    msg = (
        f"541 현재 {len(current)}개 · 신규등장 {len(added)}개 · "
        f"상품탐색 등록 {registered}개 · 페이지이탈 {len(removed)}개"
    )
    if skipped:
        msg += " · 미등록 " + ", ".join(f"{p}:{reason}" for p, reason in skipped[:10])
    log_sync("신상품 자동탐색", "성공", msg)

    return {
        "baseline": False,
        "current": len(current),
        "added": len(added),
        "removed": len(removed),
        "registered": registered,
        "skipped": skipped,
        "added_product_nos": sorted(added),
        "removed_product_nos": sorted(removed),
    }
