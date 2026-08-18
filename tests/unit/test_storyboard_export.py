from __future__ import annotations

from pathlib import Path

from facemovie.project import StoryboardProject
from facemovie.storyboard import build_export_command


def test_export_command_uses_project_settings_and_iris_alignment(tmp_path: Path) -> None:
    project = StoryboardProject(
        analysis_path="C:/input/analysis.json",
        person_name="Testperson",
        output_width=1280,
        output_height=720,
    )
    command = build_export_command(
        "python",
        tmp_path,
        tmp_path / "test.facemovie.json",
        project,
        tmp_path / "movie.mp4",
    )
    assert command[:3] == ["python", "-m", "facemovie.cli"]
    assert command[command.index("--width") + 1] == "1280"
    assert command[command.index("--height") + 1] == "720"
    assert command[command.index("--person") + 1] == "Testperson"
    assert command[command.index("--eye-anchor") + 1] == "iris"
    assert command[command.index("--mediapipe-model") + 1].endswith("models\\mediapipe\\face_landmarker.task")


def test_preview_command_overrides_only_resolution(tmp_path: Path) -> None:
    project = StoryboardProject(analysis_path="analysis.json", person_name="Testperson")
    command = build_export_command(
        "python", tmp_path, tmp_path / "test.facemovie.json", project, tmp_path / "preview.mp4", width=1280, height=720,
    )
    assert command[command.index("--width") + 1] == "1280"
    assert command[command.index("--height") + 1] == "720"


def test_export_command_requests_safe_overwrite_only_when_confirmed(tmp_path: Path) -> None:
    project = StoryboardProject(analysis_path="analysis.json", person_name="Testperson")
    command = build_export_command(
        "python", tmp_path, tmp_path / "test.facemovie.json", project, tmp_path / "movie.mp4", overwrite=True,
    )
    assert "--overwrite" in command
