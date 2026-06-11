from fastapi import APIRouter, UploadFile, File, Query, BackgroundTasks
import os
import tempfile
import asyncio
import logging
from backend.recorded.db.recorded_database import insert_session, insert_seat_events, update_session
from backend.recorded.analyzer import analyze_video

logger = logging.getLogger(__name__)

router = APIRouter()

def generate_mock_data(filename: str):
    """
    Generates realistic, deterministic mock occupancy data for testing.
    4 seats, 120-second video.
    """
    duration_sec = 120.0
    total_seats = 4
    events = [
        {"seat_id": 1, "occ_start_sec": 10.0, "occ_end_sec": 45.5},
        {"seat_id": 1, "occ_start_sec": 65.0, "occ_end_sec": 110.0},
        {"seat_id": 2, "occ_start_sec": 5.0, "occ_end_sec": 80.2},
        {"seat_id": 3, "occ_start_sec": 30.5, "occ_end_sec": 95.0},
        {"seat_id": 4, "occ_start_sec": 0.0, "occ_end_sec": 15.0},
        {"seat_id": 4, "occ_start_sec": 50.0, "occ_end_sec": 118.5}
    ]
    return duration_sec, total_seats, events

def analyze_video_task(session_id: int, temp_path: str, filename: str):
    try:
        result = analyze_video(temp_path)
        update_session(
            session_id, 
            result["duration_sec"], 
            result["total_seats"],
            "completed"
        )
        insert_seat_events(session_id, result["seat_events"])
    except Exception as e:
        logger.error(f"Analysis failed for session {session_id}: {e}")
        update_session(session_id, 0.0, 0, "failed")
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

@router.post("/analyze")
async def analyze(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(..., description="Video file to analyze"),
    mock: bool = Query(False, description="Use mock data")
):
    if mock:
        duration_sec, total_seats, events = generate_mock_data(video.filename)
        session_id = insert_session(video.filename, duration_sec, total_seats, status="completed")
        insert_seat_events(session_id, events)
        return {
            "session_id": session_id,
            "total_seats": total_seats,
            "duration_sec": duration_sec,
            "status": "completed"
        }

    # Save UploadFile to a temp file
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, video.filename)
    
    with open(temp_path, "wb") as f:
        while chunk := await video.read(1024 * 1024):
            f.write(chunk)
            
    session_id = insert_session(video.filename, 0.0, 0, status="processing")
    
    background_tasks.add_task(analyze_video_task, session_id, temp_path, video.filename)
    
    return {
        "session_id": session_id,
        "total_seats": 0,
        "duration_sec": 0.0,
        "status": "processing"
    }
