import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import threading

from backend.config import settings
from backend.live.cv_core.state_store import StateStore
from backend.live.cv_core.stream_reader import StreamReader
from backend.live.cv_core.detector import YOLODetector
from backend.live.cv_core.occupancy import resolve_seat_assignments

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances to be imported by our routers
live_store = StateStore()
live_store.set_stream_url(settings.stream_url)
system_events = [] # Lightweight queue buffer for streaming errors
system_events_counter = 0
global_tracker = None
current_frame = None

cv_thread_lock = threading.Lock()
cv_thread = None
cv_stop_event = threading.Event()

global_reader = None

def run_cv_pipeline():
    """
    Synchronous blocking loop that continuously feeds frames through the AI framework.
    """
    import cv2
    from backend.live.cv_core.occupancy import ChairTracker, draw_occupancy_preview
    from backend.live.db.live_database import get_db
    global global_tracker
    global current_frame
    global global_reader
    global system_events_counter
    
    conn = get_db()
    stream_url = live_store.get_stream_url()
    
    # Start analysis session
    try:
        cursor = conn.execute(
            "INSERT INTO analysis_sessions (video_source) VALUES (?)",
            (str(stream_url),)
        )
        conn.commit()
        live_store.current_session_id = cursor.lastrowid
        logger.info(f"Started analysis session {live_store.current_session_id} for source {stream_url}")
    except Exception as e:
        logger.error(f"Failed to start analysis session in DB: {e}")
    
    reader = StreamReader(stream_url=stream_url, state_store=live_store)
    global_reader = reader
    detector = YOLODetector(model_path=settings.yolo_model, conf_threshold=settings.min_detection_confidence)
    tracker = ChairTracker(iou_threshold=settings.occupancy_iou_threshold)
    global_tracker = tracker
    
    logger.info("Background CV Pipeline thread activated.")
    
    _bootstrap_frames = []
    _bootstrapped = False
    
    # Capture the current event object so this thread knows when to stop,
    # even if the global cv_stop_event is reassigned.
    current_stop_event = cv_stop_event

    frame_count = 0
    for frame, error_event in reader.read_frames():
        frame_count += 1
        if current_stop_event.is_set():
            logger.info("CV Pipeline stop event detected. Exiting loop.")
            break
            
        if frame is None:
            # Pass the error payload down the line to be consumed by the WebSocket endpoint
            if error_event:
                system_events.append(error_event)
                system_events_counter += 1
                if len(system_events) > 500:
                    system_events.pop(0)
            continue

        if frame_count % 3 != 0:
            continue

        if not _bootstrapped:
            _bootstrap_frames.append(frame)
            if len(_bootstrap_frames) >= 3:
                consensus_boxes = detector.detect_chairs_consensus(_bootstrap_frames, min_votes=2)
                if consensus_boxes:
                    tracker.seat_registry.register_all(consensus_boxes)
                _bootstrapped = True
            continue  # skip normal processing until bootstrap is done
            
        people_boxes, chair_boxes = detector.detect_objects(frame)
        
        # Run tracker to update dynamic chairs and detect sitting events
        registered = live_store.get_registered_seats()
        tracked_chairs = tracker.update(
            chair_boxes,
            people_boxes,
            current_video_time=reader.current_video_time,
            registered_seats=registered
        )
        live_store.update_dynamic_seats(tracked_chairs)
            
        # Draw and encode current annotated frame for frontend preview streaming
        annotated = draw_occupancy_preview(frame, tracked_chairs, people_boxes)
        current_frame = annotated
        ret, jpeg = cv2.imencode('.jpg', annotated)
        if ret:
            live_store.set_latest_frame(jpeg.tobytes())

    # When the loop exits, finalize the ledger and store state
    total_duration = reader.total_video_duration
    if total_duration <= 0.0:
        total_duration = reader.current_video_time
    tracker.finalize_ledger(total_duration)
    live_store.update_dynamic_seats(tracker.tracked_chairs)

    # End analysis session and any open events
    if live_store.current_session_id is not None:
        try:
            conn.execute(
                "UPDATE analysis_sessions SET ended_at = datetime('now') WHERE session_id = ?",
                (live_store.current_session_id,)
            )
            conn.execute(
                "UPDATE occupancy_events SET ended_at = datetime('now') WHERE session_id = ? AND ended_at IS NULL",
                (live_store.current_session_id,)
            )
            conn.commit()
            logger.info(f"Ended analysis session {live_store.current_session_id}")
        except Exception as e:
            logger.error(f"Failed to end analysis session in DB: {e}")


def start_cv_pipeline():
    global cv_thread, cv_stop_event
    with cv_thread_lock:
        if cv_thread is not None and cv_thread.is_alive():
            logger.info("Stopping existing CV Pipeline thread...")
            cv_stop_event.set()          # signals the currently running thread's captured reference
            cv_thread.join(timeout=5.0)  # give it slightly more time to release VideoCapture
            cv_stop_event.clear()        # reuse the same event object — do NOT reassign it
            if cv_thread.is_alive():
                logger.warning("CV Pipeline thread did not exit cleanly within timeout. Abandoning capture release to prevent segfault.")
            else:
                if global_reader is not None:
                    try:
                        if global_reader.cap is not None:
                            global_reader.cap.release()
                            global_reader.cap = None
                            import time
                            time.sleep(1.0)  # Allow macOS AVFoundation to release hardware
                    except Exception as e:
                        logger.warning(f"Could not release old VideoCapture: {e}")
        
        cv_thread = threading.Thread(target=run_cv_pipeline, daemon=True)
        cv_thread.start()
        logger.info("Started new background CV Pipeline thread.")


def halt_cv_pipeline():
    global cv_thread, cv_stop_event
    with cv_thread_lock:
        if cv_thread is not None and cv_thread.is_alive():
            logger.info("Halting CV Pipeline thread...")
            cv_stop_event.set()
            cv_thread.join(timeout=5.0)
            cv_stop_event.clear()
            if cv_thread.is_alive():
                logger.warning("CV Pipeline thread did not exit cleanly within timeout. Abandoning capture release to prevent segfault.")
            else:
                if global_reader is not None:
                    try:
                        if global_reader.cap is not None:
                            global_reader.cap.release()
                            global_reader.cap = None
                            import time
                            time.sleep(1.0)  # Allow macOS AVFoundation to release hardware
                    except Exception as e:
                        logger.warning(f"Could not release VideoCapture: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event to manage our background CV process logically.
    """
    from backend.live.db.live_database import init_db as init_live_db, hydrate_state_store
    from backend.recorded.db.recorded_database import init_db as init_recorded_db
    init_live_db()
    init_recorded_db()
    hydrate_state_store(live_store)
    
    start_cv_pipeline()
    
    yield
    
    logger.info("FastAPI termination sequence initiated.")

def create_app() -> FastAPI:
    app = FastAPI(title="ChronosDeskBackend", lifespan=lifespan)

    # CORS Configuration utilizing .env restrictions
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def health_check():
        return {"status": "ok", "service": "ChronosDeskUnified"}
        
    from backend.live.routers import seats, stream
    from backend.recorded.routers import analyze, sessions

    app.include_router(seats.router, prefix="/live", tags=["live-seats"])
    app.include_router(stream.router, prefix="/live", tags=["live-stream"])
    app.include_router(analyze.router, prefix="/recorded", tags=["recorded-analyze"])
    app.include_router(sessions.router, prefix="/recorded", tags=["recorded-sessions"])

    return app

app = create_app()
