from __future__ import annotations

import json
from datetime import datetime, timezone

import requests

from misharp_hero.config import (
    SELLMATE_ENABLED,
    SELLMATE_API_BASE_URL,
    SELLMATE_API_TOKEN,
    SELLMATE_INVENTORY_PATH,
    SELLMATE_INVENTORY_METHOD,
    SELLMATE_AUTH_HEADER,
    SELLMATE_AUTH_PREFIX,
    SELLMATE_PAGE_MODE,
    SELLMATE_PAGE_PARAM,
    SELLMATE_OFFSET_PARAM,
    SELLMATE_PAGE_SIZE_PARAM,
    SELLMATE_PAGE_SIZE,
    SELLMATE_RESPONSE_LIST_KEY,
    SELLMATE_EXTRA_PARAMS,
    SELLMATE_PRODUCT_NO_FIELD,
    SELLMATE_PRODUCT_CODE_FIELD,
    SELLMATE_VARIANT_CODE_FIELD,
    SELLMATE_STOCK_FIELD,
    SELLMATE_AVAILABLE_FIELD,
    SELLMATE_WAREHOUSE_FIELD,
)
from misharp_hero.repository import (
    product_code_to_no_map,
    upsert_inventory_current,
    log_sync,
)


def _nested(payload, dotted_key):
    cur = payload
    for part in str(dotted_key or "").split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _int(v):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return 0


class SellmateClient:
    """
    셀메이트 공개 웹에는 Developer Portal/API 신청 안내는 확인되지만,
    고객별 발급 API의 엔드포인트/필드 스펙은 발급 문서를 기준으로 해야 한다.
    그래서 코드에 임의 URL을 박지 않고 Secrets 설정으로 주입한다.
    """

    def configured(self):
        return bool(
            SELLMATE_ENABLED
            and SELLMATE_API_BASE_URL
            and SELLMATE_INVENTORY_PATH
            and SELLMATE_API_TOKEN
        )

    def headers(self):
        if not self.configured():
            raise RuntimeError("Sellmate API 설정이 완료되지 않았습니다.")
        value = SELLMATE_API_TOKEN
        if SELLMATE_AUTH_PREFIX:
            value = f"{SELLMATE_AUTH_PREFIX} {value}".strip()
        return {SELLMATE_AUTH_HEADER: value, "Accept": "application/json"}

    def _request(self, params):
        url = SELLMATE_API_BASE_URL.rstrip("/") + "/" + SELLMATE_INVENTORY_PATH.lstrip("/")
        method = SELLMATE_INVENTORY_METHOD.upper()
        if method == "GET":
            r = requests.get(url, headers=self.headers(), params=params, timeout=60)
        else:
            r = requests.request(method, url, headers=self.headers(), json=params, timeout=60)
        if not r.ok:
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise RuntimeError(f"Sellmate API 실패 {r.status_code}: {detail}")
        return r.json()

    def inventory_rows(self, max_pages=1000):
        rows = []
        size = max(1, int(SELLMATE_PAGE_SIZE))
        for page_idx in range(max_pages):
            params = dict(SELLMATE_EXTRA_PARAMS or {})
            if SELLMATE_PAGE_MODE == "page":
                params[SELLMATE_PAGE_PARAM] = page_idx + 1
                params[SELLMATE_PAGE_SIZE_PARAM] = size
            elif SELLMATE_PAGE_MODE == "offset":
                params[SELLMATE_OFFSET_PARAM] = page_idx * size
                params[SELLMATE_PAGE_SIZE_PARAM] = size
            payload = self._request(params)
            part = _nested(payload, SELLMATE_RESPONSE_LIST_KEY)
            if part is None and isinstance(payload, list):
                part = payload
            if not isinstance(part, list):
                raise RuntimeError(
                    "Sellmate 응답에서 재고 목록을 찾지 못했습니다. "
                    "SELLMATE_RESPONSE_LIST_KEY를 발급 문서에 맞게 설정하세요."
                )
            rows.extend(part)
            if SELLMATE_PAGE_MODE == "none" or len(part) < size:
                break
        return rows


def normalize_inventory(raw, code_to_no):
    product_no = str(raw.get(SELLMATE_PRODUCT_NO_FIELD) or "").strip() or None
    product_code = str(raw.get(SELLMATE_PRODUCT_CODE_FIELD) or "").strip() or None
    variant_code = str(raw.get(SELLMATE_VARIANT_CODE_FIELD) or "").strip() or None
    if not product_no and product_code:
        product_no = code_to_no.get(product_code)
    inventory_key = variant_code or product_code or (f"product_no:{product_no}" if product_no else None)
    if not inventory_key:
        return None
    available_raw = raw.get(SELLMATE_AVAILABLE_FIELD)
    return {
        "inventory_key": inventory_key,
        "product_no": product_no,
        "product_code": product_code,
        "variant_code": variant_code,
        "stock_qty": _int(raw.get(SELLMATE_STOCK_FIELD)),
        "available_qty": None if available_raw in (None, "") else _int(available_raw),
        "warehouse": str(raw.get(SELLMATE_WAREHOUSE_FIELD) or "").strip() or None,
        "source": "sellmate",
        "raw_json": json.dumps(raw, ensure_ascii=False, default=str),
        "captured_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }


def sync_inventory():
    client = SellmateClient()
    raw_rows = client.inventory_rows()
    code_to_no = product_code_to_no_map()
    rows = []
    for raw in raw_rows:
        item = normalize_inventory(raw, code_to_no)
        if item:
            rows.append(item)
    count = upsert_inventory_current(rows)
    mapped = sum(1 for r in rows if r.get("product_no"))
    log_sync("Sellmate 재고", "성공", f"{count} SKU · Cafe24 매핑 {mapped}건")
    return count, mapped
