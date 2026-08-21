from __future__ import annotations
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from misharp_hero.config import DATABASE_URL
from misharp_hero.models import Base

_engine = None
_Session = None


def get_engine():
    global _engine, _Session
    if _engine is None:
        connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
        _engine = create_engine(
            DATABASE_URL,
            future=True,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args=connect_args,
        )
        _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_session():
    get_engine()
    return _Session()


@contextmanager
def session_scope():
    s = get_session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def _ensure_product_columns(engine):
    """create_all이 기존 products 테이블 컬럼을 추가하지 못하므로 최소 마이그레이션을 수행한다."""
    inspector = inspect(engine)
    if "products" not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns("products")}
    dialect = engine.dialect.name
    ts_type = "TIMESTAMP" if dialect == "postgresql" else "DATETIME"
    wanted = {
        "retail_price": "FLOAT",
        "display": "VARCHAR(20)",
        "selling": "VARCHAR(20)",
        "cafe24_created_at": ts_type,
        "cafe24_updated_at": ts_type,
    }
    missing = [(name, coltype) for name, coltype in wanted.items() if name not in existing]
    if not missing:
        return

    with engine.begin() as conn:
        for name, coltype in missing:
            conn.execute(text(f"ALTER TABLE products ADD COLUMN {name} {coltype}"))




def _ensure_hero_metric_columns(engine):
    """기존 hero_metrics_v2에 사후 반품지표 컬럼을 안전하게 추가한다."""
    inspector = inspect(engine)
    if "hero_metrics_v2" not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns("hero_metrics_v2")}
    dialect = engine.dialect.name
    ts_type = "TIMESTAMP" if dialect == "postgresql" else "DATETIME"
    wanted = {
        "return_order_count": "INTEGER",
        "return_qty": "INTEGER",
        "return_rate": "FLOAT",
        "return_collected_at": ts_type,
    }
    missing = [(name, coltype) for name, coltype in wanted.items() if name not in existing]
    if not missing:
        return

    with engine.begin() as conn:
        for name, coltype in missing:
            conn.execute(text(f"ALTER TABLE hero_metrics_v2 ADD COLUMN {name} {coltype}"))


def init_db():
    """동시 Streamlit 실행에서 DDL 충돌이 나지 않도록 PostgreSQL advisory lock 사용."""
    engine = get_engine()

    if DATABASE_URL.startswith("postgresql"):
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(20260821)"))
            Base.metadata.create_all(bind=conn, checkfirst=True)
        _ensure_product_columns(engine)
        _ensure_hero_metric_columns(engine)
        return

    try:
        Base.metadata.create_all(engine, checkfirst=True)
        _ensure_product_columns(engine)
        _ensure_hero_metric_columns(engine)
    except Exception as e:
        if DATABASE_URL.startswith("sqlite") and "already exists" in str(e).lower():
            return
        raise
