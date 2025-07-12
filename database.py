# database.py
# Placeholder module
# database.py
import sqlite3

def get_conn():
    return sqlite3.connect("sugar_match.db", check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        role        TEXT,
        username    TEXT,
        name        TEXT,
        age         INTEGER,
        bio         TEXT,
        photo_file_id TEXT,
        payment_proof TEXT,
        approved    INTEGER DEFAULT 0,
        lat REAL, lon REAL
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

init_db()
