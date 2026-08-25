"""Persistentes, bewusst simples Storyboard-Projektformat."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_VERSION = 1


@dataclass
class StoryboardCard:
    source_path: str
    enabled: bool
    rotation_degrees: float = 0.0
    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    # Optional project-local replacement for the two MediaPipe iris centres.
    # The source photo and its analysis remain untouched.
    eye_override: list[list[float]] | None = None


@dataclass
class StoryboardProject:
    analysis_path: str
    cards: list[StoryboardCard] = field(default_factory=list)
    title: str = "Years in Focus"
    person_name: str = ""
    hold_seconds: float = 3.3
    transition_seconds: float = 0.8
    fps: float = 30.0
    output_width: int = 1920
    output_height: int = 1080
    # Existing projects retain the established card-stack movie. Timelapse
    # values are persisted already while its UI prototype is being evaluated.
    movie_mode: str = "years_in_focus"
    timelapse_frames_per_image: int = 3
    timelapse_transition_frames: int = 2
    timelapse_max_images_per_year: int = 3
    timelapse_frontal_only: bool = True
    # The normal workflow stays deliberately simple.  Advanced users can opt
    # into a modest FFmpeg post-encode to trade output size for image quality.
    output_quality: str = "standard"
    advanced_output_options: bool = False
    # Preview output keeps a separately chosen size tier, but always mirrors the
    # final movie's aspect ratio (landscape, portrait or square).
    preview_width: int = 1280
    preview_height: int = 720
    # Review-only captions are deliberately opt-in and are passed to the
    # renderer only for a preview export, never for the final movie.
    preview_show_image_number: bool = False
    preview_show_filename: bool = False
    eye_y: float = 0.38
    eye_distance: float = 0.033
    series_minimum_gap_minutes: float = 5.0
    desired_image_count: int = 0
    # Yellow cards remain opt-in: they can be useful for small collections or
    # lower-resolution films, but should not silently enter a standard movie.
    selection_quality_level: int = 0
    # Maximum horizontal head rotation admitted to automatic movie selection.
    # It is a project preference; the original analysis data remains unchanged.
    maximum_side_view_degrees: float = 25.0
    play_after_export: bool = False
    # Optional user-owned music file. It is referenced in the project, never copied.
    background_audio_path: str = ""
    # Ordered local playlist; the legacy singular field remains readable for
    # projects created before playlists and mirrors its first entry.
    background_audio_paths: list[str] = field(default_factory=list)
    # Optional full-frame stills. Unlike cards, they are not face-analysed or
    # aligned; each is shown for ``slide_seconds`` at the beginning/end.
    opening_slide_path: str = ""
    closing_slide_path: str = ""
    slide_seconds: float = 3.0
    border_enabled: bool = True
    border_pixels: int = 5
    border_color: str = "#ffffff"
    max_visible_cards: int = 0
    preview_enabled: bool = True
    # A view-only aid for chronological projects. It never changes card order or
    # which cards participate in a render.
    show_year_separators: bool = True
    # The region is the most useful trust signal in the large preview. New
    # projects therefore show it immediately; existing project files retain
    # their explicitly stored choice.
    preview_show_face_region: bool = True
    digikam_source: dict[str, object] | None = None

    @classmethod
    def from_analysis(cls, analysis_path: Path) -> StoryboardProject:
        records = json.loads(analysis_path.read_text(encoding="utf-8"))
        records = cls.sorted_records(records, "date")
        cards = [
            StoryboardCard(record["path"], record["status"] == "accepted")
            for record in records
            if record.get("path")
        ]
        return cls(
            analysis_path=str(analysis_path.resolve()), cards=cards,
            person_name=cls._person_from_records(records),
        )

    @staticmethod
    def sorted_records(records: list[dict], order: str) -> list[dict]:
        """Sort import candidates predictably; missing capture times go to the end."""
        if order == "name":
            return sorted(records, key=lambda record: Path(str(record.get("path", ""))).name.casefold())
        return sorted(
            records,
            key=lambda record: (
                not bool(record.get("capture_time")),
                str(record.get("capture_time") or ""),
                Path(str(record.get("path", ""))).name.casefold(),
            ),
        )

    @staticmethod
    def _person_from_records(records: list[dict]) -> str:
        for record in records:
            region = record.get("region") or {}
            if region.get("name"):
                return str(region["name"])
        return ""

    @classmethod
    def load(cls, path: Path) -> StoryboardProject:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("version") != PROJECT_VERSION:
            raise ValueError(f"Nicht unterstützte Projektversion: {raw.get('version')!r}")
        settings = raw["settings"]
        # Kept solely for projects saved while the short-lived experimental
        # "lively stack" option existed. Its effect is intentionally retired.
        settings.pop("rotation_jitter", None)
        if "selection_quality_level" not in settings:
            settings["selection_quality_level"] = 1 if settings.get("include_borderline_images") else 0
        settings.pop("include_borderline_images", None)
        project = cls(
            analysis_path=raw["analysis_path"],
            cards=[StoryboardCard(**card) for card in raw["cards"]],
            **settings,
        )
        if not isinstance(project.background_audio_paths, list):
            project.background_audio_paths = []
        project.background_audio_paths = [str(path) for path in project.background_audio_paths if path][:10]
        if not project.background_audio_paths and project.background_audio_path:
            project.background_audio_paths = [project.background_audio_path]
        if project.background_audio_paths:
            project.background_audio_path = project.background_audio_paths[0]
        if not project.person_name:
            analysis_path = Path(project.analysis_path)
            if analysis_path.is_file():
                records = json.loads(analysis_path.read_text(encoding="utf-8"))
                project.person_name = cls._person_from_records(records)
        return project

    def save(self, path: Path) -> None:
        settings = asdict(self)
        settings.pop("analysis_path")
        settings.pop("cards")
        payload = {
            "version": PROJECT_VERSION,
            "analysis_path": self.analysis_path,
            "cards": [asdict(card) for card in self.cards],
            "settings": settings,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
