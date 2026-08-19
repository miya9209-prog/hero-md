from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
import math
import pandas as pd
from misharp_hero.repository import (
    upsert_product, add_candidate, add_launch, upsert_metric48h,
    upsert_monthly_hero, add_action
)
from misharp_hero.hero_score import prelaunch_score, postlaunch_score, hero_grade, diagnose

def _blank(v):
    return pd.isna(v) or str(v).strip() == ""

def _text(v):
    return "" if _blank(v) else str(v).strip()

def _float(v):
    if _blank(v):
        return None
    try:
        return float(str(v).replace(",", "").replace("%","").strip())
    except Exception:
        return None

def _dt(v):
    if _blank(v):
        return None
    try:
        return pd.to_datetime(v).to_pydatetime()
    except Exception:
        return None

def import_md_excel(path):
    path = Path(path)
    book = pd.ExcelFile(path)
    summary = {"candidates":0, "launches":0, "heroes":0, "actions":0}

    # 1. 상품스케줄표
    if "1.상품스케줄표" in book.sheet_names:
        df = pd.read_excel(path, sheet_name="1.상품스케줄표")
        for _, r in df.iterrows():
            supplier_product_name = _text(r.iloc[1] if len(r)>1 else "")
            if not supplier_product_name:
                continue
            product_id = upsert_product({
                "supplier_product_name": supplier_product_name,
                "tentative_name": _text(r.iloc[3] if len(r)>3 else ""),
                "supply_price": _float(r.iloc[2] if len(r)>2 else None),
                "supplier_name": _text(r.iloc[6] if len(r)>6 else ""),
                "product_name": _text(r.iloc[3] if len(r)>3 else "") or supplier_product_name,
            })
            focus = _text(r.iloc[4] if len(r)>4 else "").upper() == "O"
            score = prelaunch_score(focus=focus)
            add_candidate({
                "product_id": product_id,
                "supplier_product_name": supplier_product_name,
                "tentative_name": _text(r.iloc[3] if len(r)>3 else ""),
                "exposure_plan_at": _dt(r.iloc[0] if len(r)>0 else None),
                "order_plan_at": _dt(r.iloc[7] if len(r)>7 else None),
                "supply_price": _float(r.iloc[2] if len(r)>2 else None),
                "supplier_name": _text(r.iloc[6] if len(r)>6 else ""),
                "focus_candidate": focus,
                "hero_dna": _text(r.iloc[5] if len(r)>5 else ""),
                "status": _text(r.iloc[8] if len(r)>8 else ""),
                "note": _text(r.iloc[9] if len(r)>9 else ""),
                "prelaunch_score": score,
            })
            summary["candidates"] += 1

    # 2. 주간상품체크
    sheet2 = "2.주간상품체크(제작팀공유)"
    if sheet2 in book.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet2)
        for _, r in df.iterrows():
            supplier_name = _text(r.iloc[1] if len(r)>1 else "")
            product_name = _text(r.iloc[2] if len(r)>2 else "")
            launch_at = _dt(r.iloc[3] if len(r)>3 else None)
            if not product_name or not launch_at:
                continue
            product_id = upsert_product({
                "supplier_product_name": supplier_name or None,
                "product_name": product_name,
            })
            launch_id = add_launch({
                "product_id": product_id,
                "product_name": product_name,
                "supplier_product_name": supplier_name,
                "launch_at": launch_at,
                "close_48h_at": launch_at + timedelta(hours=48),
                "hero_manual": _text(r.iloc[10] if len(r)>10 else ""),
                "review_manual": _text(r.iloc[12] if len(r)>12 else ""),
                "md_action": _text(r.iloc[11] if len(r)>11 else ""),
                "production_action": _text(r.iloc[14] if len(r)>14 else ""),
            })
            views = int(_float(r.iloc[5] if len(r)>5 else 0) or 0)
            qty = int(_float(r.iloc[6] if len(r)>6 else 0) or 0)
            revenue = float(_float(r.iloc[9] if len(r)>9 else 0) or 0)
            # 기존 엑셀은 판매건수 항목이 없어 수량으로 임시 대체. API 연동 후 정확한 판매건수로 갱신됨.
            orders = qty
            cvr = orders/views if views else 0
            metric = {
                "launch_id": launch_id,
                "product_no": None,
                "start_at": launch_at,
                "end_at": launch_at + timedelta(hours=48),
                "views": views, "order_count": orders, "qty": qty, "revenue": revenue,
                "cvr": cvr, "qty_cvr": qty/views if views else 0,
                "rpv": revenue/views if views else 0,
            }
            score = postlaunch_score(metric)
            metric["hero_score"] = score
            metric["hero_grade"] = hero_grade(score)
            metric["diagnosis"] = diagnose(views, cvr)
            upsert_metric48h(metric)
            if _text(r.iloc[11] if len(r)>11 else ""):
                add_action({
                    "product_name": product_name,
                    "issue_type": "MD 조치",
                    "action_text": _text(r.iloc[11]),
                    "team": "MD",
                    "status": "대기",
                })
                summary["actions"] += 1
            if _text(r.iloc[14] if len(r)>14 else ""):
                add_action({
                    "product_name": product_name,
                    "issue_type": "제작팀 조치",
                    "action_text": _text(r.iloc[14]),
                    "team": "제작",
                    "status": "대기",
                })
                summary["actions"] += 1
            summary["launches"] += 1

    # 3. 월별 HERO
    sheet3 = "3.월별HERO LIST"
    if sheet3 in book.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet3)
        for _, r in df.iterrows():
            month = _text(r.iloc[0] if len(r)>0 else "")
            product_name = _text(r.iloc[1] if len(r)>1 else "")
            if not month or not product_name:
                continue
            margin_rate = _float(r.iloc[7] if len(r)>7 else None)
            revenue = float(_float(r.iloc[6] if len(r)>6 else 0) or 0)
            gross_profit = revenue * margin_rate/100 if margin_rate is not None else None
            upsert_monthly_hero({
                "month": month[:7],
                "product_name": product_name,
                "supplier_product_name": _text(r.iloc[2] if len(r)>2 else ""),
                "hero_status": _text(r.iloc[4] if len(r)>4 else ""),
                "qty": int(_float(r.iloc[5] if len(r)>5 else 0) or 0),
                "revenue": revenue,
                "margin_rate": margin_rate,
                "gross_profit": gross_profit,
                "keep_status": _text(r.iloc[8] if len(r)>8 else ""),
                "note": _text(r.iloc[10] if len(r)>10 else ""),
            })
            summary["heroes"] += 1

    # 4. 주간회의의 추가논의/조치
    sheet4 = "4.MD주간회의록"
    if sheet4 in book.sheet_names:
        raw = pd.read_excel(path, sheet_name=sheet4, header=None)
        for i in range(len(raw)):
            if i < 5:
                continue
            row = raw.iloc[i].tolist()
            if len(row) < 5:
                continue
            meeting_date = _dt(row[0])
            product_name = _text(row[1])
            action = _text(row[3])
            owner = _text(row[4])
            if meeting_date and product_name and action and product_name != "경쟁사명":
                add_action({
                    "product_name": product_name,
                    "issue_type": "주간회의",
                    "action_text": action,
                    "owner": owner or None,
                    "team": "MD",
                    "status": "대기",
                    "note": _text(row[2]),
                })
                summary["actions"] += 1

    return summary
