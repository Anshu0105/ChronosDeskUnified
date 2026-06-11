import math
import time
from typing import List, Tuple, Dict, Any, Optional
from threading import Lock
from backend.live.cv_core.config import OCCUPANCY_IOU_THRESHOLD, OCCUPANCY_CENTROID_FALLBACK_DISTANCE

def compute_iou(boxA: Tuple[float, float, float, float], boxB: Tuple[float, float, float, float]) -> float:
    """
    Compute the Intersection over Union (IoU) metric for two bounding boxes.
    
    Args:
        boxA, boxB: (x1, y1, x2, y2) in pixel coordinates
    Returns:
        IoU score as float between 0.0 and 1.0
    """
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0.0, xB - xA) * max(0.0, yB - yA)
    if interArea == 0:
        return 0.0

    boxAArea = max(0.0, boxA[2] - boxA[0]) * max(0.0, boxA[3] - boxA[1])
    boxBArea = max(0.0, boxB[2] - boxB[0]) * max(0.0, boxB[3] - boxB[1])

    iou = interArea / float(boxAArea + boxBArea - interArea)
    return iou


def compute_overlap_ratio(chair_box: Tuple[float, float, float, float], person_box: Tuple[float, float, float, float]) -> float:
    """
    Computes the percentage of the chair's bounding box that is overlapped by the person's bounding box.
    Formula: Area(person ∩ chair) / Area(chair)
    """
    xA = max(chair_box[0], person_box[0])
    yA = max(chair_box[1], person_box[1])
    xB = min(chair_box[2], person_box[2])
    yB = min(chair_box[3], person_box[3])

    interArea = max(0.0, xB - xA) * max(0.0, yB - yA)
    if interArea == 0:
        return 0.0

    chair_area = max(0.0, chair_box[2] - chair_box[0]) * max(0.0, chair_box[3] - chair_box[1])
    if chair_area == 0.0:
        return 0.0

    return interArea / chair_area


def _get_centroid(box: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """Helper function to calculate the (x, y) centroid of a bounding box."""
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

def _compute_distance(centroidA: Tuple[float, float], centroidB: Tuple[float, float]) -> float:
    """Helper function to compute Euclidean distance between two centroids."""
    return math.hypot(centroidA[0] - centroidB[0], centroidA[1] - centroidB[1])


def is_occupied_two_stage(
    chair_box: Tuple[float, float, float, float],
    person_box: Tuple[float, float, float, float],
    iou_threshold: float
) -> bool:
    """
    Two-stage occupancy check:
      Stage 1: IoU >= iou_threshold
      Stage 2: Euclidean distance between centroids <= OCCUPANCY_CENTROID_FALLBACK_DISTANCE
               AND abs(person_box_bottom - chair_box_bottom) <= 40.0
    """
    # Stage 1: IoU Check
    if compute_iou(chair_box, person_box) >= iou_threshold:
        return True

    # Stage 2: Fallback Check
    centroid_chair = _get_centroid(chair_box)
    centroid_person = _get_centroid(person_box)
    dist = _compute_distance(centroid_chair, centroid_person)
    
    if dist <= OCCUPANCY_CENTROID_FALLBACK_DISTANCE and abs(person_box[3] - chair_box[3]) <= 40.0:
        return True
        
    return False


def is_seat_occupied(
    seat_box: Tuple[float, float, float, float],
    person_boxes: List[Tuple[float, float, float, float]],
    iou_threshold: float = 0.25
) -> bool:
    """
    Returns True if any person bbox overlaps seat_box above threshold or via fallback.
    Kept for backward compatibility with older tests.
    """
    for person_box in person_boxes:
        if is_occupied_two_stage(seat_box, person_box, iou_threshold):
            return True
    return False


def resolve_seat_assignments(
    seats: Dict[int, Tuple[float, float, float, float]],
    person_boxes: List[Tuple[float, float, float, float]],
    iou_threshold: float = 0.25
) -> Dict[int, bool]:
    """
    Determines occupancy for all seats based on bounding box IoU or fallback.
    Kept for backward compatibility with older tests.
    """
    seat_status = {seat_id: False for seat_id in seats}
    assigned_persons = set()
    possible_assignments = []
    
    for seat_id, seat_box in seats.items():
        seat_center = _get_centroid(seat_box)
        for p_idx, p_box in enumerate(person_boxes):
            if is_occupied_two_stage(seat_box, p_box, iou_threshold):
                p_center = _get_centroid(p_box)
                dist = _compute_distance(seat_center, p_center)
                possible_assignments.append((dist, seat_id, p_idx))
                
    possible_assignments.sort(key=lambda x: x[0])
    assigned_seats = set()
    
    for dist, seat_id, p_idx in possible_assignments:
        if p_idx not in assigned_persons and seat_id not in assigned_seats:
            seat_status[seat_id] = True
            assigned_persons.add(p_idx)
            assigned_seats.add(seat_id)
            
    return seat_status


def format_time(seconds: float) -> str:
    secs = max(0, int(seconds))
    m = secs // 60
    s = secs % 60
    return f"{m:02d}:{s:02d}"


def format_duration(seconds: float) -> str:
    secs = int(max(0.0, seconds))
    if secs >= 60:
        m = secs // 60
        s = secs % 60
        return f"{m}m {s}s"
    return f"{secs}s"


class SeatRegistry:
    """
    Maintains stable, persistent seat IDs across frames.
    Once a seat is registered, its ID never changes regardless of detection order.
    """

    def __init__(self, iou_match_threshold: float = 0.4):
        self._lock = Lock()
        self._seats: Dict[int, Tuple[float, float, float, float]] = {}
        self._missing_since: Dict[int, float] = {}
        self._next_id = 1
        self.iou_match_threshold = iou_match_threshold

    def register_all(self, boxes: List[Tuple[float, float, float, float]]) -> Dict[int, Tuple[float, float, float, float]]:
        """
        Called on bootstrap frame. Assigns new IDs to all boxes sorted left-to-right by x1.
        Clears any existing registry first.
        Returns the full id->bbox mapping.
        """
        with self._lock:
            self._seats = {}
            self._missing_since = {}
            self._next_id = 1
            sorted_boxes = sorted(boxes, key=lambda b: b[0])
            for box in sorted_boxes:
                is_duplicate = False
                for existing_box in self._seats.values():
                    if compute_iou(box, existing_box) >= 0.55:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    self._seats[self._next_id] = box
                    self._next_id += 1
                    
            self._deduplicate_unlocked(threshold=0.5)
            return dict(self._seats)

    def update_positions(
        self, 
        new_boxes: List[Tuple[float, float, float, float]], 
        vacant_seat_ids: set, 
        current_time: float
    ) -> Dict[int, Tuple[float, float, float, float]]:
        """
        Called on periodic re-check frames.
        Matches new_boxes to existing seats by highest IoU.
        - Matched seat: update its bbox position.
        - Ghost Chair (unmatched vacant existing): reassigned to closest unmatched new box.
        - Unmatched new box: assign new ID.
        - Unmatched occupied existing: kept as is.
        - Ghost Chair missing > 30s: deleted.
        Returns updated id->bbox mapping.
        """
        with self._lock:
            matched_existing = set()
            matched_new = set()
            # 1. Match by IoU >= threshold (small movements)
            assignments = []
            for seat_id, seat_box in self._seats.items():
                for ni, new_box in enumerate(new_boxes):
                    iou = compute_iou(seat_box, new_box)
                    if iou >= self.iou_match_threshold:
                        assignments.append((iou, seat_id, ni))
            assignments.sort(key=lambda x: -x[0])
            for iou, seat_id, ni in assignments:
                if seat_id not in matched_existing and ni not in matched_new:
                    self._seats[seat_id] = new_boxes[ni]
                    matched_existing.add(seat_id)
                    matched_new.add(ni)
                    
            # 2. Ghost Chair Reassignment
            unmatched_existing = [sid for sid in self._seats.keys() if sid not in matched_existing]
            ghost_chairs = [sid for sid in unmatched_existing if sid in vacant_seat_ids]
            unmatched_new = [ni for ni in range(len(new_boxes)) if ni not in matched_new]
            
            def _center(box):
                return ((box[0]+box[2])/2.0, (box[1]+box[3])/2.0)
                
            ghost_centers = {sid: _center(self._seats[sid]) for sid in ghost_chairs}
            new_centers = {ni: _center(new_boxes[ni]) for ni in unmatched_new}
            
            dist_assignments = []
            for sid in ghost_chairs:
                for ni in unmatched_new:
                    c1 = ghost_centers[sid]
                    c2 = new_centers[ni]
                    dist = (c1[0]-c2[0])**2 + (c1[1]-c2[1])**2
                    dist_assignments.append((dist, sid, ni))
            
            dist_assignments.sort(key=lambda x: x[0])  # shortest distance first
            
            reassigned_ghosts = set()
            for dist, sid, ni in dist_assignments:
                if sid not in reassigned_ghosts and ni not in matched_new:
                    self._seats[sid] = new_boxes[ni]
                    reassigned_ghosts.add(sid)
                    matched_new.add(ni)
                    matched_existing.add(sid)
            
            # 3. Track missing ghosts and delete if > 30s
            still_ghosts = [sid for sid in ghost_chairs if sid not in reassigned_ghosts]
            for sid in still_ghosts:
                if sid not in self._missing_since:
                    self._missing_since[sid] = current_time
                    
            to_delete = []
            for sid in list(self._missing_since.keys()):
                if sid in matched_existing or sid not in self._seats:
                    del self._missing_since[sid]
                else:
                    if sid in still_ghosts and (current_time - self._missing_since[sid]) >= 30.0:
                        to_delete.append(sid)
                        
            for sid in to_delete:
                del self._seats[sid]
                del self._missing_since[sid]
            
            # 4. New boxes with no match get new IDs
            for ni, new_box in enumerate(new_boxes):
                if ni not in matched_new:
                    self._seats[self._next_id] = new_box
                    self._next_id += 1
                    
            return dict(self._seats)

    def get_all(self) -> Dict[int, Tuple[float, float, float, float]]:
        with self._lock:
            return dict(self._seats)

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._seats) == 0

    def _deduplicate_unlocked(self, threshold: float = 0.5):
        to_remove = set()
        seat_ids = sorted(list(self._seats.keys()))
        for i in range(len(seat_ids)):
            id_a = seat_ids[i]
            if id_a in to_remove:
                continue
            for j in range(i + 1, len(seat_ids)):
                id_b = seat_ids[j]
                if id_b in to_remove:
                    continue
                if compute_iou(self._seats[id_a], self._seats[id_b]) >= threshold:
                    to_remove.add(id_b)
        for rid in to_remove:
            del self._seats[rid]

    def deduplicate(self, threshold: float = 0.5):
        with self._lock:
            self._deduplicate_unlocked(threshold)


def is_person_sitting(
    chair_box: Tuple[float, float, float, float],
    person_box: Tuple[float, float, float, float],
    iou_threshold: float = 0.15
) -> bool:
    """
    Three-stage filter to distinguish a sitting person from a standing person near a chair.

    Height Ratio Guard:
        If person height / chair height > 2.2, require IoU >= 0.25 to confirm occupancy.

    Stage A — Lower-body centroid overlap:
        The bottom 25% of the person box is the "seated zone".
        Compute the centroid of that zone. If it falls inside the chair box → sitting.

    Stage B — Vertical midpoint alignment:
        A sitting person's vertical midpoint (py1+py2)/2 should be within
        [chair_top - 0.3*chair_height, chair_bottom + 0.2*chair_height].
        If midpoint is above this band → standing.

    Stage C — Aspect ratio guard:
        A standing person's bounding box is tall and narrow.
        If person height / person width > 2.0 AND IoU < 0.20 → standing, reject.

    Returns True only if Stage A OR (Stage B AND NOT Stage C) passes.
    Falls back to standard IoU >= iou_threshold if none of the geometric stages fire.
    """
    px1, py1, px2, py2 = person_box
    cx1, cy1, cx2, cy2 = chair_box

    person_h = py2 - py1
    person_w = px2 - px1
    chair_h = cy2 - cy1

    if person_h <= 0 or person_w <= 0 or chair_h <= 0:
        return compute_iou(chair_box, person_box) >= iou_threshold

    iou = compute_iou(chair_box, person_box)

    if (person_h / chair_h) > 2.2:
        if iou < 0.25:
            return False

    # Stage A: lower-body centroid
    seated_zone_top = py1 + 0.75 * person_h
    seated_centroid_x = (px1 + px2) / 2.0
    seated_centroid_y = (seated_zone_top + py2) / 2.0
    stage_a = (cx1 <= seated_centroid_x <= cx2) and (cy1 <= seated_centroid_y <= cy2)

    if stage_a:
        return True

    # Stage B: vertical midpoint alignment
    person_mid_y = (py1 + py2) / 2.0
    band_top = cy1 - 0.3 * chair_h
    band_bottom = cy2 + 0.2 * chair_h
    stage_b = band_top <= person_mid_y <= band_bottom

    # Stage C: aspect ratio guard
    aspect_ratio = person_h / person_w
    stage_c_reject = (aspect_ratio > 2.0) and (iou < 0.20)

    if stage_b and not stage_c_reject:
        return True

    # Fallback
    return iou >= iou_threshold


class OccupancyConfirmation:
    """
    Per-seat state machine that requires a stable signal for a minimum duration
    before committing a state change. Applies asymmetric windows:
      - VACANT → OCCUPIED: requires occupy_confirm_secs of continuous sitting signal
      - OCCUPIED → VACANT: requires vacate_confirm_secs of continuous absent signal
    
    On confirmation of OCCUPIED, backdates the start timestamp by occupy_confirm_secs.
    On confirmation of VACANT, backdates the end timestamp by vacate_confirm_secs.
    """

    def __init__(
        self,
        occupy_confirm_secs: float = 5.0,
        vacate_confirm_secs: float = 3.0
    ):
        self.occupy_confirm_secs = occupy_confirm_secs
        self.vacate_confirm_secs = vacate_confirm_secs
        # Per-seat state
        self._confirmed: Dict[int, str] = {}           # seat_id -> "vacant" | "occupied"
        self._candidate_start: Dict[int, float] = {}   # seat_id -> time candidate began
        self._candidate_state: Dict[int, str] = {}     # seat_id -> current candidate

    def update(
        self,
        seat_id: int,
        raw_signal: bool,
        current_time: float
    ) -> Tuple[str, Optional[float]]:
        """
        Feed one frame's raw signal for a seat.
        
        Args:
            seat_id: The stable seat ID.
            raw_signal: True if sitting detected this frame, False otherwise.
            current_time: Current video timestamp in seconds.
        
        Returns:
            (confirmed_status, confirmed_start_time)
            confirmed_status: "occupied" or "vacant" — the committed state
            confirmed_start_time: 
                - When transitioning TO occupied: backdated start = current_time - occupy_confirm_secs
                - When transitioning TO vacant: backdated end = current_time - vacate_confirm_secs  
                - None if no state transition occurred this call
        """
        incoming = "occupied" if raw_signal else "vacant"
        
        # Initialize on first sight
        if seat_id not in self._confirmed:
            self._confirmed[seat_id] = "vacant"
            self._candidate_state[seat_id] = incoming
            self._candidate_start[seat_id] = current_time
            return "vacant", None

        confirmed = self._confirmed[seat_id]
        candidate = self._candidate_state[seat_id]

        # Signal changed — reset candidate
        if incoming != candidate:
            self._candidate_state[seat_id] = incoming
            self._candidate_start[seat_id] = current_time
            return confirmed, None

        # Signal stable — check if window elapsed
        elapsed = current_time - self._candidate_start[seat_id]

        if incoming == "occupied" and confirmed == "vacant":
            if elapsed >= self.occupy_confirm_secs:
                self._confirmed[seat_id] = "occupied"
                backdated_start = self._candidate_start[seat_id]  # already the true start
                return "occupied", backdated_start

        elif incoming == "vacant" and confirmed == "occupied":
            if elapsed >= self.vacate_confirm_secs:
                self._confirmed[seat_id] = "vacant"
                backdated_end = self._candidate_start[seat_id]  # when vacating began
                return "vacant", backdated_end

        return confirmed, None

    def reset_seat(self, seat_id: int):
        """Remove all state for a seat (called when seat is removed from registry)."""
        for d in [self._confirmed, self._candidate_start, self._candidate_state]:
            d.pop(seat_id, None)

    def get_confirmed(self, seat_id: int) -> str:
        return self._confirmed.get(seat_id, "vacant")


class ChairTracker:
    """
    Maintains persistent tracking of chairs across video frames.
    Matches detected chairs with tracked chairs to assign stable IDs.
    Calculates occupancy based on human-chair overlap ratio and tracks duration.
    """
    def __init__(self, iou_threshold: Optional[float] = None, max_distance: float = 50.0):
        self._lock = Lock()
        self.tracked_chairs = []
        self.chair_counter = 0
        self.max_distance = max_distance
        self.id_mapping_registry = {}
        self.sequential_counter = 1
        self.chair_time_ledger = {}
        self.iou_threshold = iou_threshold if iou_threshold is not None else OCCUPANCY_IOU_THRESHOLD
        self.current_video_time = 0.0
        self.seat_registry = SeatRegistry(iou_match_threshold=0.4)
        self._frame_count: int = 0
        self.chair_check_interval: int = 60  # re-detect chairs every N frames
        self.occupancy_confirmation = OccupancyConfirmation(
            occupy_confirm_secs=5.0,
            vacate_confirm_secs=3.0
        )

    def reset(self):
        """
        Fully resets all tracker state so a new video can be processed cleanly.
        Equivalent to constructing a new ChairTracker instance without losing
        the configuration parameters (iou_threshold, max_distance, chair_check_interval).
        """
        with self._lock:
            self.tracked_chairs = []
            self.chair_counter = 0
            self.id_mapping_registry = {}
            self.sequential_counter = 1
            self.chair_time_ledger = {}
            self.current_video_time = 0.0
            self._frame_count = 0
            self.seat_registry = SeatRegistry(iou_match_threshold=0.4)
            self.occupancy_confirmation = OccupancyConfirmation(
                occupy_confirm_secs=5.0,
                vacate_confirm_secs=3.0
            )

    def update(
        self,
        detected_chairs: List[Tuple[float, float, float, float]],
        detected_people: List[Tuple[float, float, float, float]],
        current_video_time: float = 0.0,
        registered_seats: Optional[Dict[int, dict]] = None
    ) -> List[dict]:
        with self._lock:
            self.current_video_time = current_video_time
            
            if registered_seats:
                # 1. Sync tracked chairs with registered seats
                updated_tracked = []
                for seat_id, info in registered_seats.items():
                    bbox = info["bbox"]
                    existing = next((c for c in self.tracked_chairs if c.get("seat_id") == seat_id or c.get("id") == seat_id), None)
                    if existing:
                        existing["bbox"] = bbox
                        existing["id"] = seat_id
                        existing["seat_id"] = seat_id
                        updated_tracked.append(existing)
                    else:
                        updated_tracked.append({
                            "id": seat_id,
                            "seat_id": seat_id,
                            "bbox": bbox,
                            "status": "vacant",
                            "sat_at": None,
                            "duration": "0s",
                            "missed_frames": 0,
                            "history": []
                        })
                self.tracked_chairs = updated_tracked
                # Clean up deleted seats from the ledger to prevent memory leaks/ghost states
                self.chair_time_ledger = {k: v for k, v in self.chair_time_ledger.items() if k in registered_seats}
            else:
                self._frame_count += 1
                # Bootstrap: populate registry on first frame or if empty
                if self.seat_registry.is_empty():
                    registry_map = self.seat_registry.register_all(detected_chairs)
                elif self._frame_count % self.chair_check_interval == 0 and detected_chairs is not None:
                    vacant_ids = {c["id"] for c in self.tracked_chairs if c.get("status", "vacant") == "vacant"}
                    registry_map = self.seat_registry.update_positions(detected_chairs, vacant_ids, current_video_time)
                    self.seat_registry.deduplicate(threshold=0.5)
                    registry_map = self.seat_registry.get_all()
                else:
                    registry_map = self.seat_registry.get_all()

                # Rebuild tracked_chairs from stable registry
                existing_by_id = {c["id"]: c for c in self.tracked_chairs if c.get("raw_id") is not None}
                updated_tracked = []
                for seat_id, bbox in registry_map.items():
                    if seat_id in existing_by_id:
                        chair = existing_by_id[seat_id]
                        chair["bbox"] = bbox
                    else:
                        chair = {
                            "id": seat_id,
                            "raw_id": seat_id,
                            "seat_id": seat_id,
                            "bbox": bbox,
                            "status": "vacant",
                            "sat_at": None,
                            "duration": "0s",
                            "missed_frames": 0,
                            "history": []
                        }
                    updated_tracked.append(chair)
                self.tracked_chairs = updated_tracked
                # Sync ledger
                self.chair_time_ledger = {k: v for k, v in self.chair_time_ledger.items() if k in registry_map}
                # Clean up confirmation state for removed seats
                for removed_id in set(self.occupancy_confirmation._confirmed.keys()) - set(registry_map.keys()):
                    self.occupancy_confirmation.reset_seat(removed_id)

            # 4. Resolve human-chair occupancy using the two-stage check
            assigned_people = set()
            
            for chair in self.tracked_chairs:
                best_p_idx = -1
                best_metric = -1.0
                
                for p_idx, person_box in enumerate(detected_people):
                    if p_idx in assigned_people:
                        continue
                    if is_person_sitting(chair["bbox"], person_box, self.iou_threshold):
                        metric = compute_iou(chair["bbox"], person_box)
                        if metric > best_metric:
                            best_metric = metric
                            best_p_idx = p_idx
                
                # Raw state for this frame
                raw_occupied = (best_p_idx != -1)

                confirmed_status, transition_time = self.occupancy_confirmation.update(
                    seat_id=chair["id"],
                    raw_signal=raw_occupied,
                    current_time=current_video_time
                )

                if confirmed_status != chair["status"]:
                    # State transition confirmed
                    if confirmed_status == "occupied":
                        chair["status"] = "occupied"
                        chair["sat_at"] = transition_time  # backdated start
                        chair["duration"] = "0s"
                        if best_p_idx != -1:
                            chair["assigned_person_box"] = detected_people[best_p_idx]
                            assigned_people.add(best_p_idx)
                    else:
                        chair["status"] = "vacant"
                        chair["sat_at"] = None
                        chair["duration"] = "0s"
                        if "assigned_person_box" in chair:
                            del chair["assigned_person_box"]
                else:
                    # No transition — update duration if occupied
                    if chair["status"] == "occupied" and chair.get("sat_at") is not None:
                        chair["duration"] = format_duration(current_video_time - chair["sat_at"])
                    if confirmed_status == "occupied" and best_p_idx != -1:
                        chair["assigned_person_box"] = detected_people[best_p_idx]
                        assigned_people.add(best_p_idx)

            if registered_seats is None:
                # Remap raw IDs to normalized sequential integers starting from 1
                for chair in self.tracked_chairs:
                    raw_id = chair.get("raw_id")
                    if raw_id is None:
                        try:
                            if isinstance(chair["id"], str):
                                raw_id = int(chair["id"].split()[-1])
                            else:
                                raw_id = int(chair["id"])
                        except (ValueError, IndexError):
                            raw_id = self.chair_counter
                        chair["raw_id"] = raw_id

                    if raw_id not in self.id_mapping_registry:
                        self.id_mapping_registry[raw_id] = self.sequential_counter
                        self.sequential_counter += 1
                    
                    mapped_val = self.id_mapping_registry[raw_id]
                    chair["id"] = mapped_val

            # Ensure seat_id matches frontend key
            for chair in self.tracked_chairs:
                chair["seat_id"] = chair["id"]

            # Track state transition history using the sequential IDs
            for chair in self.tracked_chairs:
                chair_id = chair["id"]
                if chair_id not in self.chair_time_ledger:
                    self.chair_time_ledger[chair_id] = {
                        "current_state": "VACANT",
                        "state_start_time": current_video_time,
                        "accumulated_occupied_time": 0.0,
                        "transition_history": [],
                        "raw_events": [],
                        "candidate_state": "VACANT",
                        "candidate_start_time": current_video_time,
                        "consecutive_frames": 1
                    }
                
                ledger_entry = self.chair_time_ledger[chair_id]
                raw_state_str = chair["status"].upper() # 'VACANT' or 'OCCUPIED'
                
                if "candidate_state" not in ledger_entry:
                    ledger_entry["candidate_state"] = ledger_entry["current_state"]
                    ledger_entry["candidate_start_time"] = ledger_entry["state_start_time"]
                    ledger_entry["consecutive_frames"] = 1
                    
                if raw_state_str == ledger_entry["candidate_state"]:
                    ledger_entry["consecutive_frames"] += 1
                else:
                    ledger_entry["candidate_state"] = raw_state_str
                    ledger_entry["candidate_start_time"] = current_video_time
                    ledger_entry["consecutive_frames"] = 1
                    
                if ledger_entry["consecutive_frames"] >= 15:
                    if ledger_entry["candidate_state"] != ledger_entry["current_state"]:
                        old_state = ledger_entry["current_state"]
                        start_time = ledger_entry["state_start_time"]
                        end_time = ledger_entry["candidate_start_time"]
                        duration = end_time - start_time
                        
                        if duration >= 0.5:
                            start_formatted = format_time(start_time)
                            end_formatted = format_time(end_time)
                            state_label = old_state.capitalize()
                            transition_str = f"{start_formatted} - {end_formatted} --> {state_label}"
                            ledger_entry["transition_history"].append(transition_str)
                            
                            if old_state == "OCCUPIED":
                                ledger_entry["accumulated_occupied_time"] += duration
                                ledger_entry["raw_events"].append({
                                    "occ_start_sec": start_time,
                                    "occ_end_sec": end_time
                                })
                                
                        ledger_entry["current_state"] = ledger_entry["candidate_state"]
                        ledger_entry["state_start_time"] = ledger_entry["candidate_start_time"]

                chair["transition_history"] = list(ledger_entry["transition_history"])

            return self.tracked_chairs

    def finalize_ledger(self, total_video_length: float):
        """
        Force-close any active blocks remaining in the ledger when the video ends.
        """
        with self._lock:
            for chair_id, ledger_entry in self.chair_time_ledger.items():
                # If there's a pending unconfirmed candidate transition, resolve it first
                if ledger_entry.get("candidate_state") and ledger_entry["candidate_state"] != ledger_entry["current_state"]:
                    old_state = ledger_entry["current_state"]
                    start_time = ledger_entry["state_start_time"]
                    end_time = ledger_entry["candidate_start_time"]
                    duration = end_time - start_time
                    
                    if duration >= 0.5:
                        start_formatted = format_time(start_time)
                        end_formatted = format_time(end_time)
                        state_label = old_state.capitalize()
                        transition_str = f"{start_formatted} - {end_formatted} --> {state_label}"
                        ledger_entry["transition_history"].append(transition_str)
                        
                        if old_state == "OCCUPIED":
                            ledger_entry["accumulated_occupied_time"] += duration
                            ledger_entry["raw_events"].append({
                                "occ_start_sec": start_time,
                                "occ_end_sec": end_time
                            })
                    
                    ledger_entry["current_state"] = ledger_entry["candidate_state"]
                    ledger_entry["state_start_time"] = ledger_entry["candidate_start_time"]

                # Finalize the current active state up to total_video_length
                old_state = ledger_entry["current_state"]
                start_time = ledger_entry["state_start_time"]
                duration = total_video_length - start_time
                
                if duration >= 0.5:
                    start_formatted = format_time(start_time)
                    end_formatted = format_time(total_video_length)
                    state_label = old_state.capitalize()
                    transition_str = f"{start_formatted} - {end_formatted} --> {state_label}"
                    ledger_entry["transition_history"].append(transition_str)
                    
                    if old_state == "OCCUPIED":
                        ledger_entry["accumulated_occupied_time"] += duration
                        ledger_entry["raw_events"].append({
                            "occ_start_sec": start_time,
                            "occ_end_sec": total_video_length
                        })
                
                ledger_entry["state_start_time"] = total_video_length
                    
            # Also update duration and transition_history on the tracked_chairs so it is immediately updated
            for chair in self.tracked_chairs:
                chair_id = chair["id"]
                if chair_id in self.chair_time_ledger:
                    ledger_entry = self.chair_time_ledger[chair_id]
                    chair["transition_history"] = list(ledger_entry["transition_history"])
                    if chair["status"] == "occupied" and chair.get("sat_at") is not None:
                        chair["duration"] = format_duration(total_video_length - chair["sat_at"])
                    else:
                        chair["duration"] = "0s"


def draw_occupancy_preview(
    frame,
    seats: List[dict],
    person_boxes: List[Tuple[float, float, float, float]]
):
    """
    Annotates a video frame with bounding boxes for visual verification on the frontend.
    Draws:
      - Unassigned people in Blue
      - Vacant chairs in Green
      - Sitting interactions (person + chair union) in Red
    """
    import cv2
    annotated = frame.copy()
    
    assigned_person_boxes = []
    
    # 1. Draw chairs and sitting interactions
    for seat in seats:
        x1_c, y1_c, x2_c, y2_c = map(int, seat["bbox"])
        status = seat.get("status", "vacant")
        
        if status == "occupied" and "assigned_person_box" in seat:
            # Draw interaction box (Red) around union of chair and person
            p_box = seat["assigned_person_box"]
            assigned_person_boxes.append(p_box)
            
            x1_p, y1_p, x2_p, y2_p = map(int, p_box)
            x1 = min(x1_c, x1_p)
            y1 = min(y1_c, y1_p)
            x2 = max(x2_c, x2_p)
            y2 = max(y2_c, y2_p)
            
            chair_area = max(0, x2_c - x1_c) * max(0, y2_c - y1_c)
            union_area = max(0, x2 - x1) * max(0, y2 - y1)
            
            if chair_area > 0 and union_area > 1.2 * chair_area:
                x1, y1, x2, y2 = x1_c, y1_c, x2_c, y2_c
            
            color = (80, 80, 244) # Red (BGR)
            duration = seat.get("duration", "0s")
            if isinstance(duration, str):
                label = f"Sitting ({duration})"
            else:
                label = f"Sitting ({int(duration)}s)"
            
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, label, (x1, y1 - 6), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        else:
            # Draw vacant or unknown chair box (Green or Gray)
            if status == "vacant":
                color = (80, 244, 80) # Green (BGR)
            else:
                color = (160, 160, 160) # Gray (BGR)
                
            label = f"Seat {seat['seat_id']}"
            cv2.rectangle(annotated, (x1_c, y1_c), (x2_c, y2_c), color, 2)
            cv2.putText(annotated, label, (x1_c, y1_c - 6), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    # Helper function to check if box is in assigned_person_boxes
    def is_assigned(box):
        for assigned in assigned_person_boxes:
            if all(abs(box[i] - assigned[i]) < 1e-3 for i in range(4)):
                return True
        return False

    # 2. Draw unassigned people (Blue)
    for box in person_boxes:
        if is_assigned(box):
            continue
        x1, y1, x2, y2 = map(int, box)
        color = (244, 160, 80) # Blue (BGR)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        cv2.putText(annotated, "Person", (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        
    return annotated
