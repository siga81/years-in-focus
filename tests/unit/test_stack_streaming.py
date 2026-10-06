from pathlib import Path

import numpy as np
import pytest

from facemovie.models import Landmarks
from facemovie.rendering import stack


@pytest.mark.parametrize("limit", [0, 1, 3])
@pytest.mark.parametrize("opening,closing,edge_fades", [(False, False, True), (True, True, True), (False, False, False)])
def test_streaming_preserves_stack_pixels_and_frame_count(monkeypatch, limit, opening, closing, edge_fades):
    layers = [
        (np.full((4, 6, 3), value, np.uint8), np.full((4, 6), alpha, np.uint8))
        for value, alpha in [(80, 200), (160, 128), (240, 64), (30, 180)]
    ]
    frames = []
    prepared = []

    class Writer:
        released = False

        def isOpened(self):
            return True

        def write(self, frame):
            frames.append(frame.copy())

        def release(self):
            self.released = True

    writer = Writer()
    monkeypatch.setattr(stack.cv2, "VideoWriter", lambda *_: writer)

    def prepare(path, *_):
        # The next card must be prepared after the preceding card was written.
        if prepared:
            assert frames
        prepared.append(int(path.stem))
        return layers[int(path.stem)]

    monkeypatch.setattr(stack, "_card_layer", prepare)
    monkeypatch.setattr(stack, "_static_slide_frame", lambda *_: np.full((4, 6, 3), 50, np.uint8))
    landmarks = Landmarks((1, 1), (3, 1), (2, 2), (1, 3), (3, 3), 1, (0, 0, 4, 4))
    entries = [(Path(f"{index}.jpg"), landmarks, 4) for index in range(4)]
    result = stack.render_stack_mp4(
        entries, Path("unused-test-output.mp4"), (6, 4), 10, .2, .1, .38, .033,
        max_visible_cards=limit,
        opening_slide=Path("opening.jpg") if opening else None,
        closing_slide=Path("closing.jpg") if closing else None,
        slide_seconds=.2, edge_fades=edge_fades,
    )
    expected_count = 12 + 2 * opening + 3 * closing - int(not edge_fades and not opening)
    assert result.frame_count == len(frames) == expected_count
    # Last card hold precedes the closing-slide transition and hold.
    expected_layers = layers[-limit:] if limit else layers
    expected = stack._compose([(*layer, 1.0) for layer in expected_layers], (6, 4))
    assert np.array_equal(frames[-4 if closing else -1], expected)
    assert prepared == list(range(4))
    assert writer.released


def test_writer_is_released_when_card_preparation_fails(monkeypatch):
    class Writer:
        released = False

        def isOpened(self):
            return True

        def release(self):
            self.released = True

    writer = Writer()
    monkeypatch.setattr(stack.cv2, "VideoWriter", lambda *_: writer)

    def fail(*_):
        raise OSError("Unreadable image")

    monkeypatch.setattr(stack, "_card_layer", fail)
    landmarks = Landmarks((1, 1), (3, 1), (2, 2), (1, 3), (3, 3), 1, (0, 0, 4, 4))
    with pytest.raises(OSError, match="Unreadable image"):
        stack.render_stack_mp4([(Path("0.jpg"), landmarks, 4)], Path("unused-test-output.mp4"), (6, 4), 10, .2, .1, .38, .033)
    assert writer.released
