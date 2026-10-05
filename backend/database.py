import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Configure it with the Neon PostgreSQL connection string."
    )

def normalize_database_url(database_url: str) -> str:
    """Use the installed psycopg2 driver for every PostgreSQL URL."""
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(
            f"Invalid DATABASE_URL schema: '{database_url}'. "
            "PostgreSQL is required."
        )
    return url.set(drivername="postgresql+psycopg2").render_as_string(
        hide_password=False
    )


if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DATABASE_URL = normalize_database_url(DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
