from backend.main import start_cv_pipeline, halt_cv_pipeline
import asyncio
import os
import time
import shutil
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

# Set prefix to empty so we can house both /ws and /stream routes cleanly
router = APIRouter(prefix="", tags=["stream"])

class SourcePayload(BaseModel):
    source: str

def get_live_state():
    from backend.main import live_store as store, start_cv_pipeline, system_events, current_frame
    return store, system_events

def trigger_cv_pipeline():
    try:
        start_cv_pipeline()
    except Exception as e:
        logger.error(f"Failed to trigger CV pipeline: {e}")

def halt_cv_pipeline():
    try:
        from backend.main import cv_stop_event
        cv_stop_event.set()
    except Exception as e:
        logger.error(f"Failed to halt CV pipeline: {e}")

@router.websocket("/ws/occupancy")
async def occupancy_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("Live dashboard connected to /ws/occupancy")
    
    store, system_events = get_live_state()
    import backend.main as main_module
    last_counter = main_module.system_events_counter
    
    try:
        while True:
            current_counter = main_module.system_events_counter
            # Check for any new stream failures pushed by CV core thread
            if current_counter > last_counter:
                new_events_count = current_counter - last_counter
                for event in system_events[-new_events_count:]:
                    await websocket.send_json(event)
                last_counter = current_counter
                
            else:
                current_seats = store.get_all_seats()
                seats_out = [
                    {
                        "seat_id": seat["seat_id"],
                        "display_name": seat.get("display_name"),
                        "status": seat["status"],
                        "bbox": seat["bbox"],
                        "sat_at": seat["sat_at"],
                        "duration": seat["duration"],
                        "history": seat.get("history", [])
                    }
                    for seat in current_seats
                ]
                
                payload = {
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "seats": seats_out
                }
                
                await websocket.send_json(payload)

                
            await asyncio.sleep(1.0)
            
    except WebSocketDisconnect:
        logger.info("Dashboard cleanly unmounted occupancy WebSocket.")
        halt_cv_pipeline()
    except Exception as e:
        logger.error(f"Terminating WS unexpectedly: {e}")


@router.get("/stream/live")
def stream_live():
    """
    HTTP MJPEG streaming endpoint for displaying real-time annotated frame previews in frontend.
    """
    store, _ = get_live_state()
    
    def frame_generator():
        while True:
            frame_bytes = store.get_latest_frame()
            if frame_bytes is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            # Loop at ~25 FPS to keep network overhead low
            time.sleep(0.04)
            
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/stream/videos")
def get_available_videos():
    """
    Scans the videos/ folder and returns a list of compatible video files.
    """
    videos_dir = os.path.join(os.getcwd(), "videos")
    if not os.path.exists(videos_dir):
        return []
    
    try:
        files = os.listdir(videos_dir)
        return [f for f in files if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
    except Exception as e:
        logger.error(f"Failed to read videos directory: {e}")
        return []


@router.post("/stream/source")
def update_stream_source(payload: SourcePayload):
    """
    Switches the live background CV pipeline source dynamically.
    """
    store, _ = get_live_state()
    source = payload.source
    
    if source == "0":
        # Integer 0 represents default local camera (webcam)
        active_source = 0
    else:
        # Prepend videos/ directory mapping if it is a relative filename from selector
        if not (source.startswith("/") or source.startswith("rtsp://") or source.startswith("http://") or source.startswith("https://")):
            active_source = os.path.join("videos", source)
        else:
            active_source = source
            
    store.set_stream_url(active_source)
    logger.info(f"Switched background stream to source: {active_source}")
    store.reset_occupancy_state()
    trigger_cv_pipeline()
    return {"status": "success", "active_source": str(active_source)}


@router.post("/stream/upload")
def upload_video_file(file: UploadFile = File(...)):
    """
    Receives video file uploads from frontend browser, stores it in videos/,
    and instantly redirects the CV pipeline to run against it.
    """
    store, _ = get_live_state()
    videos_dir = os.path.join(os.getcwd(), "videos")
    os.makedirs(videos_dir, exist_ok=True)
    
    target_path = os.path.join(videos_dir, file.filename)
    try:
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        relative_source = os.path.join("videos", file.filename)
        store.set_stream_url(relative_source)
        logger.info(f"Uploaded video '{file.filename}' and set stream source.")
        store.reset_occupancy_state()
        trigger_cv_pipeline()
        return {"status": "success", "filename": file.filename, "active_source": relative_source}
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/stream/start")
def start_stream():
    trigger_cv_pipeline()
    return {"status": "success"}

@router.post("/stream/stop")
def stop_stream():
    halt_cv_pipeline()
    return {"status": "success"}
