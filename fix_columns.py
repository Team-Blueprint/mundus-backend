import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS email VARCHAR(255);"))
        conn.execute(text("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS user_id INTEGER;"))
        conn.commit()
    print("Successfully added missing columns to contractors.")
except Exception as e:
    print(f"Error: {e}")

