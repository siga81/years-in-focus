import numpy as np
import pytest

from facemovie.vision.mediapipe_landmarker import DenseFaceLandmarks


def test_eye_geometry_uses_eye_corners_not_gaze_position() -> None:
    points = np.zeros((478, 3), dtype=np.float64)
    points[33, :2] = (10, 20)
    points[133, :2] = (20, 20)
    points[362, :2] = (40, 20)
    points[263, :2] = (50, 20)
    points[468:473, :2] = (13, 22)
    points[473:478, :2] = (47, 18)
    geometry = DenseFaceLandmarks(points)
    assert np.allclose(geometry.right_eye_center, (15, 20))
    assert np.allclose(geometry.left_eye_center, (45, 20))
    assert geometry.eye_distance == 30
    iris = geometry.as_sparse_landmarks("iris")
    assert iris.left_eye == (13.0, 22.0)
    assert iris.right_eye == (47.0, 18.0)


def test_head_pose_reports_yaw_from_facial_transform() -> None:
    angle = np.deg2rad(30)
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = np.array(
        [[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]],
        dtype=np.float64,
    )
    pose = DenseFaceLandmarks(np.zeros((478, 3), dtype=np.float64), transform).head_pose_degrees()
    assert pose is not None
    assert pose["pose_yaw_degrees"] == pytest.approx(30.0)
