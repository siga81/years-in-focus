from facemovie.project import StoryboardCard, StoryboardProject
from facemovie.storyboard import StoryboardApp


def test_next_enabled_card_skips_inactive_cards_without_wrapping() -> None:
    app = object.__new__(StoryboardApp)
    app.selected_index = 0
    app.project = StoryboardProject(
        analysis_path="",
        cards=[
            StoryboardCard("first.jpg", True),
            StoryboardCard("second.jpg", False),
            StoryboardCard("third.jpg", True),
        ],
    )

    assert app._next_enabled_card_index() == 2
    app.selected_index = 2
    assert app._next_enabled_card_index() is None


def test_previous_enabled_card_skips_inactive_cards_without_wrapping():
    app = object.__new__(StoryboardApp)
    app.project = StoryboardProject(analysis_path="", cards=[
        StoryboardCard("first.jpg", True), StoryboardCard("second.jpg", False),
        StoryboardCard("third.jpg", True)])
    app.selected_index = 2
    assert app._previous_enabled_card_index() == 0
    app.selected_index = 0
    assert app._previous_enabled_card_index() is None


import pytest


@pytest.mark.parametrize("old_scale,new_scale", [(0.37, .444), (2.4, 2.0), (.5, .5)])
def test_zoom_keeps_pixel_under_pointer_with_existing_pan(old_scale, new_scale):
    pointer, viewport, image_size, pan = (731, 219), (1000, 700), (1733, 997), (63, -41)
    new_pan = StoryboardApp._zoom_pan_at_pointer(pointer, viewport, image_size, old_scale, new_scale, pan)
    for cursor, extent, pixels, old_offset, new_offset in zip(pointer, viewport, image_size, pan, new_pan):
        old_origin = extent / 2 + old_offset - round(pixels * old_scale) / 2
        source_pixel = (cursor - old_origin) / old_scale
        new_origin = extent / 2 + new_offset - round(pixels * new_scale) / 2
        assert new_origin + source_pixel * new_scale == pytest.approx(cursor)
