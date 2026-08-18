from __future__ import annotations

import numpy as np

from facemovie.alignment import (
    face_anchored_scale,
    render_face_normalized_image,
    render_full_image,
    similarity_matrix,
)
from facemovie.models import Landmarks


def test_similarity_matrix_maps_eye_midpoint_to_target() -> None:
    landmarks = Landmarks((100, 200), (200, 200), (150, 240), (120, 280), (180, 280), 0.9, (80, 150, 140, 160))
    matrix = similarity_matrix(landmarks, (1000, 500), 0.4, 0.2)
    point = matrix[:, :2] @ np.asarray([150.0, 200.0]) + matrix[:, 2]
    assert np.allclose(point, [500.0, 200.0])


def test_rotation_can_be_disabled() -> None:
    landmarks = Landmarks((100, 100), (200, 130), (150, 150), (120, 180), (180, 185), 0.9, (70, 60, 180, 180))
    matrix = similarity_matrix(landmarks, (1000, 500), 0.4, 0.2, rotation_strength=0.0)
    assert np.allclose(matrix[0, 1], 0.0)


def test_full_rotation_makes_both_eyes_horizontal_and_centred() -> None:
    landmarks = Landmarks((100, 100), (200, 130), (150, 150), (120, 180), (180, 185), 0.9, (70, 60, 180, 180))
    matrix = similarity_matrix(landmarks, (1000, 500), 0.4, 0.2, rotation_strength=1.0)
    left = matrix[:, :2] @ np.asarray(landmarks.left_eye) + matrix[:, 2]
    right = matrix[:, :2] @ np.asarray(landmarks.right_eye) + matrix[:, 2]
    assert np.isclose(left[1], right[1])
    assert np.allclose((left + right) / 2, (500.0, 200.0))
    assert np.isclose(np.linalg.norm(right - left), 200.0)


def test_full_image_renderer_preserves_entire_source_and_adds_background() -> None:
    image = np.full((100, 200, 3), 50, dtype=np.uint8)
    rendered = render_full_image(image, (200, 200), "black")
    assert rendered.shape == (200, 200, 3)
    assert np.all(rendered[0] == 0)
    assert np.all(rendered[50:150] == 50)


def test_face_anchored_scale_keeps_an_off_center_face_and_whole_image_visible() -> None:
    scale = face_anchored_scale((200, 100), (20, 20), (200, 200), 0.4)
    assert np.isclose(scale, 100 / 180)


def test_face_normalized_renderer_keeps_output_size() -> None:
    image = np.full((100, 200, 3), 100, dtype=np.uint8)
    landmarks = Landmarks((80, 40), (120, 40), (100, 55), (90, 70), (110, 70), 0.9, (60, 20, 80, 70))
    rendered, scale = render_face_normalized_image(image, landmarks, (200, 200), 0.4, 0.2)
    assert rendered.shape == (200, 200, 3)
    assert np.isclose(scale, 1.0)
