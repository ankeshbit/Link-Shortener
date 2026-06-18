import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment variables from .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Fallback for pytest/testing environment
if not DATABASE_URL:
    if "pytest" in sys.modules or os.getenv("TESTING") == "true":
        DATABASE_URL = "postgresql://postgres:postgrespassword@localhost:5432/test_db"
    else:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Please configure it with a PostgreSQL connection string."
        )

# Handle PostgreSQL url scheme change on cloud providers like Railway (postgres:// -> postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Ensure PostgreSQL scheme is used
if not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError(
        f"Invalid DATABASE_URL schema: '{DATABASE_URL}'. PostgreSQL is required."
    )

engine = create_engine(DATABASE_URL)
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
