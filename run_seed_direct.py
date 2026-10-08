import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.config import settings
# Override the database URL to use port 5432 instead of 6543 for DDL
settings.DATABASE_URL = settings.DATABASE_URL.replace(":6543", ":5432")

from app.database import engine
from scripts.seed_db import seed

# Force close existing connections
engine.dispose()
seed()
