"""
Initialize the database with all AI infrastructure tables.
Run this to recreate the database from scratch.
"""
import sys
import os

# Add the backend directory to the Python path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, backend_dir)

from database import engine
from models import Base

if __name__ == "__main__":
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Done! All AI infrastructure tables created.")
