"""Small FFmpeg bridge for attaching user-selected background music."""

from __future__ import annotations

import math
import shutil
import subprocess
import wave
from pathlib import Path

from facemovie.runtime import application_root


def find_ffmpeg(asset_root: Path | None = None) -> Path | None:
    """Prefer YiF's bundled tool, then allow a developer's PATH installation."""
    if asset_root is not None:
        bundled = asset_root / "ffmpeg.exe"
        if bundled.is_file():
            return bundled
    beside_application = application_root() / "ffmpeg.exe"
    if beside_application.is_file():
        return beside_application
    discovered = shutil.which("ffmpeg")
    return Path(discovered) if discovered else None


def find_ffprobe(asset_root: Path | None = None) -> Path | None:
    """Locate ffprobe beside a bundled/developer FFmpeg when it is available."""
    if asset_root is not None:
        bundled = asset_root / "ffprobe.exe"
        if bundled.is_file():
            return bundled
    beside_application = application_root() / "ffprobe.exe"
    if beside_application.is_file():
        return beside_application
    ffmpeg = find_ffmpeg(asset_root)
    if ffmpeg is not None:
        sibling = ffmpeg.with_name("ffprobe.exe")
        if sibling.is_file():
            return sibling
    discovered = shutil.which("ffprobe")
    return Path(discovered) if discovered else None


def audio_duration_seconds(audio: Path, asset_root: Path | None = None) -> float | None:
    """Read an audio duration locally; WAV works without FFmpeg, other files use ffprobe."""
    if not audio.is_file():
        return None
    if audio.suffix.casefold() == ".wav":
        try:
            with wave.open(str(audio), "rb") as source:
                rate = source.getframerate()
                return source.getnframes() / rate if rate else None
        except (OSError, wave.Error):
            return None
    ffprobe = find_ffprobe(asset_root)
    if ffprobe is None:
        return None
    try:
        result = subprocess.run(
            [
                str(ffprobe), "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nokey=1:noprint_wrappers=1", str(audio),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=8,
        )
        duration = float(result.stdout.strip())
        return duration if result.returncode == 0 and math.isfinite(duration) and duration >= 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def format_audio_duration(seconds: float) -> str:
    """Return a stable compact duration such as 03:42 or 1:03:42."""
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, seconds_value = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds_value:02d}"
    return f"{minutes:02d}:{seconds_value:02d}"


def background_audio_command(
    ffmpeg: Path, silent_video: Path, music: Path, output: Path, duration_seconds: float,
) -> list[str]:
    """Build a deterministic loop, trim and fade command for a finished silent MP4."""
    if duration_seconds <= 0:
        raise ValueError("Video duration must be positive before adding audio.")
    fade_duration = min(3.0, duration_seconds)
    fade_start = max(0.0, duration_seconds - fade_duration)
    audio_filter = (
        f"atrim=duration={duration_seconds:.6f},"
        f"afade=t=out:st={fade_start:.6f}:d={fade_duration:.6f},"
        "aresample=async=1[audio]"
    )
    return [
        str(ffmpeg), "-y", "-stream_loop", "-1", "-i", str(music), "-i", str(silent_video),
        "-filter_complex", audio_filter,
        "-map", "1:v:0", "-map", "[audio]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest", str(output),
    ]


def playlist_audio_command(
    ffmpeg: Path, silent_video: Path, tracks: list[Path], output: Path,
    duration_seconds: float, track_durations: list[float],
) -> list[str]:
    """Concatenate and loop a small playlist before trimming it to the movie."""
    if not tracks or len(tracks) != len(track_durations) or any(value <= 0 for value in track_durations):
        raise ValueError("A playable background-music playlist is required.")
    repetitions = max(1, math.ceil(duration_seconds / sum(track_durations)))
    repeated = tracks * repetitions
    inputs: list[str] = []
    for track in repeated:
        inputs.extend(["-i", str(track)])
    fade_duration = min(3.0, duration_seconds)
    fade_start = max(0.0, duration_seconds - fade_duration)
    normalized = "".join(
        f"[{index}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[a{index}];"
        for index in range(len(repeated))
    )
    sources = "".join(f"[a{index}]" for index in range(len(repeated)))
    filter_graph = (
        f"{normalized}{sources}concat=n={len(repeated)}:v=0:a=1,"
        f"atrim=duration={duration_seconds:.6f},"
        f"afade=t=out:st={fade_start:.6f}:d={fade_duration:.6f},"
        "aresample=async=1[audio]"
    )
    return [
        str(ffmpeg), "-y", *inputs, "-i", str(silent_video),
        "-filter_complex", filter_graph, "-map", f"{len(repeated)}:v:0", "-map", "[audio]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(output),
    ]


def mux_background_audio(
    silent_video: Path, music: Path | list[Path], output: Path, duration_seconds: float, asset_root: Path | None = None,
) -> None:
    """Attach one track or looped ordered tracks and fade out only at film end."""
    tracks = [music] if isinstance(music, Path) else music
    if not tracks or any(not track.is_file() for track in tracks):
        missing = next((track for track in tracks if not track.is_file()), None)
        raise FileNotFoundError(f"Background music file is unavailable: {missing}")
    ffmpeg = find_ffmpeg(asset_root)
    if ffmpeg is None:
        raise FileNotFoundError(
            "FFmpeg was not found. Background music needs the FFmpeg component shipped with Years in Focus."
        )
    durations = [audio_duration_seconds(track, asset_root) for track in tracks]
    if any(value is None for value in durations):
        raise ValueError("The duration of one background music track could not be read.")
    command = (
        background_audio_command(ffmpeg, silent_video, tracks[0], output, duration_seconds)
        if len(tracks) == 1
        else playlist_audio_command(ffmpeg, silent_video, tracks, output, duration_seconds, [float(value) for value in durations])
    )
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode:
        details = completed.stdout.strip() or "FFmpeg returned an unknown error."
        raise RuntimeError(f"Background music could not be added:\n{details}")


def transcode_video_quality(
    source: Path, output: Path, quality: str, asset_root: Path | None = None,
) -> None:
    """Apply the two deliberately modest expert output profiles.

    YiF's standard export remains the fast OpenCV MP4 output.  These profiles
    only use FFmpeg's built-in MPEG-4 encoder, so they do not quietly introduce
    a GPL-only encoder dependency such as libx264.
    """
    quantizer = {"high": "2", "smaller": "7"}.get(quality)
    if quantizer is None:
        raise ValueError(f"Unknown video quality profile: {quality}")
    ffmpeg = find_ffmpeg(asset_root)
    if ffmpeg is None:
        raise FileNotFoundError(
            "FFmpeg was not found. Advanced video-quality profiles need the FFmpeg component shipped with Years in Focus."
        )
    completed = subprocess.run(
        [
            str(ffmpeg), "-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "mpeg4", "-q:v", quantizer, "-c:a", "copy", "-movflags", "+faststart", str(output),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode:
        details = completed.stdout.strip() or "FFmpeg returned an unknown error."
        raise RuntimeError(f"Video-quality profile could not be applied:\n{details}")
