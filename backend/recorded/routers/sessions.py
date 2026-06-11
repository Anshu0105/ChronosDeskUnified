from fastapi import APIRouter, HTTPException, Response
import io
import csv
from backend.recorded.db.recorded_database import get_session, get_events_for_session, get_sessions

router = APIRouter()

@router.get("/sessions")
def list_sessions():
    """
    Returns list of all sessions ordered by analyzed_at DESC.
    """
    return get_sessions()

@router.get("/sessions/{session_id}")
def get_session_detail(session_id: int):
    """
    Returns the details of a session and its events list.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    events = get_events_for_session(session_id)
    return {
        "session": session,
        "events": events
    }

@router.get("/sessions/{session_id}/export")
def export_session_csv(session_id: int):
    """
    Generates and returns a CSV file of the session occupancy events.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    events = get_events_for_session(session_id)
    
    # Generate CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    # Header row
    writer.writerow(["seat_id", "occ_start_sec", "occ_end_sec", "occupied_duration_sec"])
    # Data rows
    for event in events:
        start = event["occ_start_sec"]
        end = event["occ_end_sec"]
        duration = round(end - start, 2)
        writer.writerow([event["seat_id"], start, end, duration])
        
    csv_data = output.getvalue()
    output.close()
    
    headers = {
        "Content-Disposition": f"attachment; filename=session_{session_id}.csv"
    }
    return Response(content=csv_data, media_type="text/csv", headers=headers)
