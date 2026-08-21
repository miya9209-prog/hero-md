from __future__ import annotations
from datetime import datetime
import json
import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from misharp_hero.db import get_session, get_engine, session_scope
from misharp_hero.models import (
    Product,
    Candidate,
    Launch,
    Metric48h,
    AnalyticsProductMetric,
    InventoryCurrent,
    HeroMetricV2,
    MonthlyHero,
    ActionItem,
    SeraMetric,
    OAuthToken,
    SyncLog,
)


def df(sql, params=None):
    with get_engine().connect() as conn:
        result = conn.execute(
            text(sql),
            params or {},
        )

        rows = result.mappings().all()

        return pd.DataFrame(
            rows,
            columns=list(result.keys()),
        )


def upsert_product(data: dict):
    with session_scope() as s:
        obj = None
        product_no = str(data.get("product_no") or "").strip() or None
        if product_no:
            obj = s.scalar(select(Product).where(Product.product_no == product_no))
        if obj is None and data.get("supplier_product_name"):
            obj = s.scalar(
                select(Product).where(Product.supplier_product_name == data["supplier_product_name"])
            )
        if obj is None:
            obj = Product()
            s.add(obj)
        for k, v in data.items():
            if hasattr(obj, k) and v not in ("",):
                setattr(obj, k, v)
        s.flush()
        return obj.id


def add_candidate(data: dict):
    with session_scope() as s:
        name = data.get("supplier_product_name") or ""
        existing = s.scalar(
            select(Candidate).where(
                Candidate.supplier_product_name == name,
                Candidate.exposure_plan_at == data.get("exposure_plan_at"),
            )
        )
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


def upsert_hero_metric_v2(data: dict):
    with session_scope() as s:
        obj = s.scalar(select(HeroMetricV2).where(HeroMetricV2.launch_id == data["launch_id"]))
        if obj is None:
            obj = HeroMetricV2(launch_id=data["launch_id"], product_no=str(data["product_no"]))
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
        obj = s.scalar(
            select(MonthlyHero).where(
                MonthlyHero.month == data["month"],
                MonthlyHero.product_name == data.get("product_name", ""),
            )
        )
        if obj is None:
            obj = MonthlyHero(month=data["month"], product_name=data.get("product_name", ""))
            s.add(obj)
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        s.flush()
        return obj.id


def save_sera_rows(rows: list[dict]):
    if not rows:
        return 0
    with session_scope() as s:
        for row in rows:
            s.add(SeraMetric(**row))
    return len(rows)


def _upsert_stmt(model, rows, conflict_cols, update_cols):
    engine = get_engine()
    if engine.dialect.name == "postgresql":
        stmt = pg_insert(model).values(rows)
        return stmt.on_conflict_do_update(
            index_elements=conflict_cols,
            set_={c: getattr(stmt.excluded, c) for c in update_cols},
        )
    if engine.dialect.name == "sqlite":
        stmt = sqlite_insert(model).values(rows)
        return stmt.on_conflict_do_update(
            index_elements=conflict_cols,
            set_={c: getattr(stmt.excluded, c) for c in update_cols},
        )
    raise RuntimeError(f"지원하지 않는 DB: {engine.dialect.name}")


def upsert_analytics_daily(rows: list[dict]):
    if not rows:
        return 0
    stmt = _upsert_stmt(
        AnalyticsProductMetric,
        rows,
        ["metric_date", "product_no"],
        [
            "product_name",
            "views",
            "cart_count",
            "cart_rate",
            "order_count",
            "qty",
            "revenue",
            "raw_json",
            "collected_at",
        ],
    )
    with get_engine().begin() as conn:
        conn.execute(stmt)
    return len(rows)


def upsert_inventory_current(rows: list[dict]):
    if not rows:
        return 0
    stmt = _upsert_stmt(
        InventoryCurrent,
        rows,
        ["inventory_key"],
        [
            "product_no",
            "product_code",
            "variant_code",
            "stock_qty",
            "available_qty",
            "warehouse",
            "source",
            "raw_json",
            "captured_at",
        ],
    )
    with get_engine().begin() as conn:
        conn.execute(stmt)
    return len(rows)


def product_code_to_no_map():
    data = df("SELECT product_no, product_code FROM products WHERE product_code IS NOT NULL")
    if data.empty:
        return {}
    return {
        str(r["product_code"]).strip(): str(r["product_no"]).strip()
        for _, r in data.iterrows()
        if str(r.get("product_code") or "").strip() and str(r.get("product_no") or "").strip()
    }


def latest_inventory_by_product():
    data = df(
        "SELECT product_no, product_code, stock_qty, available_qty, captured_at "
        "FROM inventory_current"
    )
    if data.empty:
        return data
    data["stock_qty"] = pd.to_numeric(data["stock_qty"], errors="coerce").fillna(0)
    data["available_qty"] = pd.to_numeric(data["available_qty"], errors="coerce")
    grouped = data.groupby("product_no", dropna=True).agg(
        sellmate_stock_qty=("stock_qty", "sum"),
        sellmate_available_qty=("available_qty", "sum"),
        inventory_updated_at=("captured_at", "max"),
    ).reset_index()
    grouped["product_no"] = grouped["product_no"].astype(str)
    return grouped


def latest_sera_by_product():
    data = df(
        "SELECT product_no, product_code, product_name, views, orders, qty, revenue, "
        "opv, espv, click_value, report_date, imported_at FROM sera_metrics "
        "WHERE product_no IS NOT NULL"
    )
    if data.empty:
        return data
    data["product_no"] = data["product_no"].astype(str)
    data = data.sort_values("imported_at").drop_duplicates("product_no", keep="last")
    return data.rename(columns={
        "views": "sera_views",
        "orders": "sera_orders",
        "qty": "sera_qty",
        "revenue": "sera_revenue",
        "opv": "sera_opv",
        "espv": "sera_espv",
        "click_value": "sera_click_value",
        "report_date": "sera_report_date",
        "imported_at": "sera_imported_at",
    })


def analytics_period(start_date: str, end_date: str):
    data = df(
        "SELECT product_no, SUM(views) views, SUM(cart_count) cart_count, "
        "SUM(order_count) order_count, SUM(qty) qty, SUM(revenue) revenue "
        "FROM analytics_product_metrics "
        "WHERE metric_date >= :start_date AND metric_date <= :end_date "
        "GROUP BY product_no",
        {"start_date": start_date, "end_date": end_date},
    )
    if data.empty:
        return data
    data["product_no"] = data["product_no"].astype(str)
    data["cvr"] = data.apply(lambda r: (r["order_count"] / r["views"]) if r["views"] else 0, axis=1)
    data["cart_rate"] = data.apply(lambda r: (r["cart_count"] / r["views"]) if r["views"] else 0, axis=1)
    data["rpv"] = data.apply(lambda r: (r["revenue"] / r["views"]) if r["views"] else 0, axis=1)
    return data


def product_master_df(start_date: str, end_date: str, search: str = "", limit: int = 2000):
    search = (search or "").strip()
    params = {"limit": int(limit)}
    if search:
        params["q"] = f"%{search.lower()}%"
        products = df(
            "SELECT product_no, product_code, product_name, supplier_product_name, "
            "supplier_name, category, supply_price, selling_price, image_url, updated_at "
            "FROM products WHERE "
            "LOWER(COALESCE(product_name,'')) LIKE :q OR "
            "LOWER(COALESCE(product_code,'')) LIKE :q OR "
            "LOWER(COALESCE(product_no,'')) LIKE :q "
            "ORDER BY updated_at DESC LIMIT :limit",
            params,
        )
    else:
        products = df(
            "SELECT product_no, product_code, product_name, supplier_product_name, "
            "supplier_name, category, supply_price, selling_price, image_url, updated_at "
            "FROM products ORDER BY updated_at DESC LIMIT :limit",
            params,
        )

    if products.empty:
        return products
    products["product_no"] = products["product_no"].astype(str)

    analytics = analytics_period(start_date, end_date)
    if not analytics.empty:
        products = products.merge(analytics, on="product_no", how="left")

    inv = latest_inventory_by_product()
    if not inv.empty:
        products = products.merge(inv, on="product_no", how="left")

    sera = latest_sera_by_product()
    if not sera.empty:
        keep = [
            "product_no",
            "sera_views",
            "sera_orders",
            "sera_qty",
            "sera_revenue",
            "sera_opv",
            "sera_espv",
            "sera_click_value",
            "sera_report_date",
        ]
        products = products.merge(sera[keep], on="product_no", how="left")

    return products


def current_launches():
    return df(
        """
        SELECT l.*,
               COALESCE(v2.views, m.views, 0) AS views,
               COALESCE(v2.order_count, m.order_count, 0) AS order_count,
               COALESCE(v2.qty, m.qty, 0) AS qty,
               COALESCE(v2.revenue, m.revenue, 0) AS revenue,
               COALESCE(v2.cvr, m.cvr, 0) AS cvr,
               COALESCE(v2.qty_cvr, m.qty_cvr, 0) AS qty_cvr,
               COALESCE(v2.rpv, m.rpv, 0) AS rpv,
               COALESCE(v2.hero_score, m.hero_score) AS hero_score,
               COALESCE(v2.hero_grade, m.hero_grade) AS hero_grade,
               COALESCE(v2.diagnosis, m.diagnosis) AS diagnosis,
               v2.cart_count, v2.cart_rate, v2.sellmate_stock_qty,
               v2.sera_opv, v2.sera_espv, v2.sera_click_value,
               COALESCE(v2.collected_at, m.collected_at) AS collected_at
        FROM launches l
        LEFT JOIN hero_metrics_v2 v2 ON v2.launch_id = l.id
        LEFT JOIN metrics_48h m ON m.launch_id = l.id
        ORDER BY l.launch_at DESC
        """
    )


def metrics_history():
    v2 = df("SELECT * FROM hero_metrics_v2 ORDER BY end_at DESC")
    if not v2.empty:
        return v2
    return df("SELECT * FROM metrics_48h ORDER BY end_at DESC")


def candidate_df():
    return df(
        """
        SELECT c.*, p.product_no, p.product_name AS cafe24_product_name
        FROM candidates c
        LEFT JOIN products p ON p.id = c.product_id
        ORDER BY COALESCE(c.exposure_plan_at, c.created_at) DESC
        """
    )


def monthly_hero_df():
    return df(
        """
        SELECT *,
          RANK() OVER (PARTITION BY month ORDER BY revenue DESC) AS revenue_rank,
          RANK() OVER (PARTITION BY month ORDER BY COALESCE(gross_profit,0) DESC) AS profit_rank,
          RANK() OVER (PARTITION BY month ORDER BY COALESCE(margin_rate,0) DESC) AS margin_rank
        FROM monthly_heroes
        ORDER BY month DESC, revenue DESC
        """
    )


def action_df():
    return df(
        "SELECT * FROM action_items "
        "ORDER BY CASE WHEN status='완료' THEN 1 ELSE 0 END, due_at, created_at DESC"
    )


def log_sync(source, status, message=""):
    with session_scope() as s:
        s.add(SyncLog(source=source, status=status, message=message))


def sync_status_df(limit=30):
    return df(
        "SELECT source, status, message, created_at FROM sync_logs "
        "ORDER BY created_at DESC LIMIT :limit",
        {"limit": int(limit)},
    )


def count_products():
    data = df("SELECT COUNT(*) AS n FROM products")
    return int(data.iloc[0]["n"]) if not data.empty else 0
