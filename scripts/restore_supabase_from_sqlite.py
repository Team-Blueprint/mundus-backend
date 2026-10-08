import os
import sys
import sqlite3
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.database import Base

def restore():
    sqlite_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mundus.db"))
    if not os.path.exists(sqlite_path):
        print(f"Error: {sqlite_path} not found!")
        return

    supabase_url = settings.DATABASE_URL
    if "sqlite" in supabase_url:
        print("Settings currently point to SQLite. Make sure DATABASE_URL is set to Supabase in .env or app/config.py.")
        return

    print(f"Reading records from local SQLite: {sqlite_path}")
    sq_conn = sqlite3.connect(sqlite_path)
    sq_conn.row_factory = sqlite3.Row
    sq_cur = sq_conn.cursor()

    print(f"Connecting to Supabase PostgreSQL...")
    engine = create_engine(supabase_url)
    
    # Ensure tables exist on Supabase
    Base.metadata.create_all(bind=engine)

    # Order of tables to respect foreign keys
    tables_order = [
        "users",
        "contractors",
        "reporters",
        "dump_points",
        "check_ins",
        "reporter_flags",
        "contractor_alerts",
        "password_reset_tokens",
        "agency_access_requests",
        "device_tokens",
    ]

    with engine.begin() as pg_conn:
        for table in tables_order:
            try:
                sq_cur.execute(f"SELECT * FROM {table}")
                rows = sq_cur.fetchall()
                if not rows:
                    print(f"  [{table}] No rows to sync.")
                    continue

                cols = rows[0].keys()
                cols_str = ", ".join([f'"{c}"' for c in cols])
                vals_placeholders = ", ".join([f":{c}" for c in cols])
                insert_stmt = text(f'INSERT INTO "{table}" ({cols_str}) VALUES ({vals_placeholders}) ON CONFLICT DO NOTHING')

                data = [dict(row) for row in rows]
                pg_conn.execute(insert_stmt, data)
                print(f"  [{table}] Synced {len(data)} rows to Supabase.")
            except Exception as e:
                print(f"  [{table}] Notice/Skipped: {e}")

    print("\n✅ Restore from SQLite to Supabase completed successfully!")

if __name__ == "__main__":
    restore()
