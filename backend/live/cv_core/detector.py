import logging
import numpy as np
from typing import List, Tuple, Optional
from ultralytics import YOLO
from backend.live.cv_core.config import MIN_DETECTION_CONFIDENCE

logger = logging.getLogger(__name__)

class YOLODetector:
    """
    Wrapper around Ultralytics YOLO to detect people and extract raw bounding boxes.
    """

    def __init__(self, model_path: str = "yolov8s.pt", conf_threshold: Optional[float] = None):
        """
        Initializes the YOLO model gracefully.
        
        :param model_path: Path to the YOLO weights file (e.g., 'yolov8n.pt').
        :param conf_threshold: Minimum confidence score to consider a valid detection.
        """
        self.model_path = model_path
        self.conf_threshold = conf_threshold if conf_threshold is not None else MIN_DETECTION_CONFIDENCE

        try:
            self.model = YOLO(self.model_path)
            logger.info(f"Loaded YOLO model from {self.model_path}")
            import torch
            if torch.backends.mps.is_available():
                self.device = "mps"
            elif torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"
            self.model.to(self.device)
            logger.info(f"YOLODetector running on device: {self.device}")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise RuntimeError(f"YOLO model load failed: {e}")

    def detect_people(self, frame: np.ndarray) -> List[Tuple[float, float, float, float]]:
        """
        Runs inference on a single OpenCV frame and extracts bounding boxes for people.
        
        :param frame: The image matrix from OpenCV (numpy array).
        :return: A list of (x1, y1, x2, y2) bounding boxes as floats.
        """
        # Define person class ID (0 in COCO dataset)
        PERSON_CLASS_ID = 0
        boxes_out: List[Tuple[float, float, float, float]] = []
        
        try:
            # Run inference; verbose=False prevents console spam per frame
            results = self.model(frame, verbose=False, device=self.device, half=True)
            
            for result in results:
                # Iterate through detected hardware-accelerated tensor boxes
                if result.boxes is None:
                    continue
                    
                for box in result.boxes:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    
                    if cls_id == PERSON_CLASS_ID and conf >= self.conf_threshold:
                        # Extract coordinates as x1, y1, x2, y2
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        boxes_out.append((x1, y1, x2, y2))
                        
            return boxes_out
        except Exception as e:
            logger.error(f"Error during YOLO inference: {e}")
            return []

    def detect_objects(self, frame: np.ndarray) -> Tuple[List[Tuple[float, float, float, float]], List[Tuple[float, float, float, float]]]:
        """
        Runs inference on a single OpenCV frame and extracts bounding boxes for both people and chairs.
        
        :param frame: The image matrix from OpenCV (numpy array).
        :return: A tuple of (person_boxes, chair_boxes).
        """
        PERSON_CLASS_ID = 0
        CHAIR_CLASS_ID = 56
        people_out: List[Tuple[float, float, float, float]] = []
        chairs_out: List[Tuple[float, float, float, float]] = []
        
        try:
            results = self.model(frame, verbose=False, device=self.device, half=True)
            
            for result in results:
                if result.boxes is None:
                    continue
                    
                for box in result.boxes:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    
                    if conf >= self.conf_threshold:
                        if cls_id == PERSON_CLASS_ID:
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            people_out.append((x1, y1, x2, y2))
                        elif cls_id == CHAIR_CLASS_ID:
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            chairs_out.append((x1, y1, x2, y2))
                            
            return people_out, chairs_out
        except Exception as e:
            logger.error(f"Error during YOLO inference: {e}")
            return [], []

    def detect_chairs_bootstrap(self, frame: np.ndarray) -> List[Tuple[float, float, float, float]]:
        """
        Run full chair detection on a frame using the configured confidence threshold
        during initial seat bootstrapping to prevent false positive ghost chairs.

        :param frame: The image matrix from OpenCV (numpy array).
        :return: A list of (x1, y1, x2, y2) bounding boxes for detected chairs.
        """
        CHAIR_CLASS_ID = 56
        CHAIR_CONF = self.conf_threshold
        chairs_out: List[Tuple[float, float, float, float]] = []

        try:
            results = self.model(frame, verbose=False, device=self.device, half=True)

            for result in results:
                if result.boxes is None:
                    continue

                for box in result.boxes:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())

                    if cls_id == CHAIR_CLASS_ID and conf >= CHAIR_CONF:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        chairs_out.append((x1, y1, x2, y2))

            return chairs_out
        except Exception as e:
            logger.error(f"Error during chair bootstrap detection: {e}")
            return []

    def detect_chairs_delta(
        self,
        frame: np.ndarray,
        known_boxes: List[Tuple[float, float, float, float]],
    ) -> Tuple[List[Tuple[float, float, float, float]], List[Tuple[float, float, float, float]]]:
        """
        Re-detect chairs and return only boxes that have moved relative to
        *known_boxes*.  A detected box is considered "moved" when its IoU
        with **every** entry in *known_boxes* is below 0.5.

        :param frame: The image matrix from OpenCV (numpy array).
        :param known_boxes: Previously registered chair bounding boxes.
        :return: A tuple of (moved_boxes, all_detected_boxes).
        """

        # ── inline IoU helper (avoids circular import from occupancy.py) ──
        def _iou(
            box_a: Tuple[float, float, float, float],
            box_b: Tuple[float, float, float, float],
        ) -> float:
            xa = max(box_a[0], box_b[0])
            ya = max(box_a[1], box_b[1])
            xb = min(box_a[2], box_b[2])
            yb = min(box_a[3], box_b[3])

            inter = max(0.0, xb - xa) * max(0.0, yb - ya)
            if inter == 0.0:
                return 0.0

            area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
            area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
            return inter / (area_a + area_b - inter)

        all_detected = self.detect_chairs_bootstrap(frame)

        moved: List[Tuple[float, float, float, float]] = []
        for det in all_detected:
            matched = any(_iou(det, kb) >= 0.5 for kb in known_boxes)
            if not matched:
                moved.append(det)

        return moved, all_detected

    def detect_chairs_consensus(
        self,
        frames: List[np.ndarray],
        min_votes: int = 2
    ) -> List[Tuple[float, float, float, float]]:
        """
        Run chair detection on multiple frames (typically the first 3 frames)
        and return only boxes that appear in at least *min_votes* of them.
        Matching is determined by IoU >= 0.4 against the running averaged box.
        Final coordinates are the mean of all matched detections.

        :param frames: List of OpenCV image matrices to scan.
        :param min_votes: Minimum number of frames a box must appear in.
        :return: List of averaged (x1, y1, x2, y2) bounding boxes.
        """

        # ── inline IoU helper (avoids circular import from occupancy.py) ──
        def _iou(
            box_a: Tuple[float, float, float, float],
            box_b: Tuple[float, float, float, float],
        ) -> float:
            xa = max(box_a[0], box_b[0])
            ya = max(box_a[1], box_b[1])
            xb = min(box_a[2], box_b[2])
            yb = min(box_a[3], box_b[3])

            inter = max(0.0, xb - xa) * max(0.0, yb - ya)
            if inter == 0.0:
                return 0.0

            area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
            area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
            return inter / (area_a + area_b - inter)

        def _avg_box(boxes):
            n = len(boxes)
            return (
                sum(b[0] for b in boxes) / n,
                sum(b[1] for b in boxes) / n,
                sum(b[2] for b in boxes) / n,
                sum(b[3] for b in boxes) / n,
            )

        # Vote accumulator: list of {"boxes": [...], "votes": int}
        accumulator = []

        for frame in frames:
            detections = self.detect_chairs_bootstrap(frame)
            for det in detections:
                matched = False
                for entry in accumulator:
                    avg = _avg_box(entry["boxes"])
                    if _iou(det, avg) >= 0.4:
                        entry["boxes"].append(det)
                        entry["votes"] += 1
                        matched = True
                        break
                if not matched:
                    accumulator.append({"boxes": [det], "votes": 1})

        # Return averaged coordinates for entries meeting the vote threshold
        result: List[Tuple[float, float, float, float]] = []
        for entry in accumulator:
            if entry["votes"] >= min_votes:
                result.append(_avg_box(entry["boxes"]))

        return result
