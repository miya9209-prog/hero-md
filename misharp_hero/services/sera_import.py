from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime

import pandas as pd

from misharp_hero.repository import save_sera_rows, log_sync

ALIASES = {
    "product_no": ["상품번호", "product_no", "상품 no", "상품no", "상품 번호"],
    "product_code": ["상품코드", "product_code", "품번"],
    "product_name": ["상품명", "노출상품명", "product_name", "상품"],
    "detail_path": ["상품상세경로", "상세경로", "상품url", "상품 URL", "url", "URL"],
    "views": ["조회수", "상품조회수", "PV", "view", "views", "노출"],
    "orders": ["주문수", "판매건수", "구매건수", "order_count", "주문"],
    "qty": ["판매수량", "판매물품수", "수량", "qty"],
    "revenue": ["매출액", "판매금액", "매출", "order_amount"],
    "opv": ["OpV", "OPV", "opv"],
    "espv": ["ESpV", "ESPV", "espv"],
    "click_value": ["클릭가치", "click_value", "클릭 가치"],
}


def _norm(s):
    return re.sub(r"\s+", "", str(s or "")).lower()


def _find_col(columns, aliases):
    normmap = {_norm(c): c for c in columns}
    for a in aliases:
        if _norm(a) in normmap:
            return normmap[_norm(a)]
    for c in columns:
        nc = _norm(c)
        for a in aliases:
            na = _norm(a)
            if na and na in nc:
                return c
    return None


def _num(v, integer=False):
    try:
        if pd.isna(v):
            return None
        x = float(str(v).replace(",", "").replace("%", "").strip())
        return int(x) if integer else x
    except Exception:
        return None


def extract_product_no(value):
    text = str(value or "")
    patterns = [
        r"product_no[=/](\d+)",
        r"product_no=(\d+)",
        r"/product/[^/]+/(\d+)",
        r"/(\d{3,})(?:\?|$)",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(1)
    return None


def infer_report_date(filename):
    text = Path(filename).stem
    patterns = [
        r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})",
        r"(\d{4})(\d{2})(\d{2})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            y, mo, d = m.groups()
            return f"{y}-{mo}-{d}"
    return None


def detect_header_row(path, sheet_name=0, max_rows=20):
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=max_rows)
    keywords = ["상품", "조회", "주문", "매출", "OpV", "ESpV"]
    best_row, best_score = 0, -1
    for i, row in raw.iterrows():
        text = " ".join(str(x) for x in row.tolist() if not pd.isna(x))
        score = sum(k.lower() in text.lower() for k in keywords)
        if score > best_score:
            best_score, best_row = score, i
    return int(best_row)


def parse_sera_excel(path):
    path = Path(path)
    xls = pd.ExcelFile(path)
    rows = []
    report_date = infer_report_date(path.name)

    for sheet in xls.sheet_names:
        header = detect_header_row(path, sheet)
        data = pd.read_excel(path, sheet_name=sheet, header=header)
        if data.empty:
            continue
        cols = {k: _find_col(data.columns, aliases) for k, aliases in ALIASES.items()}
        if not (cols["product_name"] or cols["product_no"] or cols["detail_path"]):
            continue

        for _, r in data.iterrows():
            name = str(r.get(cols["product_name"], "") if cols["product_name"] else "").strip()
            no = str(r.get(cols["product_no"], "") if cols["product_no"] else "").strip()
            if no.lower() in ("nan", "none", ""):
                no = ""
            if not no and cols["detail_path"]:
                no = extract_product_no(r.get(cols["detail_path"]))
            if not name and not no:
                continue

            raw_dict = {}
            for k, v in r.to_dict().items():
                if pd.isna(v):
                    raw_dict[str(k)] = None
                elif isinstance(v, (datetime, pd.Timestamp)):
                    raw_dict[str(k)] = str(v)
                else:
                    raw_dict[str(k)] = v

            rows.append(
                {
                    "report_name": path.name,
                    "report_date": report_date,
                    "product_no": no or None,
                    "product_code": str(r.get(cols["product_code"], "")).strip() if cols["product_code"] else None,
                    "product_name": name,
                    "views": _num(r.get(cols["views"])) if cols["views"] else None,
                    "orders": _num(r.get(cols["orders"]), True) if cols["orders"] else None,
                    "qty": _num(r.get(cols["qty"]), True) if cols["qty"] else None,
                    "revenue": _num(r.get(cols["revenue"])) if cols["revenue"] else None,
                    "opv": _num(r.get(cols["opv"])) if cols["opv"] else None,
                    "espv": _num(r.get(cols["espv"])) if cols["espv"] else None,
                    "click_value": _num(r.get(cols["click_value"])) if cols["click_value"] else None,
                    "raw_json": json.dumps(raw_dict, ensure_ascii=False, default=str),
                }
            )
    return rows


def import_sera_excel(path):
    rows = parse_sera_excel(path)
    count = save_sera_rows(rows)
    log_sync("SERA", "성공", f"{Path(path).name} {count}행")
    return count
