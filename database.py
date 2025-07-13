import sqlite3, logging, time
logger = logging.getLogger(__name__)

DB_NAME = "sugar_match.db"

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id    INTEGER PRIMARY KEY,
        role           TEXT,
        username       TEXT,
        name           TEXT,
        age            INTEGER,
        bio            TEXT,
        phone_number   TEXT,
        photo_file_id  TEXT,
        payment_proof  TEXT,
        location_text  TEXT,
        lat            REAL,
        lon            REAL,
        approved       INTEGER DEFAULT 0,
        approved_at    INTEGER          -- Unix timestamp
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
    conn = get_conn(); cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in cur.fetchall()}
    for name, ctype in [
        ("phone_number", "TEXT"),
        ("location_text", "TEXT"),
        ("lat", "REAL"),
        ("lon", "REAL"),
        ("approved_at", "INTEGER"),
    ]:
        if name not in cols:
            logger.info("Adding column %s", name)
            cur.execute(f"ALTER TABLE users ADD COLUMN {name} {ctype}")
    conn.commit()

init_db()
ensure_columns()
