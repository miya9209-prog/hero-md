from __future__ import annotations
import json
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
    AnalyticsHistoryMonthly,
    ProductCategoryMonthly,
    InventoryCurrent,
    HeroMetricV2,
    MonthlyHero,
    ActionItem,
    SeraMetric,
    SyncLog,
    NewProductPageSnapshot,
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
    AnalyticsHistoryMonthly,
    ProductCategoryMonthly,
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
               COALESCE(pm.auto_discovered, FALSE) AS auto_discovered,
               pm.discovered_at, pm.discovery_source, pm.homepage_seen_at,
               pm.homepage_last_seen_at, pm.homepage_exit_at, pm.homepage_exit_status,
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

    # v3.0 공식 판정 데이터는 Cafe24 Analytics 하나만 사용한다.
    # SERA / Sellmate는 레거시 테이블은 보존하되 상품DB 화면/판정에는 혼합하지 않는다.
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
               pm.season, pm.sourcing_type, pm.md_owner, pm.md_note,
               COALESCE(pm.auto_discovered, FALSE) AS auto_discovered,
               pm.discovered_at, pm.discovery_source, pm.homepage_seen_at,
               pm.homepage_last_seen_at, pm.homepage_exit_at, pm.homepage_exit_status,
               p.selling_price, p.display AS cafe24_display, p.selling AS cafe24_selling,
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
               v2.why_text, v2.recommended_action,
               v2.cart_count, v2.cart_rate,
               v2.return_order_count, v2.return_qty, v2.return_rate, v2.return_collected_at,
               l.review_manual AS md_followup,
               l.md_action AS md_team_work,
               l.production_action AS production_team_work,
               COALESCE(v2.collected_at, m.collected_at) AS collected_at
        FROM launches l
        LEFT JOIN product_md pm ON pm.launch_id = l.id
        LEFT JOIN products p ON p.product_no = l.product_no
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


def save_judgment_workflow(
    launch_id: int,
    decision: str,
    md_team_work: str = "",
    production_team_work: str = "",
    other_note: str = "",
):
    """상품 판정/후속업무 공유 저장.

    관찰종료는 상품DB/이력은 보존하고 '상품 탐색'과 기본 후속업무 목록에서만 제외한다.
    """
    allowed = {"미정", "확대", "유지관찰", "보완", "중단", "관찰종료"}
    decision = str(decision or "미정").strip()
    if decision not in allowed:
        raise ValueError("올바른 상품 판정을 선택하세요.")

    with session_scope() as s:
        launch = s.get(Launch, int(launch_id))
        if launch is None:
            raise ValueError("해당 상품 관찰건을 찾을 수 없습니다.")

        launch.review_manual = None if decision == "미정" else decision
        launch.md_action = (md_team_work or "").strip() or None
        launch.production_action = (production_team_work or "").strip() or None
        launch.other_note = (other_note or "").strip() or None
        launch.judgment_updated_at = datetime.utcnow()

        pm = s.scalar(select(ProductMD).where(ProductMD.launch_id == launch.id))
        owner = None
        if pm is not None:
            owner = pm.md_owner
            pm.hero_watch = decision != "관찰종료"
            pm.updated_at = datetime.utcnow()

        s.add(
            ActionItem(
                product_no=launch.product_no,
                product_name=launch.product_name or "",
                issue_type="상품 판정 및 후속업무",
                action_text=decision,
                owner=owner,
                status="완료",
                team="공유",
                note=" | ".join(
                    x for x in [
                        f"MD: {(md_team_work or '').strip()}" if (md_team_work or "").strip() else "",
                        f"제작: {(production_team_work or '').strip()}" if (production_team_work or "").strip() else "",
                        f"기타: {(other_note or '').strip()}" if (other_note or "").strip() else "",
                    ] if x
                ) or None,
            )
        )
        s.flush()
        return {"launch_id": launch.id, "decision": decision, "hero_watch": decision != "관찰종료"}


def save_post48h_followup(launch_id: int, decision: str, note: str = ""):
    """v2 호환 wrapper."""
    return save_judgment_workflow(launch_id, decision, md_team_work=note)

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


def recent_registered_product_nos(cutoff_at: datetime):
    data = df(
        "SELECT product_no FROM products WHERE product_no IS NOT NULL AND cafe24_created_at >= :cutoff",
        {"cutoff": cutoff_at},
    )
    if data.empty:
        return set()
    return set(data["product_no"].astype(str).tolist())


def upsert_history_monthly(rows: list[dict]):
    if not rows:
        return 0
    engine = get_engine()
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            stmt = pg_insert(AnalyticsHistoryMonthly).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=[AnalyticsHistoryMonthly.period_month, AnalyticsHistoryMonthly.product_no],
                set_={
                    "product_name": stmt.excluded.product_name,
                    "views": stmt.excluded.views,
                    "cart_count": stmt.excluded.cart_count,
                    "cart_rate": stmt.excluded.cart_rate,
                    "order_count": stmt.excluded.order_count,
                    "qty": stmt.excluded.qty,
                    "revenue": stmt.excluded.revenue,
                    "cvr": stmt.excluded.cvr,
                    "rpv": stmt.excluded.rpv,
                    "collected_at": stmt.excluded.collected_at,
                },
            )
        elif engine.dialect.name == "sqlite":
            stmt = sqlite_insert(AnalyticsHistoryMonthly).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["period_month", "product_no"],
                set_={
                    "product_name": stmt.excluded.product_name,
                    "views": stmt.excluded.views,
                    "cart_count": stmt.excluded.cart_count,
                    "cart_rate": stmt.excluded.cart_rate,
                    "order_count": stmt.excluded.order_count,
                    "qty": stmt.excluded.qty,
                    "revenue": stmt.excluded.revenue,
                    "cvr": stmt.excluded.cvr,
                    "rpv": stmt.excluded.rpv,
                    "collected_at": stmt.excluded.collected_at,
                },
            )
        else:
            raise RuntimeError(f"지원하지 않는 DB: {engine.dialect.name}")
        conn.execute(stmt)
    return len(rows)



def upsert_category_monthly(rows: list[dict]):
    if not rows:
        return 0
    engine = get_engine()
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            stmt = pg_insert(ProductCategoryMonthly).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    ProductCategoryMonthly.period_month,
                    ProductCategoryMonthly.product_no,
                    ProductCategoryMonthly.category_no,
                ],
                set_={
                    "product_name": stmt.excluded.product_name,
                    "product_code": stmt.excluded.product_code,
                    "category_name": stmt.excluded.category_name,
                    "sales_count": stmt.excluded.sales_count,
                    "qty": stmt.excluded.qty,
                    "revenue": stmt.excluded.revenue,
                    "cart_count": stmt.excluded.cart_count,
                    "collected_at": stmt.excluded.collected_at,
                },
            )
        elif engine.dialect.name == "sqlite":
            stmt = sqlite_insert(ProductCategoryMonthly).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["period_month", "product_no", "category_no"],
                set_={
                    "product_name": stmt.excluded.product_name,
                    "product_code": stmt.excluded.product_code,
                    "category_name": stmt.excluded.category_name,
                    "sales_count": stmt.excluded.sales_count,
                    "qty": stmt.excluded.qty,
                    "revenue": stmt.excluded.revenue,
                    "cart_count": stmt.excluded.cart_count,
                    "collected_at": stmt.excluded.collected_at,
                },
            )
        else:
            raise RuntimeError(f"지원하지 않는 DB: {engine.dialect.name}")
        conn.execute(stmt)
    return len(rows)


def apply_representative_categories(product_nos: list[str] | None = None):
    """카테고리별 실적에서 상품별 대표 카테고리를 products.category에 반영한다.

    우선순위: 카테고리 매출 > 판매수량 > 판매건수 > 장바구니 > 최근월.
    상품명으로 카테고리를 추정하지 않는다.
    """
    where = ""
    params = {}
    if product_nos:
        data = _df_in(
            """
            SELECT period_month, product_no, category_no, category_name,
                   sales_count, qty, revenue, cart_count
            FROM product_category_monthly
            WHERE product_no IN :product_nos
            """,
            [str(x) for x in product_nos],
        )
    else:
        data = df(
            """
            SELECT period_month, product_no, category_no, category_name,
                   sales_count, qty, revenue, cart_count
            FROM product_category_monthly
            """
        )
    if data.empty:
        return 0
    for c in ["sales_count", "qty", "revenue", "cart_count"]:
        data[c] = pd.to_numeric(data[c], errors="coerce").fillna(0)
    data["category_name"] = data["category_name"].fillna("").astype(str).str.strip()
    data = data[data["category_name"] != ""]
    if data.empty:
        return 0
    # 같은 카테고리의 여러 월 실적을 합산하되, 동률이면 최근 데이터 우선.
    grouped = (
        data.groupby(["product_no", "category_no", "category_name"], as_index=False)
        .agg(
            revenue=("revenue", "sum"),
            qty=("qty", "sum"),
            sales_count=("sales_count", "sum"),
            cart_count=("cart_count", "sum"),
            latest_month=("period_month", "max"),
        )
    )
    grouped = grouped.sort_values(
        ["product_no", "revenue", "qty", "sales_count", "cart_count", "latest_month"],
        ascending=[True, False, False, False, False, False],
    )
    best = grouped.drop_duplicates("product_no", keep="first")
    engine = get_engine()
    updated = 0
    with engine.begin() as conn:
        for r in best.itertuples(index=False):
            result = conn.execute(
                text("UPDATE products SET category=:category, updated_at=:updated_at WHERE product_no=:product_no"),
                {
                    "category": str(r.category_name),
                    "updated_at": datetime.utcnow(),
                    "product_no": str(r.product_no),
                },
            )
            updated += int(result.rowcount or 0)
    return updated


def category_summary():
    return df(
        """
        SELECT COUNT(*) AS rows_count, COUNT(DISTINCT product_no) AS product_count,
               MIN(period_month) AS first_month, MAX(period_month) AS last_month
        FROM product_category_monthly
        """
    )

def history_summary():
    return df(
        """
        SELECT COUNT(*) AS rows_count,
               COUNT(DISTINCT product_no) AS product_count,
               MIN(period_month) AS first_month,
               MAX(period_month) AS last_month
        FROM analytics_history_monthly
        """
    )


def history_recent_rows(limit: int = 20):
    return df(
        """
        SELECT h.period_month, h.product_no, COALESCE(p.product_name, h.product_name) AS product_name,
               h.views, h.cart_count, h.order_count, h.qty, h.revenue, h.cvr, h.rpv
        FROM analytics_history_monthly h
        LEFT JOIN products p ON p.product_no=h.product_no
        ORDER BY h.period_month DESC, h.revenue DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )

def dna_history_dataset(months: int = 12):
    """최근 3년 월별 성과에서 미샵 DNA 분석용 상품 집계 데이터를 만든다.

    전체 회사 상품DB는 보존하지만 DNA 분석 범위는 최대 36개월로 제한한다.
    상품별로 선택 기간의 조회/장바구니/판매/매출을 합산하고 CVR/RPV를 재계산한다.
    """
    months = max(1, min(int(months or 12), 36))
    latest = df("SELECT MAX(period_month) AS max_month FROM analytics_history_monthly")
    if latest.empty or not latest.iloc[0].get("max_month"):
        return pd.DataFrame()
    max_month = pd.Period(str(latest.iloc[0]["max_month"]), freq="M")
    min_month = max_month - (months - 1)
    data = df(
        """
        SELECT h.product_no,
               COALESCE(MAX(p.product_name), MAX(h.product_name)) AS product_name,
               MAX(p.category) AS product_db_category,
               MAX(p.selling_price) AS selling_price,
               SUM(COALESCE(h.views,0)) AS views,
               SUM(COALESCE(h.cart_count,0)) AS cart_count,
               SUM(COALESCE(h.order_count,0)) AS order_count,
               SUM(COALESCE(h.qty,0)) AS qty,
               SUM(COALESCE(h.revenue,0)) AS revenue,
               MIN(h.period_month) AS first_month,
               MAX(h.period_month) AS last_month
        FROM analytics_history_monthly h
        LEFT JOIN products p ON p.product_no=h.product_no
        WHERE h.period_month BETWEEN :start_month AND :end_month
          AND (p.cafe24_created_at IS NULL OR p.cafe24_created_at >= :cutoff)
        GROUP BY h.product_no
        """,
        {
            "start_month": str(min_month),
            "end_month": str(max_month),
            "cutoff": datetime.utcnow() - timedelta(days=365 * 3 + 2),
        },
    )
    if data.empty:
        return data

    # 선택 기간의 실제 Cafe24 Analytics 카테고리 성과로 대표 카테고리를 결정한다.
    # 카테고리가 없을 때 상품명으로 추정하지 않고 상품DB 값 또는 미분류만 사용한다.
    cat = df(
        """
        SELECT product_no, category_no, category_name,
               SUM(COALESCE(revenue,0)) AS revenue,
               SUM(COALESCE(qty,0)) AS qty,
               SUM(COALESCE(sales_count,0)) AS sales_count,
               SUM(COALESCE(cart_count,0)) AS cart_count,
               MAX(period_month) AS latest_month
        FROM product_category_monthly
        WHERE period_month BETWEEN :start_month AND :end_month
        GROUP BY product_no, category_no, category_name
        """,
        {"start_month": str(min_month), "end_month": str(max_month)},
    )
    category_map = {}
    if not cat.empty:
        for c in ["revenue", "qty", "sales_count", "cart_count"]:
            cat[c] = pd.to_numeric(cat[c], errors="coerce").fillna(0)
        cat["category_name"] = cat["category_name"].fillna("").astype(str).str.strip()
        cat = cat[cat["category_name"] != ""].sort_values(
            ["product_no", "revenue", "qty", "sales_count", "cart_count", "latest_month"],
            ascending=[True, False, False, False, False, False],
        )
        best_cat = cat.drop_duplicates("product_no", keep="first")
        category_map = dict(zip(best_cat["product_no"].astype(str), best_cat["category_name"]))
    data["category"] = data.apply(
        lambda r: category_map.get(str(r["product_no"]))
        or (str(r.get("product_db_category") or "").strip() if str(r.get("product_db_category") or "").strip().lower() not in {"", "none", "nan"} else "미분류"),
        axis=1,
    )

    for c in ["views", "cart_count", "order_count", "qty", "revenue", "selling_price"]:
        if c in data.columns:
            data[c] = pd.to_numeric(data[c], errors="coerce").fillna(0)
    data["cvr"] = data.apply(lambda r: (float(r["order_count"]) / float(r["views"])) if float(r["views"]) > 0 else 0.0, axis=1)
    data["rpv"] = data.apply(lambda r: (float(r["revenue"]) / float(r["views"])) if float(r["views"]) > 0 else 0.0, axis=1)
    data["cart_rate"] = data.apply(lambda r: (float(r["cart_count"]) / float(r["views"])) if float(r["views"]) > 0 else 0.0, axis=1)
    return data

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


def exploration_launches():
    """현재 48시간 탐색창에 있는 상품만 반환한다."""
    data = current_launches(only_observed=True)
    if data.empty:
        return data
    now = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None)
    launch_at = pd.to_datetime(data["launch_at"], errors="coerce")
    close_at = pd.to_datetime(data["close_48h_at"], errors="coerce")
    mask = launch_at.notna() & close_at.notna() & (launch_at <= now) & (close_at > now)
    return data[mask].sort_values("launch_at", ascending=False).reset_index(drop=True)


def judgment_launches(include_ended: bool = False):
    """48시간 완료 후 상품 판정 및 공유 후속업무 대상."""
    data = current_launches(only_observed=False)
    if data.empty:
        return data
    now = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None)
    close_at = pd.to_datetime(data["close_48h_at"], errors="coerce")
    data = data[close_at.notna() & (close_at <= now)].copy()
    if not include_ended and "md_followup" in data.columns:
        data = data[data["md_followup"].fillna("") != "관찰종료"].copy()
    return data.sort_values("close_48h_at", ascending=False).reset_index(drop=True)


def recent_products_for_discovery(cutoff_at: datetime):
    """자동탐색 후보: 최근 등록 + 판매중 + 진열중인 Cafe24 상품."""
    return df(
        """
        SELECT p.product_no, p.product_name, p.product_code, p.category,
               p.selling_price, p.image_url, p.cafe24_created_at,
               p.display, p.selling,
               pm.id AS product_md_id, pm.launch_id, pm.hero_watch,
               pm.discovered_at, pm.discovery_source, pm.homepage_seen_at
        FROM products p
        LEFT JOIN product_md pm ON pm.product_no=p.product_no
        WHERE p.product_no IS NOT NULL
          AND p.cafe24_created_at >= :cutoff
          AND COALESCE(p.display,'T') IN ('T','TRUE','Y','YES','1')
          AND COALESCE(p.selling,'T') IN ('T','TRUE','Y','YES','1')
        ORDER BY p.cafe24_created_at DESC
        """,
        {"cutoff": cutoff_at},
    )


def auto_register_exploration(
    product_no: str,
    detected_at: datetime,
    source: str,
    homepage_seen_at: datetime | None = None,
    launch_at: datetime | None = None,
):
    """신상페이지 신규등장 상품을 상품 탐색에 등록한다.

    같은 product_no가 과거에 이미 판매된 상품이어도 신상페이지에서 새롭게 등장한
    '재오픈 신상'이면 새 Launch를 만든다. 단, 현재 48시간 관찰이 살아 있으면 중복 생성하지 않는다.
    """
    product_no = str(product_no or "").strip()
    if not product_no:
        return {"created": False, "reason": "product_no 없음"}

    with session_scope() as s:
        product = s.scalar(select(Product).where(Product.product_no == product_no))
        if product is None:
            return {"created": False, "reason": "상품DB 없음"}

        pm = s.scalar(select(ProductMD).where(ProductMD.product_no == product_no))
        if pm is None:
            pm = ProductMD(product_no=product_no)
            s.add(pm)

        # 현재 진행 중인 관찰건은 중복등록하지 않는다.
        if pm.launch_id:
            existing = s.get(Launch, pm.launch_id)
            if existing is not None and existing.close_48h_at and existing.close_48h_at > detected_at:
                pm.homepage_seen_at = pm.homepage_seen_at or homepage_seen_at
                pm.homepage_last_seen_at = homepage_seen_at or detected_at
                pm.homepage_exit_at = None
                pm.homepage_exit_status = None
                pm.updated_at = datetime.utcnow()
                s.flush()
                return {"created": False, "launch_id": existing.id, "reason": "현재 관찰중"}

        effective_launch_at = launch_at or detected_at
        launch = Launch(
            product_id=product.id,
            product_no=product_no,
            product_name=product.product_name or "",
            supplier_product_name=product.supplier_product_name,
            launch_at=effective_launch_at,
            close_48h_at=effective_launch_at + timedelta(hours=48),
        )
        s.add(launch)
        s.flush()

        pm.hero_watch = True
        pm.launch_at = effective_launch_at
        pm.launch_id = launch.id
        pm.auto_discovered = True
        pm.discovered_at = detected_at
        pm.discovery_source = source or "신상페이지 + Cafe24 API"
        pm.homepage_seen_at = homepage_seen_at or detected_at
        pm.homepage_last_seen_at = homepage_seen_at or detected_at
        pm.homepage_exit_at = None
        pm.homepage_exit_status = None
        pm.updated_at = datetime.utcnow()
        s.flush()
        return {"created": True, "launch_id": launch.id}


def _decode_snapshot_payload(raw: str | None):
    try:
        payload = json.loads(raw or "[]")
    except Exception:
        payload = []
    if isinstance(payload, dict):
        ordered = [str(x) for x in payload.get("ordered", []) if str(x)]
        return {"version": int(payload.get("version") or 4), "ordered": ordered, "set": set(ordered)}
    ordered = [str(x) for x in (payload or []) if str(x)]
    return {"version": 3, "ordered": ordered, "set": set(ordered)}


def latest_new_product_snapshot():
    with session_scope() as s:
        row = s.scalar(
            select(NewProductPageSnapshot)
            .order_by(NewProductPageSnapshot.captured_at.desc())
            .limit(1)
        )
        if row is None:
            return None
        decoded = _decode_snapshot_payload(row.product_nos_json)
        return {
            "id": row.id,
            "captured_at": row.captured_at,
            "page_url": row.page_url,
            "version": decoded["version"],
            "ordered_product_nos": decoded["ordered"],
            "product_nos": decoded["set"],
            "product_count": int(row.product_count or len(decoded["ordered"])),
        }


def new_product_baseline_for_day(day):
    start_at = datetime.combine(day, datetime.min.time())
    noon_at = datetime.combine(day, datetime.min.time()).replace(hour=12)
    with session_scope() as s:
        rows = s.scalars(
            select(NewProductPageSnapshot)
            .where(
                NewProductPageSnapshot.captured_at >= start_at,
                NewProductPageSnapshot.captured_at < noon_at,
            )
            .order_by(NewProductPageSnapshot.captured_at.desc())
            .limit(20)
        ).all()
        for row in rows:
            decoded = _decode_snapshot_payload(row.product_nos_json)
            if decoded["version"] >= 4 and decoded["ordered"]:
                return {
                    "id": row.id,
                    "captured_at": row.captured_at,
                    "page_url": row.page_url,
                    "version": decoded["version"],
                    "ordered_product_nos": decoded["ordered"],
                    "product_nos": decoded["set"],
                }
    return None


def save_new_product_snapshot(captured_at: datetime, page_url: str, product_nos, added=None, removed=None):
    ordered, seen = [], set()
    for x in product_nos or []:
        pno = str(x or "").strip()
        if pno and pno not in seen:
            ordered.append(pno)
            seen.add(pno)
    payload = {"version": 4, "ordered": ordered}
    added_list = [str(x) for x in (added or []) if str(x)]
    removed_list = [str(x) for x in (removed or []) if str(x)]
    with session_scope() as s:
        obj = NewProductPageSnapshot(
            captured_at=captured_at,
            page_url=page_url,
            product_nos_json=json.dumps(payload, ensure_ascii=False),
            product_count=len(ordered),
            added_json=json.dumps(added_list, ensure_ascii=False),
            removed_json=json.dumps(removed_list, ensure_ascii=False),
        )
        s.add(obj)
        s.flush()
        return obj.id


def new_product_discovery_status():
    with session_scope() as s:
        row = s.scalar(
            select(NewProductPageSnapshot)
            .order_by(NewProductPageSnapshot.captured_at.desc())
            .limit(1)
        )
        if row is None:
            return {"current": 0, "added": 0, "removed": 0, "captured_at": None, "page_url": None, "version": 0}
        decoded = _decode_snapshot_payload(row.product_nos_json)
        try:
            added = json.loads(row.added_json or "[]")
        except Exception:
            added = []
        try:
            removed = json.loads(row.removed_json or "[]")
        except Exception:
            removed = []
        return {
            "current": int(row.product_count or 0),
            "added": len(added),
            "removed": len(removed),
            "captured_at": row.captured_at,
            "page_url": row.page_url,
            "version": decoded["version"],
        }


def cleanup_legacy_discovery_active():
    now = datetime.now()
    cleaned = 0
    with session_scope() as s:
        rows = s.scalars(
            select(ProductMD).where(
                ProductMD.auto_discovered == True,
                ProductMD.hero_watch == True,
            )
        ).all()
        for pm in rows:
            source = str(pm.discovery_source or "")
            if source.startswith("신상 상단 신규오픈"):
                continue
            launch = s.get(Launch, pm.launch_id) if pm.launch_id else None
            if launch is None:
                continue
            if launch.close_48h_at and launch.close_48h_at <= now:
                continue
            if ("신상페이지" not in source) and ("541" not in source):
                continue
            pm.hero_watch = False
            pm.updated_at = datetime.utcnow()
            launch.review_manual = "관찰종료"
            if not launch.other_note:
                launch.other_note = "상품탐색 v4 전환 시 기존 자동탐색 오탐 정리"
            cleaned += 1
        s.flush()
    log_sync("신상품 자동탐색", "정리", f"v4 이전 현재 관찰중 자동탐색 {cleaned}개 관찰종료")
    return cleaned

def recent_discovery_recovery_candidates(hours: int = 48):
    """v4 전환 정리로 관찰종료된 최근 자동탐색 상품 중 복구 가능한 후보."""
    cutoff = datetime.utcnow() - timedelta(hours=int(hours))
    return df(
        """
        SELECT
            l.id AS launch_id,
            l.product_no,
            l.product_name,
            l.launch_at,
            l.close_48h_at,
            l.review_manual,
            l.other_note,
            pm.discovered_at,
            pm.discovery_source,
            pm.homepage_seen_at,
            pm.homepage_last_seen_at,
            COALESCE(v2.views, m.views, 0) AS views,
            COALESCE(v2.cart_count, 0) AS cart_count,
            COALESCE(v2.order_count, m.order_count, 0) AS order_count,
            COALESCE(v2.qty, m.qty, 0) AS qty,
            COALESCE(v2.revenue, m.revenue, 0) AS revenue
        FROM launches l
        JOIN product_md pm ON pm.launch_id = l.id
        LEFT JOIN hero_metrics_v2 v2 ON v2.launch_id = l.id
        LEFT JOIN metrics_48h m ON m.launch_id = l.id
        WHERE pm.auto_discovered = TRUE
          AND COALESCE(pm.hero_watch, FALSE) = FALSE
          AND l.review_manual = '관찰종료'
          AND l.launch_at >= :cutoff
          AND COALESCE(l.other_note, '') LIKE '%상품탐색 v4 전환%'
        ORDER BY l.launch_at DESC, l.id DESC
        """,
        {"cutoff": cutoff},
    )


def restore_discovery_launches(launch_ids: list[int]):
    """선택한 기존 Launch를 새로 만들지 않고 48시간 탐색으로 복구한다."""
    ids = sorted({int(x) for x in (launch_ids or []) if str(x).strip()})
    if not ids:
        return 0

    restored = 0
    with session_scope() as s:
        for launch_id in ids:
            launch = s.get(Launch, launch_id)
            if launch is None:
                continue
            pm = s.scalar(select(ProductMD).where(ProductMD.launch_id == launch.id))
            if pm is None:
                continue

            # v4 전환 정리로 종료된 건만 복구
            if launch.review_manual != "관찰종료":
                continue
            if "상품탐색 v4 전환" not in str(launch.other_note or ""):
                continue

            pm.hero_watch = True
            pm.launch_at = launch.launch_at
            pm.updated_at = datetime.utcnow()
            launch.review_manual = None

            note = str(launch.other_note or "")
            note = note.replace("상품탐색 v4 전환 시 기존 자동탐색 오탐 정리", "").strip(" |")
            launch.other_note = note or None

            restored += 1

        s.flush()

    log_sync("신상품 자동탐색", "복구", f"최근 자동탐색 {restored}개 48시간 탐색 복구")
    return restored


def product_rows_for_discovery(product_nos: set[str]):
    return _df_in(
        """
        SELECT product_no, product_name, selling_price, display, selling,
               cafe24_created_at, cafe24_updated_at
        FROM products
        WHERE product_no IN :product_nos
        """,
        sorted(str(x) for x in product_nos),
    )


def mark_homepage_seen(product_nos: set[str], seen_at: datetime):
    if not product_nos:
        return 0
    rows = product_rows_for_discovery(product_nos)
    if rows.empty:
        return 0
    count = 0
    with session_scope() as s:
        for pno in rows["product_no"].astype(str).tolist():
            pm = s.scalar(select(ProductMD).where(ProductMD.product_no == pno))
            if pm is None:
                pm = ProductMD(product_no=pno)
                s.add(pm)
            pm.homepage_last_seen_at = seen_at
            pm.homepage_exit_at = None
            pm.homepage_exit_status = None
            pm.updated_at = datetime.utcnow()
            count += 1
        s.flush()
    return count


def mark_homepage_exit(product_nos: set[str], exit_at: datetime):
    """신상페이지에서 사라진 상품을 API 상태와 함께 기록한다.

    판매중/진열중이면 '신상페이지 이탈(품절 가능)'로만 표시하고 품절로 단정하지 않는다.
    """
    if not product_nos:
        return 0
    rows = product_rows_for_discovery(product_nos)
    status_map = {}
    for _, r in rows.iterrows():
        display = str(r.get("display") or "").upper()
        selling = str(r.get("selling") or "").upper()
        if selling in {"F", "FALSE", "N", "NO", "0"}:
            status = "판매중지"
        elif display in {"F", "FALSE", "N", "NO", "0"}:
            status = "진열종료"
        else:
            status = "신상페이지 이탈(품절 가능)"
        status_map[str(r.get("product_no"))] = status

    count = 0
    with session_scope() as s:
        for pno in sorted(str(x) for x in product_nos):
            pm = s.scalar(select(ProductMD).where(ProductMD.product_no == pno))
            if pm is None:
                continue
            pm.homepage_exit_at = exit_at
            pm.homepage_exit_status = status_map.get(pno, "신상페이지 이탈")
            pm.updated_at = datetime.utcnow()
            count += 1
        s.flush()
    return count

def three_year_history_benchmark():
    """WHY 설명용 비교집단.

    48H 관찰 히스토리가 충분하면 등록일 기준 최근 3년 상품만 사용한다.
    현재 시스템 누적이 적을 경우에는 이용 가능한 완료 관찰건으로 자동 fallback한다.
    """
    cutoff = datetime.utcnow() - timedelta(days=365 * 3 + 1)
    data = df(
        """
        SELECT v2.views, v2.cart_count, v2.cart_rate, v2.order_count, v2.qty,
               v2.revenue, v2.cvr, v2.rpv, v2.hero_score, v2.return_rate,
               p.category, p.selling_price, p.cafe24_created_at
        FROM hero_metrics_v2 v2
        JOIN launches l ON l.id=v2.launch_id
        LEFT JOIN products p ON p.product_no=v2.product_no
        WHERE l.close_48h_at <= :now
          AND (p.cafe24_created_at IS NULL OR p.cafe24_created_at >= :cutoff)
        ORDER BY l.close_48h_at DESC
        """,
        {"now": datetime.utcnow(), "cutoff": cutoff},
    )
    # 최근 3년 데이터가 5개 미만이면 점수/WHY 엔진이 절대기준으로 fallback한다.
    # 3년 이전 데이터를 억지로 섞지 않는다.
    return data
