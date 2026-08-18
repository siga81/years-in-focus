"""Warnings from older German analysis data remain readable in English UI."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from facemovie.project import StoryboardProject
from facemovie.storyboard import StoryboardApp


class WarningTranslationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = SimpleNamespace(t=SimpleNamespace(language="en"))

    def test_translates_existing_german_analysis_warnings(self) -> None:
        self.assertEqual(
            StoryboardApp._friendly_warning(self.app, "Gesicht zu klein für Zielhöhe: 83px < 238px."),
            "Face too small for target height: 83px < 238px.",
        )
        self.assertEqual(
            StoryboardApp._friendly_warning(self.app, "Gesicht zu klein für die Zielhöhe: 127px < 238px."),
            "Face too small for target height: 127px < 238px.",
        )
        self.assertEqual(
            StoryboardApp._friendly_warning(self.app, "Keine Gesichtsregion für 'Laura Laszlo' gefunden."),
            "No face region found for 'Laura Laszlo'.",
        )
        self.assertIn(
            "Eye position for automatic alignment is uncertain",
            StoryboardApp._friendly_warning(self.app, "Niedrige YuNet-Konfidenz: 0.53."),
        )
        self.assertIn(
            "Eye position for automatic alignment is uncertain",
            StoryboardApp._friendly_warning(
                self.app,
                "Augenposition für die automatische Ausrichtung unsicher (Erkennungswert: 63 %).",
            ),
        )
        self.assertEqual(
            StoryboardApp._friendly_warning(
                self.app,
                "Die Augenposition für die automatische Ausrichtung konnte nicht sicher bestimmt werden.",
            ),
            "The eye position for automatic alignment could not be determined reliably.",
        )
        self.assertEqual(
            StoryboardApp._friendly_warning(
                self.app,
                "Zeitlich nahe Serienaufnahme: Auswahl auf 1 Bild(er) pro 5-Minuten-Cluster begrenzt.",
            ),
            "Closely timed burst photo: selection limited to 1 image(s) per 5 minute(s) cluster.",
        )

    def test_new_projects_show_face_region_in_preview_by_default(self) -> None:
        self.assertTrue(StoryboardProject(analysis_path="").preview_show_face_region)


if __name__ == "__main__":
    unittest.main()
