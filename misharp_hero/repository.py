from __future__ import annotations
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import bindparam, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from misharp_hero.db import get_engine, session_scope
from misharp_hero.models import (
    Product,
    ProductMD,
    Candidate,
    Launch,
    Metric48h,
    AnalyticsProductMetric,
    InventoryCurrent,
    HeroMetricV2,
    MonthlyHero,
    ActionItem,
    SeraMetric,
    SyncLog,
)


def df(sql, params=None):
    return pd.read_sql(text(sql), get_engine(), params=params or {})


def _df_in(sql: str, values: list[str], params=None):
    if not values:
        return pd.DataFrame()
    stmt = text(sql).bindparams(bindparam("product_nos", expanding=True))
    payload = dict(params or {})
    payload["product_nos"] = [str(v) for v in values]
    return pd.read_sql(stmt, get_engine(), params=payload)


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
        product_no = str(data.get("product_no") or "").strip() or None
        if product_no:
            q = select(Launch).where(
                Launch.product_no == product_no,
                Launch.launch_at == data["launch_at"],
            )
        else:
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


def get_product_md(product_no: str):
    data = df(
        "SELECT * FROM product_md WHERE product_no=:product_no LIMIT 1",
        {"product_no": str(product_no)},
    )
    if data.empty:
        return {}
    return data.iloc[0].to_dict()


def save_product_md(product_no: str, data: dict):
    """MD 운영정보 저장 + HERO 관찰 ON이면 해당 상품의 48H Launch를 자동 생성/갱신."""
    product_no = str(product_no).strip()
    if not product_no:
        raise ValueError("product_no가 필요합니다.")

    with session_scope() as s:
        product = s.scalar(select(Product).where(Product.product_no == product_no))
        if product is None:
            raise ValueError(f"상품번호 {product_no}를 상품 마스터에서 찾을 수 없습니다.")

        obj = s.scalar(select(ProductMD).where(ProductMD.product_no == product_no))
        if obj is None:
            obj = ProductMD(product_no=product_no)
            s.add(obj)

        for k in [
            "hero_watch",
            "launch_at",
            "sale_end_at",
            "season",
            "sourcing_type",
            "md_owner",
            "md_note",
        ]:
            if k in data:
                setattr(obj, k, data[k])

        launch = None
        launch_at = data.get("launch_at", obj.launch_at)
        hero_watch = bool(data.get("hero_watch", obj.hero_watch))
        if hero_watch and launch_at:
            if obj.launch_id:
                launch = s.get(Launch, obj.launch_id)
            if launch is None:
                launch = s.scalar(
                    select(Launch).where(
                        Launch.product_no == product_no,
                        Launch.launch_at == launch_at,
                    )
                )
            if launch is None:
                launch = Launch()
                s.add(launch)
            elif launch.launch_at and launch.launch_at != launch_at:
                # 출시시각이 바뀌면 이전 시간창의 점수/지표는 더 이상 유효하지 않다.
                old_v2 = s.scalar(select(HeroMetricV2).where(HeroMetricV2.launch_id == launch.id))
                old_v1 = s.scalar(select(Metric48h).where(Metric48h.launch_id == launch.id))
                if old_v2 is not None:
                    s.delete(old_v2)
                if old_v1 is not None:
                    s.delete(old_v1)

            launch.product_id = product.id
            launch.product_no = product_no
            launch.product_name = product.product_name or ""
            launch.supplier_product_name = product.supplier_product_name
            launch.launch_at = launch_at
            launch.close_48h_at = launch_at + timedelta(hours=48)
            # 관찰종료 상품을 상품마스터에서 다시 ON 하면 사후관찰로 재개한다.
            if launch.review_manual == "관찰종료":
                launch.review_manual = "유지관찰"
            s.flush()
            obj.launch_id = launch.id

        obj.updated_at = datetime.utcnow()
        s.flush()
        return {"product_md_id": obj.id, "launch_id": obj.launch_id}


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


def latest_inventory_by_product(product_nos: list[str] | None = None):
    if product_nos:
        data = _df_in(
            "SELECT product_no, product_code, stock_qty, available_qty, captured_at "
            "FROM inventory_current WHERE product_no IN :product_nos",
            product_nos,
        )
    else:
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


def latest_sera_by_product(product_nos: list[str] | None = None):
    base = (
        "SELECT product_no, product_code, product_name, views, orders, qty, revenue, "
        "opv, espv, click_value, report_date, imported_at FROM sera_metrics "
        "WHERE product_no IS NOT NULL"
    )
    if product_nos:
        data = _df_in(base + " AND product_no IN :product_nos", product_nos)
    else:
        data = df(base)
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


def analytics_period(start_date: str, end_date: str, product_nos: list[str] | None = None):
    base = (
        "SELECT product_no, SUM(views) views, SUM(cart_count) cart_count, "
        "SUM(order_count) order_count, SUM(qty) qty, SUM(revenue) revenue "
        "FROM analytics_product_metrics "
        "WHERE metric_date >= :start_date AND metric_date <= :end_date"
    )
    params = {"start_date": start_date, "end_date": end_date}
    if product_nos:
        data = _df_in(base + " AND product_no IN :product_nos GROUP BY product_no", product_nos, params)
    else:
        data = df(base + " GROUP BY product_no", params)
    if data.empty:
        return data
    data["product_no"] = data["product_no"].astype(str)
    data["cvr"] = data.apply(lambda r: (r["order_count"] / r["views"]) if r["views"] else 0, axis=1)
    data["cart_rate"] = data.apply(lambda r: (r["cart_count"] / r["views"]) if r["views"] else 0, axis=1)
    data["rpv"] = data.apply(lambda r: (r["revenue"] / r["views"]) if r["views"] else 0, axis=1)
    return data


def _product_master_where(filters: dict | None = None):
    filters = filters or {}
    where = ["p.product_no IS NOT NULL"]
    params = {}

    search = str(filters.get("search") or "").strip().lower()
    if search:
        where.append(
            "(LOWER(COALESCE(p.product_name,'')) LIKE :q OR "
            "LOWER(COALESCE(p.product_code,'')) LIKE :q OR "
            "LOWER(COALESCE(p.product_no,'')) LIKE :q)"
        )
        params["q"] = f"%{search}%"

    for key, col in [
        ("selling", "p.selling"),
        ("display", "p.display"),
        ("category", "p.category"),
        ("season", "pm.season"),
        ("sourcing_type", "pm.sourcing_type"),
    ]:
        val = filters.get(key)
        if val not in (None, "", "전체"):
            where.append(f"{col} = :{key}")
            params[key] = val

    hero_watch = filters.get("hero_watch")
    if hero_watch in (True, False):
        where.append("COALESCE(pm.hero_watch, FALSE) = :hero_watch")
        params["hero_watch"] = bool(hero_watch)

    return " AND ".join(where), params


def product_master_filter_values():
    def vals(sql, col):
        x = df(sql)
        if x.empty:
            return []
        return [str(v) for v in x[col].dropna().tolist() if str(v).strip()]

    return {
        "categories": vals(
            "SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category<>'' ORDER BY category",
            "category",
        ),
        "seasons": vals(
            "SELECT DISTINCT season FROM product_md WHERE season IS NOT NULL AND season<>'' ORDER BY season",
            "season",
        ),
        "sourcing_types": vals(
            "SELECT DISTINCT sourcing_type FROM product_md WHERE sourcing_type IS NOT NULL AND sourcing_type<>'' ORDER BY sourcing_type",
            "sourcing_type",
        ),
    }


def count_product_master(filters: dict | None = None):
    where, params = _product_master_where(filters)
    data = df(
        f"SELECT COUNT(*) AS n FROM products p LEFT JOIN product_md pm ON pm.product_no=p.product_no WHERE {where}",
        params,
    )
    return int(data.iloc[0]["n"]) if not data.empty else 0


def count_hero_watch():
    data = df("SELECT COUNT(*) AS n FROM product_md WHERE hero_watch=TRUE")
    return int(data.iloc[0]["n"]) if not data.empty else 0


def product_master_page(
    start_date: str,
    end_date: str,
    filters: dict | None = None,
    page: int = 1,
    page_size: int = 100,
):
    where, params = _product_master_where(filters)
    page = max(1, int(page))
    page_size = max(20, min(int(page_size), 500))
    params.update({"limit": page_size, "offset": (page - 1) * page_size})

    products = df(
        f"""
        SELECT p.id, p.product_no, p.product_code, p.product_name,
               p.supplier_product_name, p.supplier_name, p.category,
               p.supply_price, p.selling_price, p.retail_price,
               p.display, p.selling, p.image_url,
               p.cafe24_created_at, p.cafe24_updated_at, p.updated_at,
               COALESCE(pm.hero_watch, FALSE) AS hero_watch,
               pm.launch_at, pm.sale_end_at, pm.season, pm.sourcing_type,
               pm.md_owner, pm.md_note, pm.launch_id,
               l.close_48h_at,
               COALESCE(v2.hero_score, m.hero_score) AS hero_score,
               COALESCE(v2.hero_grade, m.hero_grade) AS hero_grade,
               COALESCE(v2.diagnosis, m.diagnosis) AS diagnosis
        FROM products p
        LEFT JOIN product_md pm ON pm.product_no = p.product_no
        LEFT JOIN launches l ON l.id = pm.launch_id
        LEFT JOIN hero_metrics_v2 v2 ON v2.launch_id = pm.launch_id
        LEFT JOIN metrics_48h m ON m.launch_id = pm.launch_id
        WHERE {where}
        ORDER BY COALESCE(p.cafe24_updated_at, p.updated_at) DESC, p.id DESC
        LIMIT :limit OFFSET :offset
        """,
        params,
    )
    if products.empty:
        return products

    products["product_no"] = products["product_no"].astype(str)
    product_nos = products["product_no"].tolist()

    analytics = analytics_period(start_date, end_date, product_nos)
    if not analytics.empty:
        products = products.merge(analytics, on="product_no", how="left")

    inv = latest_inventory_by_product(product_nos)
    if not inv.empty:
        products = products.merge(inv, on="product_no", how="left")

    sera = latest_sera_by_product(product_nos)
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


def product_master_df(start_date: str, end_date: str, search: str = "", limit: int = 2000):
    """기존 호출 호환용. 신규 UI는 product_master_page를 사용한다."""
    return product_master_page(
        start_date,
        end_date,
        filters={"search": search},
        page=1,
        page_size=min(int(limit), 500),
    )


def current_launches(only_observed: bool = False):
    where = "WHERE pm.hero_watch=TRUE" if only_observed else ""
    return df(
        f"""
        SELECT l.*,
               COALESCE(pm.hero_watch, FALSE) AS hero_watch,
               pm.season, pm.sourcing_type, pm.md_owner,
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
               v2.cart_count, v2.cart_rate,
               v2.return_order_count, v2.return_qty, v2.return_rate, v2.return_collected_at,
               l.review_manual AS md_followup, l.md_action AS md_followup_note,
               COALESCE(v2.collected_at, m.collected_at) AS collected_at
        FROM launches l
        LEFT JOIN product_md pm ON pm.launch_id = l.id
        LEFT JOIN hero_metrics_v2 v2 ON v2.launch_id = l.id
        LEFT JOIN metrics_48h m ON m.launch_id = l.id
        {where}
        ORDER BY l.launch_at DESC
        """
    )



def update_return_metric(launch_id: int, return_order_count: int, return_qty: int, return_rate, collected_at=None):
    """HERO 48H metric의 사후 반품지표만 안전하게 갱신한다."""
    with session_scope() as s:
        obj = s.scalar(select(HeroMetricV2).where(HeroMetricV2.launch_id == int(launch_id)))
        if obj is None:
            return False
        obj.return_order_count = int(return_order_count or 0)
        obj.return_qty = int(return_qty or 0)
        obj.return_rate = float(return_rate) if return_rate is not None else None
        obj.return_collected_at = collected_at or datetime.utcnow()
        s.flush()
        return True


def save_post48h_followup(launch_id: int, decision: str, note: str = ""):
    """48H 완료 이후 MD 판단 저장. 관찰종료는 레이더에서만 제외하고 기록은 보존한다."""
    allowed = {"확대", "유지관찰", "보완", "중단", "관찰종료"}
    decision = str(decision or "").strip()
    if decision not in allowed:
        raise ValueError("올바른 사후관리 판단을 선택하세요.")

    with session_scope() as s:
        launch = s.get(Launch, int(launch_id))
        if launch is None:
            raise ValueError("해당 HERO 관찰건을 찾을 수 없습니다.")

        launch.review_manual = decision
        launch.md_action = (note or "").strip() or None

        pm = s.scalar(select(ProductMD).where(ProductMD.launch_id == launch.id))
        owner = None
        if pm is not None:
            owner = pm.md_owner
            pm.hero_watch = decision != "관찰종료"
            pm.updated_at = datetime.utcnow()

        # 현재 상태는 Launch에, 변경 이력은 ActionItem에 남긴다.
        s.add(
            ActionItem(
                product_no=launch.product_no,
                product_name=launch.product_name or "",
                issue_type="48H 사후관리",
                action_text=decision,
                owner=owner,
                status="완료",
                team="MD",
                note=(note or "").strip() or None,
            )
        )
        s.flush()
        return {"launch_id": launch.id, "decision": decision, "hero_watch": decision != "관찰종료"}


def ended_followups(limit: int = 30):
    return df(
        """
        SELECT l.id AS launch_id, l.product_no, l.product_name, l.launch_at, l.close_48h_at,
               l.review_manual AS md_followup, l.md_action AS md_followup_note,
               pm.md_owner, pm.updated_at
        FROM launches l
        LEFT JOIN product_md pm ON pm.launch_id=l.id
        WHERE l.review_manual='관찰종료'
        ORDER BY pm.updated_at DESC, l.close_48h_at DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
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
