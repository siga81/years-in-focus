"""Lokaler MP4-Export aus bereits global ausgerichteten Einzelbildern."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class VideoResult:
    frame_count: int
    fps: float
    hold_frames: int
    transition_frames: int
    image_count: int
    size: tuple[int, int]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def frame_counts(fps: float, hold_seconds: float, transition_seconds: float) -> tuple[int, int]:
    if fps <= 0 or hold_seconds < 0 or transition_seconds < 0:
        raise ValueError("FPS sowie Stand- und Übergangszeit müssen nichtnegativ sein.")
    return max(1, round(fps * hold_seconds)), round(fps * transition_seconds)


def _read_bgr(path: Path) -> np.ndarray:
    # cv2.imread ist unter Windows bei Umlauten nicht zuverlässig.
    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise OSError(f"Bild kann nicht gelesen werden: {path}")
    return image


def render_mp4(
    image_paths: list[Path], output_path: Path, fps: float, hold_seconds: float, transition_seconds: float
) -> VideoResult:
    if not image_paths:
        raise ValueError("Kein akzeptiertes Bild für den Videoexport vorhanden.")
    if output_path.exists():
        raise FileExistsError(f"Ausgabedatei existiert bereits: {output_path}")

    frames = [_read_bgr(path) for path in image_paths]
    height, width = frames[0].shape[:2]
    if any(frame.shape[:2] != (height, width) for frame in frames):
        raise ValueError("Alle Eingabebilder müssen dieselbe Ausgabegröße besitzen.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    if not writer.isOpened():
        raise OSError("OpenCV konnte keinen MP4-VideoWriter öffnen.")

    hold_frames, transition_frames = frame_counts(fps, hold_seconds, transition_seconds)
    written = 0
    try:
        for index, current in enumerate(frames):
            for _ in range(hold_frames):
                writer.write(current)
                written += 1
            if index == len(frames) - 1:
                continue
            following = frames[index + 1]
            for step in range(1, transition_frames + 1):
                alpha = step / (transition_frames + 1)
                writer.write(cv2.addWeighted(current, 1.0 - alpha, following, alpha, 0.0))
                written += 1
    finally:
        writer.release()

    return VideoResult(written, fps, hold_frames, transition_frames, len(frames), (width, height))
