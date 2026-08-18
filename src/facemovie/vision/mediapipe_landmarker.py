"""Dense local face geometry inside an existing XMP person region."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

from facemovie.models import FaceRegion, Landmarks

# MediaPipe Face Mesh V2 topology.  Names follow the subject; the subject's
# right eye appears on the left side of a frontal image.
RIGHT_EYE_CORNERS = (33, 133)
LEFT_EYE_CORNERS = (362, 263)
RIGHT_IRIS = (468, 469, 470, 471, 472)
LEFT_IRIS = (473, 474, 475, 476, 477)


@dataclass(frozen=True)
class DenseFaceLandmarks:
    """478 landmarks mapped back to oriented source-image coordinates."""

    points: np.ndarray
    facial_transform: np.ndarray | None = None

    def _mean(self, indices: tuple[int, ...]) -> np.ndarray:
        return self.points[np.asarray(indices), :2].mean(axis=0)

    @property
    def right_eye_center(self) -> np.ndarray:
        """Anatomically stable center between the two eye corners."""
        return self._mean(RIGHT_EYE_CORNERS)

    @property
    def left_eye_center(self) -> np.ndarray:
        return self._mean(LEFT_EYE_CORNERS)

    @property
    def right_iris_center(self) -> np.ndarray:
        return self._mean(RIGHT_IRIS)

    @property
    def left_iris_center(self) -> np.ndarray:
        return self._mean(LEFT_IRIS)

    @property
    def eye_midpoint(self) -> np.ndarray:
        return (self.right_eye_center + self.left_eye_center) / 2.0

    @property
    def eye_distance(self) -> float:
        return float(np.linalg.norm(self.left_eye_center - self.right_eye_center))

    def as_sparse_landmarks(self, eye_anchor: str = "contour") -> Landmarks:
        """Expose precise eye geometry to the existing card renderer."""
        if eye_anchor == "contour":
            right_eye, left_eye = self.right_eye_center, self.left_eye_center
        elif eye_anchor == "iris":
            right_eye, left_eye = self.right_iris_center, self.left_iris_center
        else:
            raise ValueError("eye_anchor muss 'contour' oder 'iris' sein.")
        xy = self.points[:, :2]
        minimum = xy.min(axis=0)
        maximum = xy.max(axis=0)
        nose = self.points[1, :2]
        right_mouth = self.points[61, :2]
        left_mouth = self.points[291, :2]
        return Landmarks(
            left_eye=tuple(right_eye),
            right_eye=tuple(left_eye),
            nose=tuple(nose),
            left_mouth=tuple(right_mouth),
            right_mouth=tuple(left_mouth),
            score=1.0,
            face_box=(
                float(minimum[0]), float(minimum[1]),
                float(maximum[0] - minimum[0]), float(maximum[1] - minimum[1]),
            ),
        )

    def head_pose_degrees(self) -> dict[str, float] | None:
        """Return approximate yaw, pitch and roll from MediaPipe's face transform."""
        if self.facial_transform is None or self.facial_transform.shape != (4, 4):
            return None
        rotation = self.facial_transform[:3, :3]
        left, _singular, right = np.linalg.svd(rotation)
        rotation = left @ right
        if np.linalg.det(rotation) < 0:
            left[:, -1] *= -1
            rotation = left @ right
        yaw = np.degrees(np.arctan2(rotation[0, 2], rotation[2, 2]))
        pitch = np.degrees(np.arctan2(-rotation[1, 2], np.hypot(rotation[0, 2], rotation[2, 2])))
        roll = np.degrees(np.arctan2(rotation[1, 0], rotation[0, 0]))
        return {
            "pose_yaw_degrees": float(yaw),
            "pose_pitch_degrees": float(pitch),
            "pose_roll_degrees": float(roll),
        }


class MediaPipeFaceLandmarker:
    """MediaPipe Face Landmarker constrained by an existing person rectangle."""

    def __init__(self, model_path: Path, min_presence: float = 0.5) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"MediaPipe-Modell nicht gefunden: {model_path}")
        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=min_presence,
            min_face_presence_confidence=min_presence,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> MediaPipeFaceLandmarker:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def detect(self, image_bgr: np.ndarray, region: FaceRegion, margin: float = 0.35) -> DenseFaceLandmarks | None:
        height, width = image_bgr.shape[:2]
        if region.coordinate_system == "pixel_left_top":
            region_x, region_y = region.x, region.y
            region_width, region_height = region.width, region.height
        else:
            region_x, region_y = region.x * width, region.y * height
            region_width, region_height = region.width * width, region.height * height
        # Tight digiKam/XMP rectangles are ideal in group photos, but very small
        # distant faces sometimes need more surrounding context.  Expand only
        # after a failed attempt so the marked person remains the central target.
        search_margins = tuple(dict.fromkeys((margin, max(margin, 0.75), max(margin, 1.0))))
        for search_margin in search_margins:
            x1 = max(0, round(region_x - region_width * search_margin))
            y1 = max(0, round(region_y - region_height * search_margin))
            x2 = min(width, round(region_x + region_width + region_width * search_margin))
            y2 = min(height, round(region_y + region_height + region_height * search_margin))
            if x2 <= x1 or y2 <= y1:
                continue

            crop_bgr = image_bgr[y1:y2, x1:x2]
            crop_rgb = np.ascontiguousarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=crop_rgb)
            result = self._landmarker.detect(mp_image)
            if not result.face_landmarks:
                continue

            crop_height, crop_width = crop_bgr.shape[:2]
            points = np.asarray(
                [
                    (x1 + point.x * crop_width, y1 + point.y * crop_height, point.z * crop_width)
                    for point in result.face_landmarks[0]
                ],
                dtype=np.float64,
            )
            matrix = None
            if result.facial_transformation_matrixes:
                matrix = np.asarray(result.facial_transformation_matrixes[0], dtype=np.float64)
            return DenseFaceLandmarks(points=points, facial_transform=matrix)
        return None
