from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from facemovie.project import StoryboardCard, StoryboardProject
from facemovie.relink import find_unique_matches, normalised_path
from facemovie.storyboard import StoryboardApp


class RelinkTests(unittest.TestCase):
    @staticmethod
    def _image(path: Path, size: tuple[int, int]) -> None:
        Image.new("RGB", size, "white").save(path)

    def test_bulk_relink_accepts_one_same_name_and_saved_size(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "moved"
            root.mkdir()
            candidate = root / "family.jpg"
            self._image(candidate, (640, 480))
            old = "D:/photos/family.jpg"
            result = find_unique_matches([old], root, {normalised_path(old): (640, 480)})
            self.assertEqual(result.matches[old], candidate.resolve())
            self.assertFalse(result.ambiguous)
            self.assertFalse(result.unresolved)

    def test_bulk_relink_never_chooses_same_name_with_multiple_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "moved"
            (root / "a").mkdir(parents=True)
            (root / "b").mkdir()
            self._image(root / "a" / "family.jpg", (640, 480))
            self._image(root / "b" / "family.jpg", (640, 480))
            old = "D:/photos/family.jpg"
            result = find_unique_matches([old], root, {normalised_path(old): (640, 480)})
            self.assertFalse(result.matches)
            self.assertEqual(result.ambiguous, (old,))

    def test_export_preflight_considers_only_enabled_missing_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            available = root / "available.jpg"
            self._image(available, (32, 32))
            app = StoryboardApp.__new__(StoryboardApp)
            app.project = StoryboardProject(
                analysis_path="",
                cards=[
                    StoryboardCard(str(available), enabled=True),
                    StoryboardCard(str(root / "missing-enabled.jpg"), enabled=True),
                    StoryboardCard(str(root / "missing-disabled.jpg"), enabled=False),
                ],
            )
            self.assertEqual(
                app._missing_enabled_card_paths(),
                [str(root / "missing-enabled.jpg")],
            )


if __name__ == "__main__":
    unittest.main()
