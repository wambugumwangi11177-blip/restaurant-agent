from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Fallback to sqlite if no DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./restaurant.db"

# Fix for Neon/Render: postgres:// → postgresql:// (SQLAlchemy 2.x requirement)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Build engine args based on DB type
connect_args = {}
engine_kwargs = {}

if DATABASE_URL.startswith("sqlite"):
    # SQLite: make path absolute and add thread safety arg
    if DATABASE_URL.startswith("sqlite:///./"):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_name = DATABASE_URL.replace("sqlite:///./", "")
        db_path = os.path.join(base_dir, db_name)
        DATABASE_URL = f"sqlite:///{db_path}"
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql"):
    # PostgreSQL (Neon/Render): optimize for production scalability
    engine_kwargs = {
        "pool_size": 20,          # Number of connections to maintain in pool
        "max_overflow": 30,       # Additional connections allowed beyond pool_size
        "pool_timeout": 30,       # Seconds to wait before giving up on getting a connection
        "pool_recycle": 1800,     # Recycle connections after 30 minutes
        "pool_pre_ping": True,    # Test connections before using them
        "echo": os.getenv("SQL_ECHO", "false").lower() == "true"  # Log SQL queries if enabled
    }

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Call this explicitly to create tables (don't run at import time)
def init_db():
    from models import Base
    Base.metadata.create_all(bind=engine)


# Additional function for getting engine info (useful for monitoring)
def get_engine_info():
    """Return engine pool information for monitoring"""
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalid()
    }