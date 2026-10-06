from __future__ import annotations

import json
from pathlib import Path

from facemovie.project import StoryboardCard, StoryboardProject
import pytest


def test_project_roundtrip(tmp_path: Path) -> None:
    project = StoryboardProject(
        analysis_path="C:/input/analysis.json",
        cards=[StoryboardCard(
            "C:/input/photo.jpg", True, rotation_degrees=1.5, scale=0.9,
            eye_override=[[101.0, 202.0], [303.0, 404.0]],
        )],
        title="Testfilm",
        person_name="Testperson",
        hold_seconds=3.5,
        transition_seconds=0.6,
        edge_fades_enabled=False,
        fps=25.0,
        output_width=1280,
        output_height=720,
        movie_mode="timelapse",
        timelapse_frames_per_image=4,
        timelapse_transition_frames=1,
        timelapse_max_images_per_year=2,
        timelapse_frontal_only=False,
        eye_distance=0.03,
        series_minimum_gap_minutes=2.5,
        play_after_export=True,
        opening_slide_path="C:/input/opening.png",
        closing_slide_path="C:/input/closing.jpg",
        output_quality="high",
        advanced_output_options=True,
        selection_quality_level=1,
        maximum_side_view_degrees=32.0,
    )
    target = tmp_path / "test.facemovie.json"
    project.save(target)
    loaded = StoryboardProject.load(target)
    assert loaded.title == "Testfilm"
    assert loaded.cards[0].rotation_degrees == 1.5
    assert loaded.cards[0].scale == 0.9
    assert loaded.cards[0].eye_override == [[101.0, 202.0], [303.0, 404.0]]
    assert loaded.person_name == "Testperson"
    assert loaded.hold_seconds == 3.5
    assert loaded.transition_seconds == 0.6
    assert loaded.edge_fades_enabled is False
    assert loaded.fps == 25.0
    assert (loaded.output_width, loaded.output_height) == (1280, 720)
    assert loaded.movie_mode == "timelapse"
    assert loaded.timelapse_frames_per_image == 4
    assert loaded.timelapse_transition_frames == 1
    assert loaded.timelapse_max_images_per_year == 2
    assert loaded.timelapse_frontal_only is False
    assert loaded.eye_distance == 0.03
    assert loaded.series_minimum_gap_minutes == 2.5
    assert loaded.play_after_export is True
    assert loaded.opening_slide_path == "C:/input/opening.png"
    assert loaded.closing_slide_path == "C:/input/closing.jpg"
    assert loaded.slide_seconds == 3.0
    assert (loaded.preview_width, loaded.preview_height) == (1280, 720)
    assert loaded.output_quality == "high"
    assert loaded.advanced_output_options is True
    assert loaded.selection_quality_level == 1
    assert loaded.maximum_side_view_degrees == 32.0


def test_project_ignores_retired_lively_stack_setting(tmp_path: Path) -> None:
    target = tmp_path / "legacy.facemovie.json"
    target.write_text(json.dumps({
        "version": 1,
        "analysis_path": "C:/input/analysis.json",
        "cards": [],
        "settings": {"rotation_jitter": 4.0},
    }), encoding="utf-8")

    project = StoryboardProject.load(target)
    project.save(target)

    saved = json.loads(target.read_text(encoding="utf-8"))
    assert "rotation_jitter" not in saved["settings"]


def test_failed_save_preserves_previous_project(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "project.yif.json"
    project = StoryboardProject(analysis_path="", title="Saved")
    project.save(target)
    original = target.read_bytes()
    project.title = "Unsaved"

    def fail(*_):
        raise OSError("Replace failed")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="Replace failed"):
        project.save(target)
    assert target.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def _movable_project(root):
    data = root / "Film.yif-Daten"
    data.mkdir(parents=True)
    analysis = data / "analysis.json"
    source = str((root.parent / "original.jpg").resolve())
    analysis.write_text(json.dumps([{"path": source, "capture_time": "2001-07-30T12:00:00"}]), encoding="utf-8")
    project = StoryboardProject(analysis_path=str(analysis), cards=[StoryboardCard(source, True)])
    target = root / "Film.yif.json"
    project.save(target)
    return target, analysis


def test_relative_analysis_survives_project_folder_move(tmp_path):
    target, analysis = _movable_project(tmp_path / "old")
    assert not Path(json.loads(target.read_text(encoding="utf-8"))["analysis_path"]).is_absolute()
    new = tmp_path / "new"
    target.parent.rename(new)
    loaded = StoryboardProject.load(new / target.name)
    assert Path(loaded.analysis_path) == new / analysis.parent.name / analysis.name
    assert Path(loaded.analysis_path).is_file()


def test_legacy_absolute_analysis_recovered_only_when_matching(tmp_path):
    target, analysis = _movable_project(tmp_path / "old")
    raw = json.loads(target.read_text(encoding="utf-8"))
    raw["analysis_path"] = str(analysis)
    target.write_text(json.dumps(raw), encoding="utf-8")
    new = tmp_path / "new"
    target.parent.rename(new)
    loaded = StoryboardProject.load(new / target.name)
    assert loaded.analysis_recovered
    assert Path(loaded.analysis_path).is_file()
    loaded.save(new / target.name)
    assert "analysis_recovered" not in json.loads((new / target.name).read_text(encoding="utf-8"))["settings"]
    (new / analysis.parent.name / analysis.name).write_text('[{"path":"wrong.jpg"}]', encoding="utf-8")
    rejected = StoryboardProject.load(new / target.name)
    # Existing relative paths are resolved normally; recovery validates missing paths.
    raw["analysis_path"] = str(analysis)
    (new / target.name).write_text(json.dumps(raw), encoding="utf-8")
    rejected = StoryboardProject.load(new / target.name)
    assert rejected.analysis_path == str(analysis)
    assert not getattr(rejected, "analysis_recovered", False)


def test_analysis_recovery_rejects_ambiguous_candidates(tmp_path):
    target, analysis = _movable_project(tmp_path / "project")
    other = target.parent / "other"
    other.mkdir()
    (other / "analysis.json").write_bytes(analysis.read_bytes())
    raw = json.loads(target.read_text(encoding="utf-8"))
    raw["analysis_path"] = str(tmp_path / "missing" / "other" / "analysis.json")
    target.write_text(json.dumps(raw), encoding="utf-8")
    loaded = StoryboardProject.load(target)
    assert not getattr(loaded, "analysis_recovered", False)
    assert not Path(loaded.analysis_path).exists()


def test_external_analysis_stays_absolute(tmp_path):
    analysis = tmp_path / "external" / "analysis.json"
    target = tmp_path / "project" / "Film.yif.json"
    StoryboardProject(analysis_path=str(analysis)).save(target)
    assert json.loads(target.read_text(encoding="utf-8"))["analysis_path"] == str(analysis)


def test_project_preserves_card_view_preferences(tmp_path):
    target = tmp_path / "view.yif.json"
    project = StoryboardProject(analysis_path="", card_size="large", card_sort="name",
                                card_filters=["used_only", "suitable"])
    project.save(target)
    loaded = StoryboardProject.load(target)
    assert loaded.card_size == "large"
    assert loaded.card_sort == "name"
    assert loaded.card_filters == ["used_only", "suitable"]
