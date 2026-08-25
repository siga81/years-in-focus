"""Sorting a storyboard must never change the user's film selection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from facemovie.project import StoryboardCard, StoryboardProject
from facemovie.storyboard import StoryboardApp


class SortPreservesSelectionTests(unittest.TestCase):
    def test_side_view_limit_only_affects_automatic_candidates(self) -> None:
        app = object.__new__(StoryboardApp)
        app.project = StoryboardProject(analysis_path="analysis.json", maximum_side_view_degrees=20.0)

        self.assertTrue(StoryboardApp._pose_is_accepted(app, {"metrics": {"pose_yaw_degrees": -19.0}}))
        self.assertFalse(StoryboardApp._pose_is_accepted(app, {"metrics": {"pose_yaw_degrees": 21.0}}))
        self.assertFalse(StoryboardApp._pose_is_accepted(app, {"metrics": {}}))

    def test_date_sort_reorders_cards_without_changing_enabled_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "later.JPG"
            second = root / "earlier.JPG"
            records = [
                {"path": str(first), "capture_time": "2025-06-20T12:00:00"},
                {"path": str(second), "capture_time": "2020-01-02T12:00:00"},
            ]
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(records), encoding="utf-8")
            project = StoryboardProject(
                analysis_path=str(analysis_path),
                cards=[StoryboardCard(str(first), True), StoryboardCard(str(second), False)],
            )
            app = object.__new__(StoryboardApp)
            app.project = project
            app.selected_index = 0
            app._card_page = 0
            app._build_card_grid = lambda: None
            app.refresh_inspector = lambda: None

            StoryboardApp.sort_cards(app, "date")

            self.assertEqual(
                [(Path(card.source_path).name, card.enabled) for card in project.cards],
                [("earlier.JPG", False), ("later.JPG", True)],
            )


if __name__ == "__main__":
    unittest.main()
