"""SQLAlchemy engine / session wiring."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _connect_args(url: str) -> dict:
    if "sslmode=require" in url or settings.app_env == "production":
        return {"sslmode": "require"}
    return {}


_db_url = _normalize_database_url(settings.database_url)
engine = create_engine(
    _db_url,
    pool_pre_ping=True,
    future=True,
    connect_args=_connect_args(_db_url),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping() -> bool:
    """Cheap connectivity check used by the health endpoint."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
