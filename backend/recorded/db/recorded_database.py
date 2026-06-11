import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("RECORDED_DB_PATH", "backend/recorded.db")

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        video_duration_sec REAL NOT NULL,
        total_seats INTEGER NOT NULL,
        analyzed_at TEXT NOT NULL,
        status TEXT DEFAULT 'completed'
    );
    """)
    # Migration for existing databases
    try:
        cursor.execute("ALTER TABLE sessions ADD COLUMN status TEXT DEFAULT 'completed'")
    except sqlite3.OperationalError:
        pass # Column likely already exists

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS seat_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL REFERENCES sessions(id),
        seat_id INTEGER NOT NULL,
        occ_start_sec REAL NOT NULL,
        occ_end_sec REAL NOT NULL
    );
    """)
    conn.commit()
    conn.close()

def insert_session(filename: str, video_duration_sec: float, total_seats: int, status: str = "completed") -> int:
    conn = get_db()
    cursor = conn.cursor()
    analyzed_at = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO sessions (filename, video_duration_sec, total_seats, analyzed_at, status) VALUES (?, ?, ?, ?, ?)",
        (filename, video_duration_sec, total_seats, analyzed_at, status)
    )
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return session_id

def insert_seat_events(session_id: int, events: list):
    conn = get_db()
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT INTO seat_events (session_id, seat_id, occ_start_sec, occ_end_sec) VALUES (?, ?, ?, ?)",
        [(session_id, e["seat_id"], e["occ_start_sec"], e["occ_end_sec"]) for e in events]
    )
    conn.commit()
    conn.close()

def update_session(session_id: int, video_duration_sec: float, total_seats: int, status: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET video_duration_sec = ?, total_seats = ?, status = ? WHERE id = ?",
        (video_duration_sec, total_seats, status, session_id)
    )
    conn.commit()
    conn.close()

def get_session(session_id: int) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, filename, video_duration_sec, total_seats, analyzed_at, status FROM sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_events_for_session(session_id: int) -> list:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT seat_id, occ_start_sec, occ_end_sec FROM seat_events WHERE session_id = ? ORDER BY seat_id, occ_start_sec", (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_sessions() -> list:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, filename, analyzed_at, total_seats, status FROM sessions ORDER BY analyzed_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
