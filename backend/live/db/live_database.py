import sqlite3
import os
import threading
import logging

logger = logging.getLogger(__name__)

# Tests can override this via os.environ if needed, but it's often 
# easier for the test runner to patch _DB_PATH directly.
_DB_PATH = os.environ.get("LIVE_DB_PATH", "backend/live.db")

# Thread-local storage for DB connections (useful for FastAPI thread pool)
_local = threading.local()

def get_db() -> sqlite3.Connection:
    """
    Returns a thread-local singleton connection.
    check_same_thread=False allows FastAPI and background threads to use SQLite.
    """
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        # Enable dictionary-like access to rows
        _local.conn.row_factory = sqlite3.Row
    return _local.conn

def init_db():
    """
    Initializes the database schema. Safe to call on startup.
    Uses individual execute() + explicit commit() for Python 3.12+ compatibility.
    """
    conn = get_db()
    
    # Enable WAL mode and foreign keys.
    # WAL is persisted in DB file, but good practice to assert it on startup.
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seats (
            seat_id      INTEGER PRIMARY KEY,
            display_name TEXT    NOT NULL,
            x1           INTEGER,
            y1           INTEGER,
            x2           INTEGER,
            y2           INTEGER,
            created_at   TEXT DEFAULT (datetime('now'))
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analysis_sessions (
            session_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            video_source TEXT NOT NULL,
            started_at   TEXT DEFAULT (datetime('now')),
            ended_at     TEXT
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS occupancy_events (
            event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER REFERENCES analysis_sessions(session_id),
            seat_id     INTEGER REFERENCES seats(seat_id),
            status      TEXT CHECK(status IN ('occupied','vacant')) NOT NULL,
            recorded_at TEXT DEFAULT (datetime('now')),
            ended_at    TEXT
        )
    """)
    
    conn.commit()
    logger.info(f"SQLite schema initialized at {_DB_PATH} (WAL mode active)")

def hydrate_state_store(store):
    """
    Reads the 'seats' table and populates the in-memory StateStore
    on application startup.
    """
    conn = get_db()
    cursor = conn.execute("SELECT seat_id, display_name, x1, y1, x2, y2 FROM seats")
    rows = cursor.fetchall()
    
    hydrated_count = 0
    with store._lock:
        store._registered_seats.clear()
        for row in rows:
            store._registered_seats[row["seat_id"]] = {
                "seat_id": row["seat_id"],
                "display_name": row["display_name"],
                "bbox": (row["x1"], row["y1"], row["x2"], row["y2"])
            }
            hydrated_count += 1
            
        # Optional: Initialize dynamic seats based on registered ones
        # Though the CV loop will do this on its first frame anyway.
        store._seats = {
            s_id: {**data, "status": "vacant", "duration_occupied": "0s"} 
            for s_id, data in store._registered_seats.items()
        }
    logger.info(f"Hydrated StateStore with {hydrated_count} seats from SQLite.")
