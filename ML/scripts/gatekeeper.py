"""Frame quality validation helpers (blur + hand occlusion)."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import List

import cv2
import numpy as np
from mediapipe import solutions as mp_solutions

HAND_DETECTED = "hand_detected"
FRAME_BLURRY = "frame_blurry"

DEFAULT_BLUR_THRESHOLD = 120.0
DEFAULT_HAND_CONFIDENCE = 0.5


@dataclass(frozen=True)
class GatekeeperResult:
    is_valid: bool
    issues: List[str]
    blur_variance: float
    hand_count: int


_hands = mp_solutions.hands.Hands(
    static_image_mode=True,
    max_num_hands=4,
    model_complexity=1,
    min_detection_confidence=0.35,
)
_hands_lock = Lock()


def _count_hands(image_bgr: np.ndarray, min_confidence: float) -> int:
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    with _hands_lock:
        results = _hands.process(image_rgb)
    handedness = getattr(results, "multi_handedness", None)
    if not handedness:
        return 0
    count = 0
    for hand in handedness:
        classification = getattr(hand, "classification", None)
        if not classification:
            continue
        if classification[0].score >= min_confidence:
            count += 1
    return count


def _laplacian_variance(image_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def validate_frame(
    image_bgr: np.ndarray,
    *,
    blur_threshold: float = DEFAULT_BLUR_THRESHOLD,
    hand_confidence: float = DEFAULT_HAND_CONFIDENCE,
) -> GatekeeperResult:
    """Return per-frame validation result for blur + occlusion."""
    issues: List[str] = []
    blur_variance = _laplacian_variance(image_bgr)
    if blur_variance < blur_threshold:
        issues.append(FRAME_BLURRY)

    hand_count = _count_hands(image_bgr, hand_confidence)
    if hand_count > 0:
        issues.append(HAND_DETECTED)

    return GatekeeperResult(is_valid=len(issues) == 0, issues=issues, blur_variance=blur_variance, hand_count=hand_count)
