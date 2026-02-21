"""
Add new columns to orders table for delivery channel, payment method, etc.
Run once to migrate the existing SQLite database.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "restaurant.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get existing columns in orders table
cursor.execute("PRAGMA table_info(orders)")
existing_cols = {row[1] for row in cursor.fetchall()}
print(f"Existing columns in orders: {existing_cols}")

migrations = [
    ("delivery_channel", "ALTER TABLE orders ADD COLUMN delivery_channel VARCHAR DEFAULT 'walk_in'"),
    ("payment_method", "ALTER TABLE orders ADD COLUMN payment_method VARCHAR DEFAULT 'pending'"),
    ("is_paid", "ALTER TABLE orders ADD COLUMN is_paid BOOLEAN DEFAULT 0"),
    ("customer_phone", "ALTER TABLE orders ADD COLUMN customer_phone VARCHAR DEFAULT ''"),
    ("notes", "ALTER TABLE orders ADD COLUMN notes TEXT DEFAULT ''"),
]

for col_name, sql in migrations:
    if col_name not in existing_cols:
        try:
            cursor.execute(sql)
            print(f"  + Added column: {col_name}")
        except sqlite3.OperationalError as e:
            print(f"  ! Skipped {col_name}: {e}")
    else:
        print(f"  = Column {col_name} already exists")

conn.commit()
conn.close()
print("\nDone! Database migrated.")
