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

if DATABASE_URL.startswith("sqlite"):
    # SQLite: make path absolute and add thread safety arg
    if DATABASE_URL.startswith("sqlite:///./"):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_name = DATABASE_URL.replace("sqlite:///./", "")
        db_path = os.path.join(base_dir, db_name)
        DATABASE_URL = f"sqlite:///{db_path}"
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Auto-create tables on import (for production deployment)
from models import Base
Base.metadata.create_all(bind=engine)

