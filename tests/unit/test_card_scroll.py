from types import SimpleNamespace
from unittest.mock import Mock

from facemovie.project import StoryboardCard, StoryboardProject
from facemovie.storyboard import StoryboardApp


def _app():
    app = StoryboardApp.__new__(StoryboardApp)
    app.project = StoryboardProject(analysis_path="", cards=[StoryboardCard("photo.jpg", True)])
    app._filtered_card_indices = [0]
    app._build_card_grid = Mock()
    app.update_card_styles = Mock()
    app.refresh_inspector = Mock()
    app._update_duration_label = Mock()
    return app


def test_toggle_with_unchanged_filter_membership_keeps_widgets():
    app = _app()
    app._card_matches_filter = lambda card: True
    app.toggle(0)
    assert not app.project.cards[0].enabled
    app._build_card_grid.assert_not_called()
    app.update_card_styles.assert_called_once_with({0})


def test_toggle_removing_card_captures_anchor_before_rebuild():
    app = _app()
    app._card_matches_filter = lambda card: card.enabled
    app._capture_card_scroll_anchor = Mock(return_value=(2, -12.0))
    app.toggle(0)
    assert app._card_scroll_restore == (2, -12.0)
    app._build_card_grid.assert_called_once()
    app.update_card_styles.assert_not_called()


def test_anchor_uses_next_surviving_card_and_pixel_offset():
    app = _app()
    app.project.cards = [StoryboardCard(str(i), i != 1) for i in range(3)]
    app._visible_card_indices = [0, 1, 2]
    app._card_widgets = [(SimpleNamespace(winfo_y=lambda y=y: y, winfo_height=lambda: 90), None, None, None)
                         for y in (0, 100, 200)]
    app.root = SimpleNamespace(update_idletasks=lambda: None)
    app.canvas = SimpleNamespace(canvasy=lambda _: 120)
    app._card_matches_filter = lambda card: card.enabled
    assert app._capture_card_scroll_anchor() == (2, 80)


def test_finish_grid_restores_anchor_after_layout():
    app = _app()
    app.root = SimpleNamespace(update_idletasks=lambda: None)
    app.canvas = Mock()
    app.canvas.bbox.return_value = (0, 0, 500, 1000)
    app._card_scroll_restore = (2, 80)
    app._visible_card_indices = [2]
    app._card_widgets = [(SimpleNamespace(winfo_y=lambda: 300), None, None, None)]
    app._grid_rebuild_pending = False
    app._update_sticky_year_separator = Mock()
    app._finish_card_grid_build()
    app.canvas.yview_moveto.assert_called_once_with(.22)
    assert app._card_scroll_restore is None


def test_page_change_clears_anchor_and_requests_top():
    app = _app()
    app._filtered_card_indices = list(range(500))
    app._card_page = 0
    app._card_scroll_restore = (2, 80)
    app._set_card_page(1)
    assert app._card_page == 1
    assert app._card_scroll_restore is None
    assert app._card_scroll_to_top
    app._build_card_grid.assert_called_once()


def test_page_layout_scrolls_to_top():
    app = _app()
    app.root = SimpleNamespace(update_idletasks=lambda: None)
    app.canvas = Mock()
    app.canvas.bbox.return_value = (0, 0, 500, 1000)
    app._card_scroll_restore = None
    app._card_scroll_to_top = True
    app._grid_rebuild_pending = False
    app._update_sticky_year_separator = Mock()
    app._finish_card_grid_build()
    app.canvas.yview_moveto.assert_called_once_with(0)
    assert not app._card_scroll_to_top
