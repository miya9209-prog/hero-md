from __future__ import annotations
from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    Float,
    DateTime,
    Text,
    Boolean,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_no: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    product_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    product_name: Mapped[str] = mapped_column(String(300), default="")
    supplier_product_name: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    tentative_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(200), nullable=True)
    supply_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    selling_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    # legacy 컬럼. HERO ITEM OS의 실제 재고는 절대 이 값을 사용하지 않는다.
    # 실제 재고는 inventory_current(Sellmate) 기준.
    stock_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    supplier_product_name: Mapped[str] = mapped_column(String(300), index=True)
    tentative_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    exposure_plan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    order_plan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    supply_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    focus_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    hero_dna: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    md_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    season_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reorder_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    prelaunch_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Launch(Base):
    __tablename__ = "launches"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    product_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    product_name: Mapped[str] = mapped_column(String(300), default="")
    supplier_product_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    launch_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    close_48h_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    hero_manual: Mapped[str | None] = mapped_column(String(20), nullable=True)
    review_manual: Mapped[str | None] = mapped_column(String(20), nullable=True)
    md_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    production_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Metric48h(Base):
    """v1 호환 테이블. 신규 화면은 HeroMetricV2를 우선 사용한다."""
    __tablename__ = "metrics_48h"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    launch_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    product_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    views: Mapped[int] = mapped_column(Integer, default=0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0)
    cvr: Mapped[float] = mapped_column(Float, default=0)
    qty_cvr: Mapped[float] = mapped_column(Float, default=0)
    rpv: Mapped[float] = mapped_column(Float, default=0)
    hero_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hero_grade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(String(100), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnalyticsProductMetric(Base):
    __tablename__ = "analytics_product_metrics"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    metric_date: Mapped[str] = mapped_column(String(10), index=True)
    product_no: Mapped[str] = mapped_column(String(50), index=True)
    product_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
    cart_count: Mapped[int] = mapped_column(Integer, default=0)
    cart_rate: Mapped[float] = mapped_column(Float, default=0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("metric_date", "product_no", name="uq_analytics_day_product"),
    )


class InventoryCurrent(Base):
    __tablename__ = "inventory_current"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inventory_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    product_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    product_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    variant_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    available_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warehouse: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="sellmate")
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HeroMetricV2(Base):
    __tablename__ = "hero_metrics_v2"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    launch_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    product_no: Mapped[str] = mapped_column(String(50), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)

    analytics_views: Mapped[int] = mapped_column(Integer, default=0)
    analytics_cart_count: Mapped[int] = mapped_column(Integer, default=0)
    analytics_cart_rate: Mapped[float] = mapped_column(Float, default=0)
    analytics_order_count: Mapped[int] = mapped_column(Integer, default=0)
    analytics_qty: Mapped[int] = mapped_column(Integer, default=0)
    analytics_revenue: Mapped[float] = mapped_column(Float, default=0)

    sera_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sera_orders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sera_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sera_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    sera_opv: Mapped[float | None] = mapped_column(Float, nullable=True)
    sera_espv: Mapped[float | None] = mapped_column(Float, nullable=True)
    sera_click_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    views: Mapped[int] = mapped_column(Integer, default=0)
    cart_count: Mapped[int] = mapped_column(Integer, default=0)
    cart_rate: Mapped[float] = mapped_column(Float, default=0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0)
    cvr: Mapped[float] = mapped_column(Float, default=0)
    qty_cvr: Mapped[float] = mapped_column(Float, default=0)
    rpv: Mapped[float] = mapped_column(Float, default=0)

    sellmate_stock_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_confidence: Mapped[str | None] = mapped_column(String(30), nullable=True)
    hero_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hero_grade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(String(150), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MonthlyHero(Base):
    __tablename__ = "monthly_heroes"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    month: Mapped[str] = mapped_column(String(7), index=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    product_name: Mapped[str] = mapped_column(String(300), default="")
    supplier_product_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    hero_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0)
    margin_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    keep_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("month", "product_name", name="uq_month_product"),)


class ActionItem(Base):
    __tablename__ = "action_items"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    product_name: Mapped[str] = mapped_column(String(300), default="")
    issue_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action_text: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="대기")
    team: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SeraMetric(Base):
    __tablename__ = "sera_metrics"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_name: Mapped[str] = mapped_column(String(300), default="")
    report_date: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    product_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    product_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_name: Mapped[str] = mapped_column(String(300), default="")
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    opv: Mapped[float | None] = mapped_column(Float, nullable=True)
    espv: Mapped[float | None] = mapped_column(Float, nullable=True)
    click_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), unique=True)
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SyncLog(Base):
    __tablename__ = "sync_logs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(50))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


Index("ix_launch_status_window", Launch.close_48h_at, Launch.product_no)
Index("ix_analytics_product_date", AnalyticsProductMetric.product_no, AnalyticsProductMetric.metric_date)
Index("ix_inventory_product_capture", InventoryCurrent.product_no, InventoryCurrent.captured_at)
