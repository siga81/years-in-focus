from __future__ import annotations

from facemovie.cli import _landmarks_with_eye_override
from facemovie.models import Landmarks


def test_eye_override_replaces_only_eye_anchors() -> None:
    original = Landmarks(
        left_eye=(10.0, 20.0), right_eye=(30.0, 40.0), nose=(21.0, 30.0),
        left_mouth=(15.0, 50.0), right_mouth=(27.0, 50.0), score=1.0,
        face_box=(0.0, 0.0, 100.0, 120.0),
    )

    adjusted = _landmarks_with_eye_override(original, [[11.5, 22.5], [31.5, 42.5]])

    assert adjusted.left_eye == (11.5, 22.5)
    assert adjusted.right_eye == (31.5, 42.5)
    assert adjusted.nose == original.nose
    assert adjusted.face_box == original.face_box


def test_invalid_eye_override_keeps_automatic_geometry() -> None:
    original = Landmarks(
        left_eye=(10.0, 20.0), right_eye=(30.0, 40.0), nose=(21.0, 30.0),
        left_mouth=(15.0, 50.0), right_mouth=(27.0, 50.0), score=1.0,
        face_box=(0.0, 0.0, 100.0, 120.0),
    )

    assert _landmarks_with_eye_override(original, [[1.0, 2.0]]) == original
