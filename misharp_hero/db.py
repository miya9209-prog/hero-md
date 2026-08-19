from __future__ import annotations
from contextlib import contextmanager
from sqlalchemy import create_engine, select
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
    Base.metadata.create_all(get_engine())
