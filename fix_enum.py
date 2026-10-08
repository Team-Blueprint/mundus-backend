import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TYPE userrole ADD VALUE 'CONTRACTOR';"))
        conn.commit()
    print("Successfully added CONTRACTOR to userrole enum.")
except Exception as e:
    print(f"Error: {e}")

