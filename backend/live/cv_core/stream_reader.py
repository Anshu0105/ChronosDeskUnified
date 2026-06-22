import cv2
import time
import logging
import numpy as np
from typing import Generator, Tuple, Optional, Any, Dict, List

# Configure basic logger for this module
logger = logging.getLogger(__name__)

class StreamReader:
    """
    Handles reading frames from a video stream with robust auto-reconnect logic
    and exponential backoff.
    """

    def __init__(self, stream_url: str | int, state_store: Any = None):
        """
        Initialize the stream reader.

        :param stream_url: The URL or device ID of the video stream.
        :param state_store: Instance of StateStore (dependency injection) to update
                            seat statuses upon critical failure.
        """
        self.stream_url = stream_url
        self.state_store = state_store
        self.cap: Optional[cv2.VideoCapture] = None
        
        self.consecutive_failures: int = 0
        self.max_failures: int = 10
        self.base_delay: float = 2.0
        self.max_delay: float = 30.0
        self.frame_count: int = 0
        self.fps: float = 30.0
        self._bootstrapped: bool = False
        self._bootstrap_frames: List[np.ndarray] = []

    def reset(self):
        """
        Resets the stream reader and all downstream CV state for a fresh video.
        Must be called before starting processing of any new video.
        """
        self._bootstrapped = False
        self._bootstrap_frames = []
        if hasattr(self, 'chair_tracker') and self.chair_tracker is not None:
            self.chair_tracker.reset()

    def connect(self) -> bool:
        """Attempts to open the OpenCV VideoCapture."""
        if self.cap is not None:
            self.cap.release()
            
        try:
            # OpenCV captures the stream
            self.cap = cv2.VideoCapture(self.stream_url)
            self.frame_count = 0
            if self.cap.isOpened():
                fps = self.cap.get(cv2.CAP_PROP_FPS)
                if fps and fps > 0:
                    self.fps = fps
                else:
                    self.fps = 30.0
                return True
            return False
        except cv2.error as e:
            logger.error(f"OpenCV error while connecting: {e}")
            return False

    def read_frames(self) -> Generator[Tuple[Optional[np.ndarray], Optional[Dict[str, str]]], None, None]:
        """
        Continuous generator that yields tuples of (frame, error_event).
        If frame is None, error_event contains the payload to be emitted to WebSockets.
        """
        try:
            while True:
                if getattr(self, '_stop_event', None) is not None and self._stop_event.is_set():
                    break

                # Check for dynamic stream source switch in the shared state store
                if self.state_store and hasattr(self.state_store, 'get_stream_url'):
                    new_url = self.state_store.get_stream_url()
                    if new_url != self.stream_url:
                        logger.info(f"Stream Reader switching source from '{self.stream_url}' to '{new_url}'")
                        self.stream_url = new_url
                        self.consecutive_failures = 0
                        if self.cap is not None:
                            self.cap.release()
                            self.cap = None

                if self.cap is None or not self.cap.isOpened():
                    if not self.connect():
                        err_payload = self._handle_disconnect()
                        yield err_payload
                        if self.consecutive_failures > self.max_failures:
                            logger.info("Breaking read loop because max failures reached.")
                            break
                        continue

                try:
                    ret, frame = self.cap.read()
                    if not ret:
                        logger.info("Video ingestion completed (ret is False). Releasing capture stream and destroying window resources.")
                        self.cap.release()
                        cv2.destroyAllWindows()
                        break

                    self.frame_count += 1
                    
                    # Reset failures on successful read
                    if self.consecutive_failures > 0:
                        logger.info("Stream reconnected successfully.")
                        self.consecutive_failures = 0
                        
                    yield (frame, None)
                    
                except cv2.error as e:
                    logger.error(f"OpenCV error reading frame: {e}")
                    yield self._handle_disconnect()
        finally:
            if hasattr(self, 'chair_tracker') and self.chair_tracker is not None:
                self.chair_tracker.reset()

    @property
    def current_video_time(self) -> float:
        return self.frame_count / self.fps

    @property
    def total_video_duration(self) -> float:
        if self.cap is not None and self.cap.isOpened():
            total_frames = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if total_frames and total_frames > 0:
                return total_frames / self.fps
        return 0.0

    def _handle_disconnect(self) -> Tuple[None, Dict[str, str]]:
        """
        Applies exponential backoff logic and handles critical state reset.
        Returns a tuple to yield containing the error message.
        """
        self.consecutive_failures += 1
        
        if self.consecutive_failures > self.max_failures:
            logger.critical("Stream completely offline after 10 retries. Resetting all seats to unknown.")
            if self.state_store and hasattr(self.state_store, 'set_all_unknown'):
                self.state_store.set_all_unknown()
            
            return (None, {"event": "stream_error", "message": "Stream permanently offline."})
            
        # Exponential backoff: 2, 4, 8, 16, 30 max
        delay = min(self.base_delay ** self.consecutive_failures, self.max_delay)
        msg = f"Stream offline. Reconnecting in {delay} seconds..."
        
        logger.warning(msg)
        time.sleep(delay)
        
        return (None, {"event": "stream_error", "message": msg})
