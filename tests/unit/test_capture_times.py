from datetime import datetime

from facemovie.storyboard import parse_capture_time
from facemovie.models import ImageAnalysis
from facemovie.selection import capture_time_with_source, reduce_series

import pytest
from PIL import Image


def test_parse_capture_time_accepts_digikam_localized_date_time() -> None:
    assert parse_capture_time("10.10.2021 11:12:18") == datetime(2021, 10, 10, 11, 12, 18)


def test_parse_capture_time_accepts_iso_date_time() -> None:
    assert parse_capture_time("2021-10-10T11:12:18") == datetime(2021, 10, 10, 11, 12, 18)


def test_reduce_series_accepts_localized_digikam_date_times() -> None:
    first = ImageAnalysis("first.jpg", (1200, 800), "10.10.2021 11:12:18")
    second = ImageAnalysis("second.jpg", (1200, 800), "10.10.2021 11:12:25")
    first.status = second.status = "accepted"
    first.metrics["yunet_score"] = 0.8
    second.metrics["yunet_score"] = 0.9

    reduce_series([first, second], minimum_gap_minutes=7.5)

    assert first.status == "deferred"
    assert second.status == "accepted"


@pytest.mark.parametrize("camera,expected,source", [
    ({36867: "2016:09:17 15:53:48", 36868: "2017:01:01 00:00:00"}, datetime(2016, 9, 17, 15, 53, 48), "DateTimeOriginal"),
    ({36868: "2016:09:17 15:53:48"}, datetime(2016, 9, 17, 15, 53, 48), "DateTimeDigitized"),
    ({36867: "invalid", 36868: "2016:09:17 15:53:48"}, datetime(2016, 9, 17, 15, 53, 48), "DateTimeDigitized"),
    ({}, None, None),
    ({36867: "invalid", 36868: "invalid"}, None, None),
])
def test_real_jpeg_date_source_and_no_edit_date_fallback(tmp_path, camera, expected, source):
    path = tmp_path / "photo.jpg"
    exif = Image.Exif()
    exif[306] = "2023:04:26 21:44:49"
    if camera:
        exif[34665] = camera
    Image.new("RGB", (20, 20)).save(path, exif=exif)
    before = path.read_bytes()
    assert capture_time_with_source(path) == (expected, source)
    assert path.read_bytes() == before
    item = ImageAnalysis(path=str(path), source_size=(20, 20),
                         capture_time=expected.isoformat() if expected else None,
                         capture_time_source=source)
    assert item.as_dict()["capture_time_source"] == source


def test_missing_image_has_no_timestamp_source(tmp_path):
    assert capture_time_with_source(tmp_path / "missing.jpg") == (None, None)
