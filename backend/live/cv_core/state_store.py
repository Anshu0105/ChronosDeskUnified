import logging
from typing import Dict, Tuple, List, Optional
from threading import Lock

logger = logging.getLogger(__name__)

class StateStore:
    """
    In-memory storage for seat configurations and their real-time occupancy status.
    Thread-safe to allow concurrent reads from FastAPI and updates from the CV loop.
    """

    def __init__(self):
        # Maps seat_id (int) -> {"bbox": (x1, y1, x2, y2), "status": "unknown", "display_name": "Seat {id}"}
        self._seats: Dict[int, dict] = {}
        self._registered_seats: Dict[int, dict] = {}
        self._stream_url: str | int = "0"
        self._latest_frame: Optional[bytes] = None
        self.current_session_id: Optional[int] = None
        # Using a lock since the FastAPI websocket loop will read this while CV loop writes to it
        self._lock = Lock()

    def set_stream_url(self, url: str | int) -> None:
        with self._lock:
            self._stream_url = url
            
    def get_stream_url(self) -> str | int:
        with self._lock:
            return self._stream_url

    def set_latest_frame(self, frame_bytes: bytes) -> None:
        with self._lock:
            self._latest_frame = frame_bytes

    def get_latest_frame(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_frame

    def register_seat(self, bbox: Tuple[float, float, float, float], display_name: Optional[str] = None, seat_id: Optional[int] = None) -> int:
        """
        Registers a new seat with its bounding box coordinates.
        Initial status defaults to 'unknown'.
        """
        with self._lock:
            if seat_id is None:
                next_id = 1
                if self._registered_seats:
                    next_id = max(self._registered_seats.keys()) + 1
            else:
                next_id = seat_id
            
            actual_display_name = display_name if display_name and display_name.strip() else f"Seat {next_id}"
            
            self._seats[next_id] = {
                "bbox": bbox,
                "status": "unknown",
                "display_name": actual_display_name
            }
            self._registered_seats[next_id] = {
                "bbox": bbox,
                "display_name": actual_display_name
            }
        logger.info(f"Seat {next_id} registered with display_name '{actual_display_name}' and bbox {bbox}")
        return next_id

    def update_status(self, updates: Dict[int, bool]) -> None:
        """
        Bulk updates the occupancy status based on the CV pipeline results.
        
        :param updates: Dictionary mapping seat_id to a boolean (True=occupied).
        """
        with self._lock:
            for seat_id, is_occupied in updates.items():
                if seat_id in self._seats:
                    self._seats[seat_id]["status"] = "occupied" if is_occupied else "vacant"
                    
    def set_all_unknown(self) -> None:
        """
        Used during stream failure/disconnect to prevent broadcasting stale data bridging.
        """
        with self._lock:
            for seat_id in self._seats:
                self._seats[seat_id]["status"] = "unknown"
        logger.warning("All seat statuses reset to 'unknown'.")

    def reset_occupancy_state(self) -> None:
        """
        Resets occupancy state (statuses, durations, transition histories, frame/tracker memory)
        while preserving manually registered seat bounding boxes.
        """
        with self._lock:
            self._seats = {
                seat_id: {
                    "bbox": info["bbox"],
                    "status": "unknown",
                    "display_name": info["display_name"],
                    "sat_at": None,
                    "duration": "0s",
                    "history": []
                }
                for seat_id, info in self._registered_seats.items()
            }
            self._latest_frame = None
        logger.info("Occupancy state reset. Restored registered seats.")

    def get_all_seats(self) -> List[dict]:
        """
        Returns a list of all current seat states for the REST/WebSocket API payload.
        Format: [{'seat_id': 1, 'display_name': 'Seat 1', 'bbox': [x,y,x,y], 'status': 'occupied', 'sat_at': timestamp, 'duration': float}]
        """
        with self._lock:
            return [
                {
                    "seat_id": seat_id,
                    "display_name": data.get("display_name", f"Seat {seat_id}"),
                    "bbox": list(data["bbox"]),
                    "status": data["status"],
                    "sat_at": data.get("sat_at"),
                    "duration": data.get("duration", 0.0),
                    "history": data.get("history", [])
                }
                for seat_id, data in self._seats.items()
            ]

    def update_dynamic_seats(self, tracked_chairs: List[dict]) -> None:
        """
        Updates the store dynamically using chairs tracked by YOLO.
        """
        from backend.live.db.live_database import get_db
        conn = get_db()
        
        with self._lock:
            for chair in tracked_chairs:
                seat_id = chair["seat_id"]
                new_status = chair["status"]
                
                # Check for status transition
                if seat_id in self._seats:
                    old_status = self._seats[seat_id]["status"]
                    if old_status != new_status and new_status in ("occupied", "vacant"):
                        if self.current_session_id is not None:
                            try:
                                conn.execute(
                                    "UPDATE occupancy_events SET ended_at = datetime('now') WHERE seat_id = ? AND ended_at IS NULL",
                                    (seat_id,)
                                )
                                conn.execute(
                                    "INSERT INTO occupancy_events (session_id, seat_id, status) VALUES (?, ?, ?)",
                                    (self.current_session_id, seat_id, new_status)
                                )
                                conn.commit()
                            except Exception as e:
                                logger.error(f"Failed to log occupancy event for seat {seat_id}: {e}")

            self._seats = {
                chair["seat_id"]: {
                    "bbox": chair["bbox"],
                    "status": chair["status"],
                    "sat_at": chair.get("sat_at"),
                    "duration": chair.get("duration", 0.0),
                    "history": chair.get("transition_history", []),
                    "display_name": self._registered_seats[chair["seat_id"]]["display_name"] if chair["seat_id"] in self._registered_seats else f"Seat {chair['seat_id']}"
                }
                for chair in tracked_chairs
            }

    def get_seats_bbox_dict(self) -> Dict[int, Tuple[float, float, float, float]]:
        """
        Extracts a dictionary of seat_id -> bbox.
        Used natively by the occupancy logic algorithms.
        """
        with self._lock:
            return {
                seat_id: data["bbox"]
                for seat_id, data in self._seats.items()
            }

    def remove_seat(self, seat_id: int) -> bool:
        """
        Removes a seat entirely from StateStore (both registered_seats and seats).
        """
        with self._lock:
            removed = False
            if seat_id in self._seats:
                del self._seats[seat_id]
                removed = True
            if seat_id in self._registered_seats:
                del self._registered_seats[seat_id]
                removed = True
            return removed

    def get_registered_seats(self) -> Dict[int, dict]:
        """
        Returns a copy of the manually registered seat configurations.
        """
        with self._lock:
            return dict(self._registered_seats)


