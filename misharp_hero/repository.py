from __future__ import annotations
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import select, delete
from misharp_hero.db import get_session, get_engine, session_scope
from misharp_hero.models import (
    Product, Candidate, Launch, Metric48h, MonthlyHero, ActionItem,
    SeraMetric, OAuthToken, SyncLog
)

def df(sql, params=None):
    return pd.read_sql(sql, get_engine(), params=params or {})

def upsert_product(data: dict):
    with session_scope() as s:
        obj = None
        product_no = str(data.get("product_no") or "").strip() or None
        if product_no:
            obj = s.scalar(select(Product).where(Product.product_no == product_no))
        if obj is None and data.get("supplier_product_name"):
            obj = s.scalar(select(Product).where(
                Product.supplier_product_name == data["supplier_product_name"]
            ))
        if obj is None:
            obj = Product()
            s.add(obj)
        for k, v in data.items():
            if hasattr(obj, k) and v not in ("",):
                setattr(obj, k, v)
        s.flush()
        return obj.id

def find_product_by_supplier_name(name: str):
    if not name:
        return None
    with get_session() as s:
        return s.scalar(select(Product).where(Product.supplier_product_name == name))

def add_candidate(data: dict):
    with session_scope() as s:
        name = data.get("supplier_product_name") or ""
        existing = s.scalar(select(Candidate).where(
            Candidate.supplier_product_name == name,
            Candidate.exposure_plan_at == data.get("exposure_plan_at"),
        ))
        obj = existing or Candidate(supplier_product_name=name)
        if not existing:
            s.add(obj)
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        s.flush()
        return obj.id

def add_launch(data: dict):
    with session_scope() as s:
        q = select(Launch).where(
            Launch.product_name == data.get("product_name", ""),
            Launch.launch_at == data["launch_at"],
        )
        obj = s.scalar(q)
        if obj is None:
            obj = Launch()
            s.add(obj)
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        s.flush()
        return obj.id

def upsert_metric48h(data: dict):
    with session_scope() as s:
        obj = s.scalar(select(Metric48h).where(Metric48h.launch_id == data["launch_id"]))
        if obj is None:
            obj = Metric48h(launch_id=data["launch_id"])
            s.add(obj)
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        s.flush()
        return obj.id

def add_action(data: dict):
    with session_scope() as s:
        obj = ActionItem(**data)
        s.add(obj)
        s.flush()
        return obj.id

def upsert_monthly_hero(data: dict):
    with session_scope() as s:
        obj = s.scalar(select(MonthlyHero).where(
            MonthlyHero.month == data["month"],
            MonthlyHero.product_name == data.get("product_name", ""),
        ))
        if obj is None:
            obj = MonthlyHero(month=data["month"], product_name=data.get("product_name", ""))
            s.add(obj)
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        s.flush()
        return obj.id

def save_sera_rows(rows: list[dict]):
    with session_scope() as s:
        for row in rows:
            s.add(SeraMetric(**row))

def log_sync(source, status, message=""):
    with session_scope() as s:
        s.add(SyncLog(source=source, status=status, message=message))

def current_launches():
    return df("""
    SELECT l.*,
           m.views, m.order_count, m.qty, m.revenue, m.cvr, m.qty_cvr, m.rpv,
           m.hero_score, m.hero_grade, m.diagnosis, m.collected_at
    FROM launches l
    LEFT JOIN metrics_48h m ON m.launch_id = l.id
    ORDER BY l.launch_at DESC
    """)

def metrics_history():
    return df("SELECT * FROM metrics_48h ORDER BY end_at DESC")

def candidate_df():
    return df("""
    SELECT c.*, p.product_no, p.product_name AS cafe24_product_name
    FROM candidates c
    LEFT JOIN products p ON p.id = c.product_id
    ORDER BY COALESCE(c.exposure_plan_at, c.created_at) DESC
    """)

def monthly_hero_df():
    return df("""
    SELECT *,
      RANK() OVER (PARTITION BY month ORDER BY revenue DESC) AS revenue_rank,
      RANK() OVER (PARTITION BY month ORDER BY COALESCE(gross_profit,0) DESC) AS profit_rank,
      RANK() OVER (PARTITION BY month ORDER BY COALESCE(margin_rate,0) DESC) AS margin_rank
    FROM monthly_heroes
    ORDER BY month DESC, revenue DESC
    """)

def action_df():
    return df("SELECT * FROM action_items ORDER BY CASE WHEN status='완료' THEN 1 ELSE 0 END, due_at, created_at DESC")
