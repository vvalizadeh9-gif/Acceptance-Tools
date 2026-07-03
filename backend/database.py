"""
Engine/session wiring.

Production target: PostgreSQL, running behind Docker + Nginx on your
company server — this is what real multi-user role enforcement (Admin,
PM, Coordinator, Contractor, Regional Manager, Viewer all hitting the
same portal concurrently) actually needs, and it's what you already
settled on. Set DATABASE_URL to point at it:

    DATABASE_URL=postgresql+psycopg://user:pass@host:5432/uso_platform

Local dev convenience: if DATABASE_URL isn't set, this falls back to a
throwaway SQLite file so you (or anyone helping you) can run the API on
a laptop with zero setup. Nothing else in this codebase changes between
the two — SQLAlchemy's `Uuid`, `CheckConstraint`, etc. in models.py are
dialect-portable. Don't ship the SQLite fallback to production: it can't
handle concurrent writes from 5+ contractors and coordinators at once.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DEFAULT_SQLITE_PATH = os.environ.get("USO_DB_PATH", "./uso_platform.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. For SQLite this is enough to bootstrap a fresh
    local instance; for Postgres in production prefer Alembic migrations."""
    import models  # noqa: F401  (ensures models are registered on Base)
    Base.metadata.create_all(bind=engine)
