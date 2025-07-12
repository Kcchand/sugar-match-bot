# database.py
import sqlite3
import logging

logger = logging.getLogger(__name__)

DB_NAME = "sugar_match.db"

def get_conn():
    """Return a SQLite connection (shared thread)."""
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    """Create tables if they don't exist."""
    conn = get_conn()
    cur = conn.cursor()

    # Full table definition with new columns
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id     INTEGER PRIMARY KEY,
        role            TEXT,
        username        TEXT,
        name            TEXT,
        age             INTEGER,
        bio             TEXT,
        photo_file_id   TEXT,
        payment_proof   TEXT,
        location_text   TEXT,
        lat             REAL,
        lon             REAL,
        approved        INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        woman_id     INTEGER,
        customer_id  INTEGER,
        status       TEXT
    )
    """)

    conn.commit()

def ensure_columns():
    """Add new columns to the users table if they are missing (zero‑downtime migration)."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(users)")
    existing_cols = {row[1] for row in cur.fetchall()}

    # Columns we must have
    required = [
        ("location_text", "TEXT"),
        ("lat",           "REAL"),
        ("lon",           "REAL"),
    ]

    for col_name, col_type in required:
        if col_name not in existing_cols:
            logger.info("Adding missing column %s to users table", col_name)
            cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")

    conn.commit()

# Run creation and migration on import
init_db()
ensure_columns()
