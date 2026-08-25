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


def _ensure_columns(engine, table_name: str, wanted: dict[str, str]):
    """SQLAlchemy create_all이 기존 테이블 컬럼을 추가하지 못하므로 안전하게 ALTER한다."""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns(table_name)}
    missing = [(name, coltype) for name, coltype in wanted.items() if name not in existing]
    if not missing:
        return

    with engine.begin() as conn:
        for name, coltype in missing:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {coltype}"))


def _migrate_existing_tables(engine):
    dialect = engine.dialect.name
    ts_type = "TIMESTAMP" if dialect == "postgresql" else "DATETIME"
    bool_type = "BOOLEAN" if dialect == "postgresql" else "BOOLEAN"

    _ensure_columns(
        engine,
        "products",
        {
            "retail_price": "FLOAT",
            "display": "VARCHAR(20)",
            "selling": "VARCHAR(20)",
            "cafe24_created_at": ts_type,
            "cafe24_updated_at": ts_type,
        },
    )

    _ensure_columns(
        engine,
        "product_md",
        {
            "auto_discovered": f"{bool_type} DEFAULT FALSE",
            "discovered_at": ts_type,
            "discovery_source": "VARCHAR(80)",
            "homepage_seen_at": ts_type,
        },
    )

    _ensure_columns(
        engine,
        "launches",
        {
            "other_note": "TEXT",
            "judgment_updated_at": ts_type,
        },
    )

    _ensure_columns(
        engine,
        "hero_metrics_v2",
        {
            "return_order_count": "INTEGER",
            "return_qty": "INTEGER",
            "return_rate": "FLOAT",
            "return_collected_at": ts_type,
            "why_text": "TEXT",
            "recommended_action": "VARCHAR(120)",
        },
    )


def init_db():
    """기존 운영DB를 보존하면서 신규 테이블/컬럼만 추가한다."""
    engine = get_engine()

    if DATABASE_URL.startswith("postgresql"):
        # Streamlit / GitHub Actions 동시 부팅 시 DDL 충돌 방지.
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(20260825)"))
            Base.metadata.create_all(bind=conn, checkfirst=True)
        _migrate_existing_tables(engine)
        return

    try:
        Base.metadata.create_all(engine, checkfirst=True)
        _migrate_existing_tables(engine)
    except Exception as e:
        if DATABASE_URL.startswith("sqlite") and "already exists" in str(e).lower():
            return
        raise
