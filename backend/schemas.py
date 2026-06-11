from pydantic import BaseModel, ConfigDict
from typing import List, Literal, Tuple, Optional, Union
from datetime import datetime

class SeatRegisterRequest(BaseModel):
    """Payload for registering a new interactive seat bbox manually."""
    bbox: Tuple[float, float, float, float]
    display_name: Optional[str] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "bbox": [50.0, 50.0, 150.0, 150.0],
                "display_name": "Left Desk"
            }
        }
    )

class SeatRegisterResponse(BaseModel):
    """Response returned after successful seat registration."""
    seat_id: int
    display_name: str
    registered: bool = True

class SeatStatusResponse(BaseModel):
    """Payload representing current real-time state of a specific seat."""
    seat_id: int
    display_name: str
    bbox: Tuple[float, float, float, float]
    status: Literal["occupied", "vacant", "unknown"]
    sat_at: Optional[float] = None
    duration: Optional[Union[float, str]] = 0.0
    history: Optional[List[str]] = None


class SeatHistoryResponse(BaseModel):
    """Payload representing a single historical timeline shift."""
    timestamp: datetime
    status: Literal["occupied", "vacant", "unknown"]

class WebSocketOccupancyPayload(BaseModel):
    """Typing equivalent of the live streaming JSON."""
    timestamp: datetime
    seats: List[dict] # Keeping dict generic for speed over WS mappings
