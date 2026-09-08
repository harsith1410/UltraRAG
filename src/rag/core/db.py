import os

import sqlalchemy
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = sqlalchemy.create_engine(DATABASE_URL)

sessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def ensure_schema():
    """Idempotent column adds for tables that predate a model change.

    create_all() only creates missing tables, never alters existing ones, and the
    project has no migration tool. Safe to run on every startup.
    """
    statements = [
        "ALTER TABLE subjects ADD COLUMN IF NOT EXISTS gdrive_folder_id VARCHAR",
    ]
    with engine.begin() as conn:
        for statement in statements:
            try:
                conn.execute(sqlalchemy.text(statement))
            except Exception as e:
                print(f"schema check skipped ({statement}): {e}")
