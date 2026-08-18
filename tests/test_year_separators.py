"""Chronology separators are derived only from existing capture timestamps."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from facemovie.project import StoryboardCard, StoryboardProject
from facemovie.storyboard import StoryboardApp


class YearSeparatorTests(unittest.TestCase):
    def test_new_projects_show_year_separators_by_default(self) -> None:
        self.assertTrue(StoryboardProject(analysis_path="").show_year_separators)

    def test_capture_year_is_shown_only_for_date_sorting(self) -> None:
        card = StoryboardCard("C:/photos/example.jpg", False)
        translator = lambda key: {"date": "Date", "year_separator_undated": "Capture date unknown"}[key]
        app = SimpleNamespace(
            project=SimpleNamespace(show_year_separators=True),
            _sort_var=SimpleNamespace(get=lambda: "Date"),
            t=translator,
            _analysis_record=lambda _card: {"capture_time": "2024-06-20T14:30:00"},
        )
        self.assertEqual(StoryboardApp._year_separator_for_card(app, card), "2024")

        app._sort_var = SimpleNamespace(get=lambda: "Filename")
        self.assertIsNone(StoryboardApp._year_separator_for_card(app, card))

    def test_missing_capture_time_gets_a_separate_marker(self) -> None:
        card = StoryboardCard("C:/photos/undated.jpg", False)
        translator = lambda key: {"date": "Date", "year_separator_undated": "Capture date unknown"}[key]
        app = SimpleNamespace(
            project=SimpleNamespace(show_year_separators=True),
            _sort_var=SimpleNamespace(get=lambda: "Date"),
            t=translator,
            _analysis_record=lambda _card: {},
        )
        self.assertEqual(StoryboardApp._year_separator_for_card(app, card), "Capture date unknown")


if __name__ == "__main__":
    unittest.main()
