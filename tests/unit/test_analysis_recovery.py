import json
from types import SimpleNamespace

import pytest

from facemovie.i18n import Translator
from facemovie.project import StoryboardCard, StoryboardProject
from facemovie.storyboard import StoryboardApp


@pytest.mark.parametrize("payload", [None, "broken JSON", '{}'])
def test_missing_analysis_is_distinguished_from_unknown_capture_date(tmp_path, payload):
    analysis = tmp_path / "analysis.json"
    if payload is not None:
        analysis.write_text(payload, encoding="utf-8")
    app = StoryboardApp.__new__(StoryboardApp)
    card = StoryboardCard(str(tmp_path / "photo.jpg"), True)
    app.project = StoryboardProject(analysis_path=str(analysis), cards=[card])
    app.t = Translator("de")
    app._sort_var = SimpleNamespace(get=lambda: app.t("date"))
    app._analysis_by_path = None
    assert app._year_separator_for_card(card) == "Analysedaten fehlen"
    assert app._card_quality(card)[2] == "Analysedaten fehlen"
    assert not app._analysis_available()
    analysis.write_text(json.dumps([{"path": card.source_path, "capture_time": None}]), encoding="utf-8")
    app._analysis_by_path = None
    assert app._year_separator_for_card(card) == "Aufnahmedatum unbekannt"
