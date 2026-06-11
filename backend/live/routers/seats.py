from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime, timezone

# Import our strictly typed JSON schemas
from backend.schemas import (
    SeatRegisterRequest, 
    SeatRegisterResponse, 
    SeatStatusResponse, 
    SeatHistoryResponse
)

router = APIRouter(prefix="/seats", tags=["seats"])

# Utilize FastAPI dependency injection to avoid Python circular imports 
# while retrieving the live global state.
def get_store():
    from backend.main import live_store as store
    return store

@router.get("", response_model=List[SeatStatusResponse])
def get_all_seats(store = Depends(get_store)):
    """
    Returns the real-time aggregated snapshot of all known seats.
    Queries the centralized thread-safe CV StateStore natively.
    """
    try:
        return store.get_all_seats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=SeatRegisterResponse)
def register_seat(payload: SeatRegisterRequest, store = Depends(get_store)):
    """
    Registers the bounding boxes drawn by the client dynamically.
    The asynchronous CV loop will pick this up mathematically on its next cycle.
    """
    from backend.live.db.live_database import get_db
    conn = get_db()
    try:
        display_name = payload.display_name if payload.display_name and payload.display_name.strip() else None
        cursor = conn.execute(
            "INSERT INTO seats (display_name, x1, y1, x2, y2) VALUES (COALESCE(?, 'Seat'), ?, ?, ?, ?)",
            (display_name, int(payload.bbox[0]), int(payload.bbox[1]), int(payload.bbox[2]), int(payload.bbox[3]))
        )
        conn.commit()
        seat_id = cursor.lastrowid
        
        # Give default name if none provided
        if not display_name:
            display_name = f"Seat {seat_id}"
            conn.execute("UPDATE seats SET display_name = ? WHERE seat_id = ?", (display_name, seat_id))
            conn.commit()
            
        store.register_seat(bbox=tuple(payload.bbox), display_name=display_name, seat_id=seat_id)
        return SeatRegisterResponse(seat_id=seat_id, display_name=display_name, registered=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")

@router.get("/{seat_id}/history")
def get_seat_history(seat_id: int, store = Depends(get_store)):
    """
    Returns the timeline history for the given seat within the most recent session.
    """
    # Verify the seat exists within our active dictionary state first
    seats_dict = store.get_seats_bbox_dict()
    if seat_id not in seats_dict:
        raise HTTPException(status_code=404, detail="Seat not found")
        
    from backend.live.db.live_database import get_db
    conn = get_db()
    
    # 1. Find the latest session
    session_cursor = conn.execute(
        """
        SELECT 
            session_id, 
            started_at,
            CAST(ROUND((julianday(COALESCE(ended_at, datetime('now'))) - julianday(started_at)) * 86400) AS INTEGER) AS session_duration_seconds
        FROM analysis_sessions
        ORDER BY session_id DESC LIMIT 1
        """
    )
    session = session_cursor.fetchone()
    
    if not session:
        return {
            "seat_id": seat_id,
            "session_duration_seconds": 0,
            "events": []
        }
        
    session_id = session["session_id"]
    started_at = session["started_at"]
    session_duration_seconds = max(0, session["session_duration_seconds"])
    
    # 2. Find events for this seat in the session
    events_cursor = conn.execute(
        """
        SELECT 
            status,
            CAST(ROUND((julianday(recorded_at) - julianday(?)) * 86400) AS INTEGER) as start_sec,
            CAST(ROUND((julianday(COALESCE(ended_at, datetime('now'))) - julianday(?)) * 86400) AS INTEGER) as end_sec
        FROM occupancy_events
        WHERE session_id = ? AND seat_id = ?
        ORDER BY recorded_at ASC
        """,
        (started_at, started_at, session_id, seat_id)
    )
    
    events = []
    for row in events_cursor.fetchall():
        start_sec = max(0, row["start_sec"])
        end_sec = max(start_sec, row["end_sec"])
        
        # Helper to format seconds as MM:SS or HH:MM:SS
        def format_sec(s):
            h = s // 3600
            m = (s % 3600) // 60
            sec = s % 60
            if h > 0:
                return f"{h:02d}:{m:02d}:{sec:02d}"
            return f"{m:02d}:{sec:02d}"
            
        events.append({
            "status": row["status"],
            "start": format_sec(start_sec),
            "end": format_sec(end_sec),
            "start_sec": start_sec,
            "end_sec": end_sec
        })
        
    return {
        "seat_id": seat_id,
        "session_duration_seconds": session_duration_seconds,
        "events": events
    }

@router.delete("/{seat_id}")
def delete_seat(seat_id: int, store = Depends(get_store)):
    """
    Removes a seat entirely from StateStore and SQLite database.
    """
    from backend.live.db.live_database import get_db
    conn = get_db()
    try:
        cursor = conn.execute("DELETE FROM seats WHERE seat_id = ?", (seat_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Seat not found")
            
        removed = store.remove_seat(seat_id)
        return {"seat_id": seat_id, "deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def parse_time_to_seconds(time_str: str) -> int:
    parts = time_str.strip().split(':')
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0

@router.get("/export/csv")
def export_seats_csv(store = Depends(get_store)):
    """
    Exports the transition history ledger as a CSV file.
    Reads directly from the occupancy_events table.
    """
    from fastapi.responses import StreamingResponse
    import io
    import csv
    from backend.main import global_tracker
    from backend.live.db.live_database import get_db

    # Finalize any open ledger items so they are flushed to DB
    if global_tracker is not None:
        global_tracker.finalize_ledger(global_tracker.current_video_time)
        store.update_dynamic_seats(global_tracker.tracked_chairs)

    conn = get_db()
    cursor = conn.execute(
        """
        SELECT 
            seat_id, status, recorded_at, ended_at,
            CAST(ROUND((julianday(COALESCE(ended_at, datetime('now'))) - julianday(recorded_at)) * 86400) AS INTEGER) as duration_seconds
        FROM occupancy_events
        ORDER BY seat_id ASC, recorded_at ASC
        """
    )
    rows = cursor.fetchall()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["seat_id", "status", "start_time", "end_time", "duration_seconds"])

    for row in rows:
        writer.writerow([
            row["seat_id"], 
            row["status"], 
            row["recorded_at"], 
            row["ended_at"] if row["ended_at"] else "", 
            max(0, row["duration_seconds"] or 0)
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="chronosdesk_export.csv"'}
    )


