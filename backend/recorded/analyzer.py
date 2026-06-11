import cv2
import os
import sys
import threading

# Add the 'backend' directory to sys.path so we can import from 'live'
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from live.cv_core.occupancy import ChairTracker
import torch
from ultralytics import YOLO

# Global singleton variables and lock for thread-safe initialization
_yolo_model = None
_device = None
_model_lock = threading.Lock()

def get_yolo_model():
    global _yolo_model, _device
    with _model_lock:
        if _yolo_model is None:
            _yolo_model = YOLO(os.environ.get("RECORDED_YOLO_MODEL", "yolov8m.pt"))
            _device = "cpu"
            if torch.backends.mps.is_available():
                _device = "mps"
    return _yolo_model, _device

def analyze_video(video_path: str) -> dict:
    """
    Analyzes a video file to detect seats and track occupancy using YOLO (Class 56).
    Returns:
    {
      "duration_sec": float,
      "total_seats": int,
      "seat_events": [ {"seat_id": int, "occ_start_sec": float, "occ_end_sec": float}, ... ]
    }
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")
        
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0
    duration_sec = total_frames / fps
    
    # Process every single frame to allow ChairTracker's 15-frame debounce to function accurately
    step = 1
        
    # Lazy-load the YOLO model singleton to save memory across concurrent requests
    model, device = get_yolo_model()
        
    # Instantiate the Live Part's robust ChairTracker logic
    tracker = ChairTracker(iou_threshold=0.25)
    
    frame_idx = 0
    while frame_idx < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            break
            
        timestamp_sec = frame_idx / fps
        
        try:
            results = model.predict(frame, device=device, verbose=False)
        except Exception:
            results = model.predict(frame, device="cpu", verbose=False)
            
        detected_people = []
        detected_chairs = []
        
        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                cls = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                if conf > 0.4:
                    # COCO Class 0 = Person, Class 56 = Chair
                    if cls == 0:
                        detected_people.append(box.xyxy[0].tolist())
                    elif cls == 56:
                        detected_chairs.append(box.xyxy[0].tolist())
                        
        # Feed the detections to the tracker which handles Deduplication, Two-Stage Verification, and Anti-Flapping
        tracker.update(
            detected_chairs=detected_chairs,
            detected_people=detected_people,
            current_video_time=timestamp_sec
        )
        
        frame_idx += step
        
    cap.release()
    
    # Force-close any pending state blocks in the ledger
    tracker.finalize_ledger(duration_sec)
    
    # Parse the ledger into the expected seat_events format
    seat_events = []
    total_seats = 0
    
    for seat_id, ledger in tracker.chair_time_ledger.items():
        total_seats += 1
        # Extract the raw_events that we added to the occupancy.py
        for evt in ledger.get("raw_events", []):
            seat_events.append({
                "seat_id": seat_id,
                "occ_start_sec": float(evt["occ_start_sec"]),
                "occ_end_sec": float(evt["occ_end_sec"])
            })
            
    return {
        "duration_sec": float(duration_sec),
        "total_seats": int(total_seats),
        "seat_events": seat_events
    }
