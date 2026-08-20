from __future__ import annotations
from contextlib import contextmanager
from sqlalchemy import create_engine, select, text
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

def init_db():
    engine = get_engine()

    if DATABASE_URL.startswith("postgresql"):
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(20260821)"))
            Base.metadata.create_all(bind=conn, checkfirst=True)
        return

    try:
        Base.metadata.create_all(engine, checkfirst=True)
    except Exception as e:
        if DATABASE_URL.startswith("sqlite") and "already exists" in str(e).lower():
            return
        raise
