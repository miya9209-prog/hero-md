from __future__ import annotations

import re
from datetime import datetime, time
from difflib import SequenceMatcher
from html.parser import HTMLParser
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
    new_product_baseline_for_day,
    product_rows_for_discovery,
    save_new_product_snapshot,
)
from misharp_hero.services.cafe24_admin import sync_products_incremental


KST = ZoneInfo("Asia/Seoul")
NEW_PRODUCT_URL = (
    MISHARP_NEW_PRODUCT_URL
    or "https://misharp.co.kr/product/list.html?cate_no=541"
)

_ANCHOR_ID_RE = re.compile(r"anchorBoxId_(\d+)", re.I)
_TOTAL_RE = re.compile(r"TOTAL\s*:\s*([0-9,]+)", re.I)


class _Cafe24ProductGridParser(HTMLParser):
    """실제 Cafe24 상품그리드(prdList)의 li#anchorBoxId_상품번호만 순서대로 읽는다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._prd_depth = 0
        self.ordered = []
        self._seen = set()
        self.text_parts = []

    @staticmethod
    def _classes(attrs):
        raw = dict(attrs).get("class", "") or ""
        return {x.strip() for x in raw.split() if x.strip()}

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        classes = self._classes(attrs)

        if tag.lower() in {"ul", "ol"} and any("prdList" in c for c in classes):
            self._prd_depth += 1
            return

        if self._prd_depth and tag.lower() in {"ul", "ol"}:
            self._prd_depth += 1

        if self._prd_depth and tag.lower() == "li":
            raw_id = attrs_d.get("id", "") or ""
            m = _ANCHOR_ID_RE.search(raw_id)
            if m:
                pno = m.group(1)
                if pno not in self._seen:
                    self.ordered.append(pno)
                    self._seen.add(pno)

    def handle_endtag(self, tag):
        if self._prd_depth and tag.lower() in {"ul", "ol"}:
            self._prd_depth -= 1

    def handle_data(self, data):
        if data:
            self.text_parts.append(data)


def parse_product_grid(html: str):
    parser = _Cafe24ProductGridParser()
    parser.feed(html or "")
    ordered = parser.ordered

    if not ordered:
        seen = set()
        for pno in _ANCHOR_ID_RE.findall(html or ""):
            if pno not in seen:
                ordered.append(pno)
                seen.add(pno)

    text = " ".join(parser.text_parts)
    m = _TOTAL_RE.search(text)
    reported_total = int(m.group(1).replace(",", "")) if m else None
    return ordered, reported_total


def _url_with_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    q["page"] = str(int(page))
    return urlunparse(parsed._replace(query=urlencode(q)))


def crawl_new_product_page(url: str | None = None, max_pages: int = 20):
    base = (url or NEW_PRODUCT_URL).strip()
    if not base:
        raise RuntimeError("미샵 신상페이지 URL이 없습니다.")

    all_ordered = []
    seen = set()
    reported_total = None
    pages = 0

    for page in range(1, max(1, int(max_pages)) + 1):
        target = _url_with_page(base, page)
        r = requests.get(
            target,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MISHARP-HERO-ITEM-OS/4.0)",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
                "Cache-Control": "no-cache",
            },
            timeout=25,
        )
        r.raise_for_status()
        page_ordered, page_total = parse_product_grid(r.text)
        if page == 1:
            reported_total = page_total

        if not page_ordered:
            break

        new_count = 0
        for pno in page_ordered:
            if pno not in seen:
                all_ordered.append(pno)
                seen.add(pno)
                new_count += 1

        if new_count == 0:
            break
        pages += 1

        if reported_total is not None and len(all_ordered) >= reported_total:
            break

    if reported_total is not None and len(all_ordered) != reported_total:
        raise RuntimeError(
            f"신상페이지 상품수 불일치: 화면 TOTAL {reported_total}개 / "
            f"실제 상품그리드 인식 {len(all_ordered)}개. 자동등록 중지."
        )

    if not all_ordered:
        raise RuntimeError("신상페이지 실제 상품그리드를 인식하지 못했습니다.")

    return {
        "ordered": all_ordered,
        "reported_total": reported_total,
        "pages": pages,
    }


def detect_top_open_block(baseline_ordered, current_ordered, min_anchor_size: int = 5, max_open: int = 40):
    baseline = [str(x) for x in baseline_ordered or []]
    current = [str(x) for x in current_ordered or []]
    if not baseline or not current:
        return [], "기준순서 없음"

    matcher = SequenceMatcher(a=baseline, b=current, autojunk=False)
    blocks = [b for b in matcher.get_matching_blocks() if b.size >= max(3, int(min_anchor_size))]
    if not blocks:
        return [], "안정 정렬구간 없음"

    anchor = min(blocks, key=lambda b: (b.b, -b.size))
    promoted = current[: anchor.b]

    if len(promoted) > int(max_open):
        return [], f"상단변화 {len(promoted)}개로 과다"

    return promoted, f"안정구간 {anchor.size}개 / 상단변화 {len(promoted)}개"


def _flag_true(v) -> bool:
    return str(v or "").strip().upper() in {"T", "TRUE", "Y", "YES", "1"}


def _in_launch_window(now: datetime) -> bool:
    return now.weekday() < 5 and time(11, 50) <= now.time() <= time(16, 0)


def _canonical_launch_at(detected_at: datetime) -> datetime:
    if detected_at.weekday() < 5 and time(11, 50) <= detected_at.time() <= time(16, 0):
        return detected_at.replace(hour=12, minute=0, second=0, microsecond=0)
    return detected_at


def discover_new_products():
    now = datetime.now(KST).replace(tzinfo=None)

    # 매 30분 14일치 대신 최근 72시간만 갱신
    sync_products_incremental(72)

    crawl = crawl_new_product_page()
    current_ordered = crawl["ordered"]
    current_set = set(current_ordered)
    reported_total = crawl["reported_total"]

    previous = latest_new_product_snapshot()
    removed = [
        p for p in (previous.get("ordered_product_nos") or [])
        if p not in current_set
    ] if previous else []

    mark_homepage_seen(current_set, now)
    if removed:
        mark_homepage_exit(set(removed), now)

    baseline = new_product_baseline_for_day(now.date())
    opened = []
    detection_note = ""

    if _in_launch_window(now) and baseline:
        opened, detection_note = detect_top_open_block(
            baseline.get("ordered_product_nos") or [],
            current_ordered,
        )
    elif _in_launch_window(now) and not baseline:
        detection_note = "정오 전 v4 기준선 없음 · 오늘 자동등록 보류"
    else:
        detection_note = "출시 감시시간 외 · 순서 스냅샷만 저장"

    registered = 0
    skipped = []

    if opened:
        rows = product_rows_for_discovery(set(opened))
        row_map = {
            str(r.get("product_no")): r
            for _, r in rows.iterrows()
        } if not rows.empty else {}

        launch_at = _canonical_launch_at(now)
        for pno in opened:
            row = row_map.get(str(pno))
            if row is None:
                skipped.append((pno, "Cafe24 상품DB 미확인"))
                continue
            if not _flag_true(row.get("display")) or not _flag_true(row.get("selling")):
                skipped.append((pno, "Cafe24 판매/진열 상태 미확인"))
                continue

            result = auto_register_exploration(
                pno,
                detected_at=now,
                source="신상 상단 신규오픈 + Cafe24 API 확인",
                homepage_seen_at=now,
                launch_at=launch_at,
            )
            if result.get("created"):
                registered += 1
            else:
                skipped.append((pno, result.get("reason") or "기존 관찰"))

    save_new_product_snapshot(
        now,
        NEW_PRODUCT_URL,
        current_ordered,
        opened,
        removed,
    )

    total_text = reported_total if reported_total is not None else len(current_ordered)
    msg = (
        f"신상 현재 {len(current_ordered)}개(화면 TOTAL {total_text}) · "
        f"오늘 상단 신규오픈 {len(opened)}개 · 상품탐색 등록 {registered}개 · "
        f"페이지이탈 {len(removed)}개 · {detection_note}"
    )
    if skipped:
        msg += " · 미등록 " + ", ".join(f"{p}:{reason}" for p, reason in skipped[:10])
    log_sync("신상품 자동탐색", "성공", msg)

    return {
        "current": len(current_ordered),
        "reported_total": reported_total,
        "opened": len(opened),
        "removed": len(removed),
        "registered": registered,
        "detection_note": detection_note,
        "opened_product_nos": opened,
        "removed_product_nos": removed,
        "skipped": skipped,
    }
