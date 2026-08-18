"""Serialisierbare Datenobjekte für die Phase-1-Analyse."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FaceRegion:
    name: str
    x: float
    y: float
    width: float
    height: float
    coordinate_system: str
    source: str


@dataclass(frozen=True)
class Landmarks:
    left_eye: tuple[float, float]
    right_eye: tuple[float, float]
    nose: tuple[float, float]
    left_mouth: tuple[float, float]
    right_mouth: tuple[float, float]
    score: float
    face_box: tuple[float, float, float, float]


@dataclass
class ImageAnalysis:
    path: str
    source_size: tuple[int, int]
    capture_time: str | None = None
    region: FaceRegion | None = None
    landmarks: Landmarks | None = None
    status: str = "rejected"
    manual_decision: str | None = None
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    output_path: str | None = None

    @property
    def filename(self) -> str:
        return Path(self.path).name

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
