"""Picasa-ähnlicher Stapel aus gerahmten, gesichtsnormalisierten Fotos."""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from facemovie.alignment import eye_geometry
from facemovie.models import Landmarks
from facemovie.rendering.video import VideoResult, frame_counts


@dataclass(frozen=True)
class StackVideoResult(VideoResult):
    max_visible_cards: int
    border_pixels: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _oriented_bgr(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        rgb = ImageOps.exif_transpose(image).convert("RGB")
    return cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)


def _border_bgr(color: str) -> tuple[int, int, int]:
    """Convert the project colour (#RRGGBB) to OpenCV's BGR convention."""
    value = color.lstrip("#")
    if len(value) != 6:
        return (255, 255, 255)
    try:
        red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return (255, 255, 255)
    return blue, green, red


def card_projected_size(
    image_size: tuple[int, int], landmarks: Landmarks, output_size: tuple[int, int],
    eye_distance_fraction: float, border_pixels: int, target_face_ratio: float | None = None,
    eye_size_balance: float = 1.0, source_face_height: float | None = None,
) -> tuple[float, float]:
    """Kartengröße bei festem Augenabstand, vor der leichten Drehung."""
    source_width, source_height = image_size
    scale = normalized_scale(
        landmarks, output_size[0], eye_distance_fraction, target_face_ratio,
        eye_size_balance, source_face_height,
    )
    return source_width * scale + 2 * border_pixels, source_height * scale + 2 * border_pixels


def median_face_ratio(
    landmarks_list: list[Landmarks], source_face_heights: list[float] | None = None
) -> float:
    heights = source_face_heights or [landmarks.face_box[3] for landmarks in landmarks_list]
    return statistics.median(
        height / eye_geometry(landmarks)[1]
        for landmarks, height in zip(landmarks_list, heights, strict=True)
    )


def normalized_scale(
    landmarks: Landmarks, output_width: int, eye_distance_fraction: float,
    target_face_ratio: float | None, eye_size_balance: float,
    source_face_height: float | None = None,
) -> float:
    """Kompromiss aus konstantem Augenabstand und konstanter Gesichtshöhe."""
    if not 0 <= eye_size_balance <= 1:
        raise ValueError("eye_size_balance muss zwischen 0 und 1 liegen.")
    _, source_distance, _ = eye_geometry(landmarks)
    eye_scale = (output_width * eye_distance_fraction) / source_distance
    if target_face_ratio is None:
        return eye_scale
    target_face_height = output_width * eye_distance_fraction * target_face_ratio
    face_scale = target_face_height / (source_face_height or landmarks.face_box[3])
    return eye_scale ** eye_size_balance * face_scale ** (1.0 - eye_size_balance)


def card_fits(
    image_size: tuple[int, int], landmarks: Landmarks, output_size: tuple[int, int],
    eye_distance_fraction: float, border_pixels: int, max_card_fraction: float,
    target_face_ratio: float | None = None, eye_size_balance: float = 1.0,
    source_face_height: float | None = None,
) -> tuple[bool, tuple[float, float]]:
    if not 0 < max_card_fraction <= 1:
        raise ValueError("max_card_fraction muss zwischen 0 und 1 liegen.")
    card_width, card_height = card_projected_size(
        image_size, landmarks, output_size, eye_distance_fraction, border_pixels,
        target_face_ratio, eye_size_balance, source_face_height,
    )
    maximum_width = output_size[0] * max_card_fraction
    maximum_height = output_size[1] * max_card_fraction
    return card_width <= maximum_width and card_height <= maximum_height, (card_width, card_height)


def source_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        oriented = ImageOps.exif_transpose(image)
        return oriented.size


def _card_layer(
    source_path: Path,
    landmarks: Landmarks,
    output_size: tuple[int, int],
    eye_y: float,
    eye_distance_fraction: float,
    border_pixels: int,
    border_color: str,
    target_face_ratio: float | None,
    eye_size_balance: float,
    source_face_height: float,
) -> tuple[np.ndarray, np.ndarray]:
    image = _oriented_bgr(source_path)
    source_height, source_width = image.shape[:2]
    midpoint, _, _ = eye_geometry(landmarks)
    output_width, output_height = output_size
    scale = normalized_scale(
        landmarks, output_width, eye_distance_fraction, target_face_ratio,
        eye_size_balance, source_face_height,
    )
    # Render 1080p cards at double resolution before reducing them.  This avoids
    # the staircase effect on the deliberately prominent, rotated white border.
    supersample = 2 if output_width * output_height <= 1920 * 1080 else 1
    border_source = max(0, round(border_pixels * supersample / scale))
    if border_source:
        card = cv2.copyMakeBorder(
            image, border_source, border_source, border_source, border_source,
            borderType=cv2.BORDER_CONSTANT, value=_border_bgr(border_color),
        )
    else:
        card = image
    card_midpoint = (midpoint[0] + border_source, midpoint[1] + border_source)
    # Rotate only as required by the detected eye axis.  OpenCV's positive
    # angle removes a positive slope because image y-coordinates point down.
    _, _, eye_angle = eye_geometry(landmarks)
    matrix = cv2.getRotationMatrix2D(card_midpoint, eye_angle, scale * supersample)
    transformed_midpoint = matrix[:, :2] @ np.asarray(card_midpoint) + matrix[:, 2]
    target = np.asarray((output_width * supersample / 2, output_height * supersample * eye_y))
    matrix[:, 2] += target - transformed_midpoint
    render_size = (output_width * supersample, output_height * supersample)
    color = cv2.warpAffine(
        card, matrix, render_size, flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0),
    )
    alpha_source = np.full(card.shape[:2], 255, dtype=np.uint8)
    alpha = cv2.warpAffine(
        alpha_source, matrix, render_size, flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )
    if supersample > 1:
        color = cv2.resize(color, output_size, interpolation=cv2.INTER_AREA)
        alpha = cv2.resize(alpha, output_size, interpolation=cv2.INTER_AREA)
    return color, alpha


def _compose(layers: list[tuple[np.ndarray, np.ndarray, float]], output_size: tuple[int, int]) -> np.ndarray:
    width, height = output_size
    result = np.zeros((height, width, 3), dtype=np.float32)
    for color, alpha, opacity in layers:
        weight = (alpha.astype(np.float32) / 255.0 * opacity)[..., None]
        result = color.astype(np.float32) * weight + result * (1.0 - weight)
    return np.clip(result, 0, 255).astype(np.uint8)


def _static_slide_frame(path: Path, output_size: tuple[int, int]) -> np.ndarray:
    """Fit a finished still into the movie without cropping or face processing."""
    image = _oriented_bgr(path)
    source_height, source_width = image.shape[:2]
    width, height = output_size
    scale = min(width / source_width, height / source_height)
    resized = cv2.resize(
        image,
        (max(1, round(source_width * scale)), max(1, round(source_height * scale))),
        interpolation=cv2.INTER_LANCZOS4 if scale > 1 else cv2.INTER_AREA,
    )
    result = np.zeros((height, width, 3), dtype=np.uint8)
    top = (height - resized.shape[0]) // 2
    left = (width - resized.shape[1]) // 2
    result[top:top + resized.shape[0], left:left + resized.shape[1]] = resized
    return result


def render_stack_mp4(
    entries: list[tuple[Path, Landmarks, float]],
    output_path: Path,
    output_size: tuple[int, int],
    fps: float,
    hold_seconds: float,
    transition_seconds: float,
    eye_y: float,
    eye_distance_fraction: float,
    border_pixels: int = 10,
    border_color: str = "#ffffff",
    max_visible_cards: int = 4,
    eye_size_balance: float = 0.0,
    opening_slide: Path | None = None,
    closing_slide: Path | None = None,
    slide_seconds: float = 3.0,
    progress: Callable[[str, int, int], None] | None = None,
) -> StackVideoResult:
    if not entries:
        raise ValueError("Kein akzeptiertes Bild für den Stapel-Videoexport vorhanden.")
    if output_path.exists():
        raise FileExistsError(f"Ausgabedatei existiert bereits: {output_path}")
    if max_visible_cards < 0:
        raise ValueError("max_visible_cards darf nicht negativ sein.")
    if slide_seconds < 0:
        raise ValueError("Die Folienstandzeit darf nicht negativ sein.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = output_size
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise OSError("OpenCV konnte keinen MP4-VideoWriter öffnen.")
    hold_frames, transition_frames = frame_counts(fps, hold_seconds, transition_seconds)
    slide_frames = max(1, round(fps * slide_seconds))
    opening_frame = _static_slide_frame(opening_slide, output_size) if opening_slide else None
    closing_frame = _static_slide_frame(closing_slide, output_size) if closing_slide else None
    target_face_ratio = median_face_ratio(
        [landmarks for _, landmarks, _ in entries],
        [face_height for _, _, face_height in entries],
    )
    cards = []
    for index, (path, landmarks, face_height) in enumerate(entries, start=1):
        if progress:
            progress("Karten vorbereiten", index - 1, len(entries))
        cards.append(_card_layer(
            path, landmarks, output_size, eye_y, eye_distance_fraction, border_pixels,
            border_color, target_face_ratio, eye_size_balance, face_height,
        ))
    if progress:
        progress("Karten vorbereiten", len(entries), len(entries))
    visible: list[tuple[np.ndarray, np.ndarray]] = []
    written = 0
    total_frames = len(cards) * (hold_frames + transition_frames)
    total_frames += slide_frames * int(opening_frame is not None)
    total_frames += slide_frames * int(closing_frame is not None)
    total_frames += transition_frames * int(closing_frame is not None)
    try:
        first_card_already_visible = False
        if opening_frame is not None:
            # The opening slide uses the configured dissolve duration, but the
            # fade is contained within its own hold time so the duration shown
            # in the UI stays accurate.  This avoids a distracting hard cut
            # from black before the first card transition starts.
            slide_fade_frames = min(transition_frames, slide_frames)
            black_frame = np.zeros_like(opening_frame)
            for frame_index in range(slide_frames):
                opacity = (
                    (frame_index + 1) / slide_fade_frames
                    if frame_index < slide_fade_frames and slide_fade_frames else 1.0
                )
                writer.write(cv2.addWeighted(black_frame, 1.0 - opacity, opening_frame, opacity, 0.0))
                written += 1
                if progress and (written % 10 == 0 or written == total_frames):
                    progress("Video schreiben", written, total_frames)
            # The first normal card transition used to fade in from black. With
            # an opening slide it instead fades from the slide into that card.
            first_static = _compose([(*cards[0], 1.0)], output_size)
            for step in range(1, transition_frames + 1):
                opacity = step / transition_frames if transition_frames else 1.0
                writer.write(cv2.addWeighted(opening_frame, 1.0 - opacity, first_static, opacity, 0.0))
                written += 1
                if progress and (written % 10 == 0 or written == total_frames):
                    progress("Video schreiben", written, total_frames)
            visible.append(cards[0])
            for _ in range(hold_frames):
                writer.write(first_static)
                written += 1
                if progress and (written % 10 == 0 or written == total_frames):
                    progress("Video schreiben", written, total_frames)
            first_card_already_visible = True
        for card in cards[1:] if first_card_already_visible else cards:
            base = _compose([(color, alpha, 1.0) for color, alpha in visible], output_size)
            for step in range(1, transition_frames + 1):
                opacity = step / transition_frames if transition_frames else 1.0
                writer.write(_compose([(base, np.full((height, width), 255, dtype=np.uint8), 1.0), (*card, opacity)], output_size))
                written += 1
                if progress and (written % 10 == 0 or written == total_frames):
                    progress("Video schreiben", written, total_frames)
            visible.append(card)
            if max_visible_cards:
                visible = visible[-max_visible_cards:]
            static = _compose([(color, alpha, 1.0) for color, alpha in visible], output_size)
            for _ in range(hold_frames):
                writer.write(static)
                written += 1
                if progress and (written % 10 == 0 or written == total_frames):
                    progress("Video schreiben", written, total_frames)
        if closing_frame is not None:
            # Preserve the current stack through the same soft transition that
            # is used between cards, rather than cutting abruptly to the slide.
            final_stack = _compose([(color, alpha, 1.0) for color, alpha in visible], output_size)
            for step in range(1, transition_frames + 1):
                opacity = step / transition_frames if transition_frames else 1.0
                writer.write(cv2.addWeighted(final_stack, 1.0 - opacity, closing_frame, opacity, 0.0))
                written += 1
                if progress and (written % 10 == 0 or written == total_frames):
                    progress("Video schreiben", written, total_frames)
            # Keep the complete closing-slide segment at the user-selected
            # duration: its final frames are the fade-out, not extra time.
            slide_fade_frames = min(transition_frames, slide_frames)
            for _ in range(slide_frames - slide_fade_frames):
                writer.write(closing_frame)
                written += 1
                if progress and (written % 10 == 0 or written == total_frames):
                    progress("Video schreiben", written, total_frames)
            # End on black rather than leaving the final slide frozen.  As at
            # the beginning, the fade fits inside the selected slide hold time.
            black_frame = np.zeros_like(closing_frame)
            for frame_index in range(slide_fade_frames):
                opacity = 1.0 - ((frame_index + 1) / slide_fade_frames)
                writer.write(cv2.addWeighted(black_frame, 1.0 - opacity, closing_frame, opacity, 0.0))
                written += 1
                if progress and (written % 10 == 0 or written == total_frames):
                    progress("Video schreiben", written, total_frames)
    finally:
        writer.release()
    return StackVideoResult(
        written, fps, hold_frames, transition_frames, len(entries), output_size,
        max_visible_cards, border_pixels,
    )
