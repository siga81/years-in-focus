from __future__ import annotations

from datetime import datetime
from pathlib import Path

from facemovie.models import ImageAnalysis
from facemovie.selection import capture_time, reduce_series


def _item(name: str, timestamp: str, score: float) -> ImageAnalysis:
    return ImageAnalysis(
        path=name,
        source_size=(100, 100),
        capture_time=timestamp,
        status="accepted",
        metrics={"yunet_score": score, "face_height_ratio": 0.3},
    )


def test_reduce_series_keeps_best_item_per_time_cluster() -> None:
    first = _item("first.jpg", "2020-01-01T12:00:00", 0.7)
    better = _item("better.jpg", "2020-01-01T12:01:00", 0.9)
    later = _item("later.jpg", "2020-01-01T12:20:00", 0.6)

    reduce_series([first, better, later], minimum_gap_minutes=5, keep=1)

    assert first.status == "deferred"
    assert better.status == "accepted"
    assert later.status == "accepted"


def test_reduce_series_leaves_review_and_missing_times_untouched() -> None:
    review = _item("review.jpg", "2020-01-01T12:00:00", 0.1)
    review.status = "review"
    unknown_time = ImageAnalysis(path="unknown.jpg", source_size=(100, 100), status="accepted")

    reduce_series([review, unknown_time], minimum_gap_minutes=5)

    assert review.status == "review"
    assert unknown_time.status == "accepted"


def test_reduce_series_never_overrides_manual_acceptance() -> None:
    manual = _item("manual.jpg", "2020-01-01T12:00:00", 0.1)
    manual.manual_decision = "accept"
    automatic = _item("automatic.jpg", "2020-01-01T12:01:00", 0.9)

    reduce_series([manual, automatic], minimum_gap_minutes=5, keep=1)

    assert manual.status == "accepted"
    assert automatic.status == "deferred"


def test_reduce_series_prefers_the_more_frontal_photo_when_other_values_match() -> None:
    frontal = _item("frontal.jpg", "2020-01-01T12:00:00", 0.9)
    side_view = _item("side.jpg", "2020-01-01T12:01:00", 0.9)
    frontal.metrics["pose_yaw_degrees"] = 4.0
    side_view.metrics["pose_yaw_degrees"] = 28.0

    reduce_series([side_view, frontal], minimum_gap_minutes=5, keep=1)

    assert frontal.status == "accepted"
    assert side_view.status == "deferred"


def test_capture_time_prefers_nested_datetime_original_over_generic_datetime(monkeypatch) -> None:
    """JPEG camera timestamps are stored below ExifOffset, not at the root."""
    class FakeExif(dict):
        def get_ifd(self, tag: int) -> dict[int, str]:
            assert tag == 34665
            return {36867: "2018:12:13 14:22:31"}

    class FakeImage:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getexif(self) -> FakeExif:
            return FakeExif({306: "2023:06:21 22:25:51"})

    monkeypatch.setattr("facemovie.selection.Image.open", lambda _path: FakeImage())

    assert capture_time(Path("edited-photo.jpg")) == datetime(2018, 12, 13, 14, 22, 31)
