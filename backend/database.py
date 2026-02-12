from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Fallback to sqlite if no DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

# If using sqlite and relative path, make it absolute relative to this file
if DATABASE_URL.startswith("sqlite:///./"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_name = DATABASE_URL.replace("sqlite:///./", "")
    db_path = os.path.join(base_dir, db_name)
    DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
