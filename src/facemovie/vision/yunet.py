"""YuNet-Landmarken innerhalb einer bereits bekannten Personenregion."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from facemovie.models import FaceRegion, Landmarks


class YuNetLandmarker:
    # The manual dialog is an aid, not a face-identification result.  A stricter
    # threshold deliberately favours a few credible suggestions over a noisy
    # overlay of false positives.  The user can always draw the region instead.
    CANDIDATE_MIN_SCORE = 0.65
    MAX_CANDIDATES = 6
    def __init__(self, model_path: Path, score_threshold: float = 0.42) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"YuNet-Modell nicht gefunden: {model_path}")
        self.score_threshold = score_threshold
        self.detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (320, 320), score_threshold, 0.3, 5000
        )

    def detect_candidates(self, image_bgr: np.ndarray, name: str = "") -> list[FaceRegion]:
        """Return face rectangles for explicit user confirmation.

        Candidate detection is not person identification.  The manual-region
        assistant must ask the user to choose one of these rectangles before it
        is used as the target person.
        """
        height, width = image_bgr.shape[:2]
        if width < 2 or height < 2:
            return []
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(image_bgr)
        if faces is None:
            return []
        # FaceDetectorYN is configured more permissively for the later landmark
        # pass.  Filter its raw suggestions here, where distracting false positives
        # are worse than a missing suggestion that can be marked manually.
        accepted: list[np.ndarray] = []
        for face in sorted(faces, key=lambda item: float(item[14]), reverse=True):
            if float(face[14]) < self.CANDIDATE_MIN_SCORE:
                continue
            if any(self._iou(face, other) >= 0.35 for other in accepted):
                continue
            accepted.append(face)
            if len(accepted) >= self.MAX_CANDIDATES:
                break

        candidates: list[FaceRegion] = []
        for face in accepted:
            x, y, face_width, face_height = (float(face[index]) for index in range(4))
            x = max(0.0, x)
            y = max(0.0, y)
            face_width = min(face_width, float(width) - x)
            face_height = min(face_height, float(height) - y)
            if face_width <= 1 or face_height <= 1:
                continue
            candidates.append(FaceRegion(
                name=name, x=x, y=y, width=face_width, height=face_height,
                coordinate_system="pixel_left_top", source="yunet_candidate",
            ))
        return candidates

    @staticmethod
    def _iou(first: np.ndarray, second: np.ndarray) -> float:
        """Return overlap for two detector boxes (x, y, width, height)."""
        x1, y1 = max(float(first[0]), float(second[0])), max(float(first[1]), float(second[1]))
        x2 = min(float(first[0] + first[2]), float(second[0] + second[2]))
        y2 = min(float(first[1] + first[3]), float(second[1] + second[3]))
        intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        union = float(first[2] * first[3] + second[2] * second[3]) - intersection
        return intersection / union if union > 0 else 0.0

    def detect(self, image_bgr: np.ndarray, region: FaceRegion) -> Landmarks | None:
        height, width = image_bgr.shape[:2]
        if region.coordinate_system == "pixel_left_top":
            x1 = max(0, round(region.x))
            y1 = max(0, round(region.y))
            x2 = min(width, round(region.x + region.width))
            y2 = min(height, round(region.y + region.height))
        else:
            x1 = max(0, round(region.x * width))
            y1 = max(0, round(region.y * height))
            x2 = min(width, round((region.x + region.width) * width))
            y2 = min(height, round((region.y + region.height) * height))
        if x2 <= x1 or y2 <= y1:
            return None

        crop = image_bgr[y1:y2, x1:x2]
        # A border lets YuNet retain landmarks when digiKam's region is tight.
        border = max(20, round(max(crop.shape[:2]) * 0.15))
        bordered = cv2.copyMakeBorder(
            crop, border, border, border, border, cv2.BORDER_CONSTANT, value=(0, 0, 0)
        )
        self.detector.setInputSize((bordered.shape[1], bordered.shape[0]))
        _, faces = self.detector.detect(bordered)
        if faces is None or len(faces) == 0:
            return None

        # The central, highest-confidence candidate best matches a marked region.
        center = np.array([bordered.shape[1] / 2, bordered.shape[0] / 2])
        def ranking(face: np.ndarray) -> tuple[float, float]:
            face_center = np.array([face[0] + face[2] / 2, face[1] + face[3] / 2])
            return (float(face[14]), -float(np.linalg.norm(face_center - center)))

        face = max(faces, key=ranking)
        offset_x, offset_y = x1 - border, y1 - border
        points = [(float(face[index]) + offset_x, float(face[index + 1]) + offset_y)
                  for index in range(4, 14, 2)]
        return Landmarks(
            left_eye=points[0], right_eye=points[1], nose=points[2],
            left_mouth=points[3], right_mouth=points[4], score=float(face[14]),
            face_box=(
                float(face[0]) + offset_x, float(face[1]) + offset_y,
                float(face[2]), float(face[3]),
            ),
        )
