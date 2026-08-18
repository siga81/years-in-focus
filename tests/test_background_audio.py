"""Audio command generation stays deterministic without requiring FFmpeg in tests."""

from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from facemovie.project import StoryboardProject
from facemovie.rendering.audio import (
    audio_duration_seconds,
    background_audio_command,
    format_audio_duration,
    playlist_audio_command,
)


class BackgroundAudioTests(unittest.TestCase):
    def test_loops_trims_and_fades_for_the_last_three_seconds(self) -> None:
        command = background_audio_command(
            Path("ffmpeg.exe"), Path("silent.mp4"), Path("music.mp3"), Path("result.mp4"), 12.5,
        )
        filter_value = command[command.index("-filter_complex") + 1]
        self.assertIn("atrim=duration=12.500000", filter_value)
        self.assertIn("afade=t=out:st=9.500000:d=3.000000", filter_value)
        self.assertIn("-stream_loop", command)
        self.assertEqual(command[command.index("-stream_loop") + 1], "-1")

    def test_short_video_fades_for_its_full_duration(self) -> None:
        command = background_audio_command(
            Path("ffmpeg.exe"), Path("silent.mp4"), Path("music.wav"), Path("result.mp4"), 1.2,
        )
        filter_value = command[command.index("-filter_complex") + 1]
        self.assertIn("afade=t=out:st=0.000000:d=1.200000", filter_value)

    def test_project_keeps_the_referenced_music_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "music.facemovie.json"
            project = StoryboardProject(analysis_path="analysis.json", background_audio_path="C:/Music/song.mp3")
            project.save(project_path)
            self.assertEqual(StoryboardProject.load(project_path).background_audio_path, "C:/Music/song.mp3")

    def test_legacy_single_music_entry_migrates_to_playlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "legacy.facemovie.json"
            StoryboardProject(analysis_path="analysis.json", background_audio_path="C:/Music/song.mp3").save(project_path)
            loaded = StoryboardProject.load(project_path)
            self.assertEqual(loaded.background_audio_paths, ["C:/Music/song.mp3"])

    def test_playlist_command_repeats_complete_order_and_normalizes_audio(self) -> None:
        command = playlist_audio_command(
            Path("ffmpeg.exe"), Path("silent.mp4"), [Path("one.mp3"), Path("two.wav")],
            Path("result.mp4"), 12.5, [3.0, 4.0],
        )
        filter_value = command[command.index("-filter_complex") + 1]
        self.assertIn("concat=n=4:v=0:a=1", filter_value)
        self.assertIn("aresample=48000", filter_value)

    def test_reads_wav_duration_without_external_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            music = Path(directory) / "short.wav"
            with wave.open(str(music), "wb") as source:
                source.setnchannels(1)
                source.setsampwidth(2)
                source.setframerate(8000)
                source.writeframes(b"\x00\x00" * 10000)
            self.assertAlmostEqual(audio_duration_seconds(music) or 0, 1.25)
            self.assertEqual(format_audio_duration(222.6), "03:43")


if __name__ == "__main__":
    unittest.main()
