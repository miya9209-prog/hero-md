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
    retail_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    display: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    selling: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    cafe24_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cafe24_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # legacy 컬럼. HERO ITEM OS의 실제 재고는 절대 이 값을 사용하지 않는다.
    # 실제 재고는 inventory_current(Sellmate) 기준.
    stock_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProductMD(Base):
    """MD가 직접 관리하는 상품 운영정보. Cafe24 재동기화와 분리한다."""
    __tablename__ = "product_md"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_no: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hero_watch: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    launch_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    sale_end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    season: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    sourcing_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    md_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    md_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    launch_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # v3.0 자동 신상품 탐색 메타데이터
    auto_discovered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    discovery_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    homepage_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
    other_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    judgment_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class AnalyticsHistoryMonthly(Base):
    """최근 3년 HERO 사전진단 학습용 월별 상품 성과."""
    __tablename__ = "analytics_history_monthly"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_month: Mapped[str] = mapped_column(String(7), index=True)
    product_no: Mapped[str] = mapped_column(String(50), index=True)
    product_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
    cart_count: Mapped[int] = mapped_column(Integer, default=0)
    cart_rate: Mapped[float] = mapped_column(Float, default=0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0)
    cvr: Mapped[float] = mapped_column(Float, default=0)
    rpv: Mapped[float] = mapped_column(Float, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("period_month", "product_no", name="uq_history_month_product"),
    )


class ProductCategoryMonthly(Base):
    """Cafe24 Analytics 카테고리별 상품성과 월 스냅샷.

    상품은 복수 카테고리에 속할 수 있으므로 원본 관계를 보존하고,
    DNA/상품DB에서는 성과가 가장 큰 카테고리를 대표 카테고리로 선택한다.
    """
    __tablename__ = "product_category_monthly"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_month: Mapped[str] = mapped_column(String(7), index=True)
    product_no: Mapped[str] = mapped_column(String(50), index=True)
    product_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    product_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category_no: Mapped[str] = mapped_column(String(50), index=True)
    category_name: Mapped[str] = mapped_column(String(200), index=True)
    sales_count: Mapped[int] = mapped_column(Integer, default=0)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0)
    cart_count: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("period_month", "product_no", "category_no", name="uq_category_month_product"),
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

    # 반품률은 48시간 초기점수와 분리해 사후 판매품질 판단에 사용한다.
    return_order_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    return_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    return_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # v2 호환 컬럼. 신규 HERO 판정에서는 Sellmate 재고를 사용하지 않는다.
    sellmate_stock_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_confidence: Mapped[str | None] = mapped_column(String(30), nullable=True)
    hero_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hero_grade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(String(150), nullable=True)
    why_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(120), nullable=True)
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
Index("ix_product_md_watch_launch", ProductMD.hero_watch, ProductMD.launch_at)
Index("ix_analytics_product_date", AnalyticsProductMetric.product_no, AnalyticsProductMetric.metric_date)
Index("ix_history_product_month", AnalyticsHistoryMonthly.product_no, AnalyticsHistoryMonthly.period_month)
Index("ix_category_product_month", ProductCategoryMonthly.product_no, ProductCategoryMonthly.period_month)
Index("ix_inventory_product_capture", InventoryCurrent.product_no, InventoryCurrent.captured_at)
