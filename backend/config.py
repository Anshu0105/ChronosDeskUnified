from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Union

from pydantic import field_validator

class Settings(BaseSettings):
    """
    Globally accessible application settings statically typed.
    Automatically loaded from the .env file.
    """
    stream_url: Union[str, int] = 0

    @field_validator('stream_url', mode='before')
    @classmethod
    def parse_stream_url(cls, v):
        if str(v) == "0":
            return 0
        return v

    yolo_model: str = "yolov8s.pt"
    iou_threshold: float = 0.25
    
    occupancy_iou_threshold: float = 0.15
    occupancy_centroid_fallback_distance: float = 80.0
    min_detection_confidence: float = 0.40
    
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Singleton dependency exported for FastAPI injection / global state
settings = Settings()

# Uppercase constants exported for direct module imports
OCCUPANCY_IOU_THRESHOLD = settings.occupancy_iou_threshold
OCCUPANCY_CENTROID_FALLBACK_DISTANCE = settings.occupancy_centroid_fallback_distance
MIN_DETECTION_CONFIDENCE = settings.min_detection_confidence

