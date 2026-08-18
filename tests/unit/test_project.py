from __future__ import annotations

import json
from pathlib import Path

from facemovie.project import StoryboardCard, StoryboardProject


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
