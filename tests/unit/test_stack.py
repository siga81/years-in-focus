from __future__ import annotations

from pathlib import Path

from PIL import Image

from facemovie.models import Landmarks
from facemovie.rendering.stack import (
    _static_slide_frame,
    card_fits,
    median_face_ratio,
    normalized_scale,
)


def test_card_eligibility_rejects_too_large_projected_card() -> None:
    landmarks = Landmarks((90, 100), (110, 100), (100, 120), (95, 140), (105, 140), 0.9, (70, 70, 60, 100))
    fits, _ = card_fits((1000, 750), landmarks, (1000, 750), 0.04, 10, 0.85)
    assert not fits


def test_blended_scale_reduces_face_height_variation() -> None:
    narrow = Landmarks((0, 0), (100, 0), (50, 30), (25, 60), (75, 60), 0.9, (0, 0, 200, 410))
    wide = Landmarks((0, 0), (250, 0), (125, 60), (65, 130), (185, 130), 0.9, (0, 0, 500, 690))
    ratio = (4.1 + 2.76) / 2
    narrow_scale = normalized_scale(narrow, 1920, 0.04, ratio, 0.5)
    wide_scale = normalized_scale(wide, 1920, 0.04, ratio, 0.5)
    assert (narrow.face_box[3] * narrow_scale) / (wide.face_box[3] * wide_scale) < 1.25


def test_xmp_region_height_can_define_perceived_face_size() -> None:
    small = Landmarks((0, 0), (90, 0), (45, 30), (20, 60), (70, 60), 0.9, (0, 0, 180, 260))
    portrait = Landmarks((0, 0), (300, 0), (150, 80), (80, 180), (220, 180), 0.9, (0, 0, 560, 600))
    target_ratio = median_face_ratio([small, portrait], [240, 1900])
    small_scale = normalized_scale(small, 1920, 0.04, target_ratio, 0.0, 240)
    portrait_scale = normalized_scale(portrait, 1920, 0.04, target_ratio, 0.0, 1900)
    assert abs(240 * small_scale - 1900 * portrait_scale) < 1e-6


def test_static_slide_is_contained_without_distortion(tmp_path: Path) -> None:
    source = tmp_path / "portrait.png"
    Image.new("RGB", (100, 200), "red").save(source)
    frame = _static_slide_frame(source, (400, 200))
    assert frame.shape == (200, 400, 3)
    assert frame[100, 200].tolist() == [0, 0, 255]
    assert frame[100, 20].tolist() == [0, 0, 0]
