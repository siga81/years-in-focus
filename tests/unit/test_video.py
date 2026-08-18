from __future__ import annotations

import pytest

from facemovie.rendering.video import frame_counts


def test_frame_counts_for_standard_video_settings() -> None:
    assert frame_counts(30, 4.0, 0.8) == (120, 24)


def test_frame_counts_rejects_invalid_settings() -> None:
    with pytest.raises(ValueError):
        frame_counts(0, 4.0, 0.8)
