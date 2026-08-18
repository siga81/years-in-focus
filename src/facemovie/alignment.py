"""Globale Similarity Transform für vollständige Fotos."""

from __future__ import annotations

import math

import cv2
import numpy as np

from facemovie.models import Landmarks


def eye_geometry(landmarks: Landmarks) -> tuple[tuple[float, float], float, float]:
    (lx, ly), (rx, ry) = landmarks.left_eye, landmarks.right_eye
    distance = math.hypot(rx - lx, ry - ly)
    if distance <= 0:
        raise ValueError("Augenabstand ist null")
    return ((lx + rx) / 2, (ly + ry) / 2), distance, math.degrees(math.atan2(ry - ly, rx - lx))


def similarity_matrix(
    landmarks: Landmarks,
    output_size: tuple[int, int],
    eye_y: float,
    eye_distance_fraction: float,
    rotation_strength: float = 0.0,
) -> np.ndarray:
    """Return a 2x3 matrix mapping the source image into output coordinates."""

    output_width, output_height = output_size
    midpoint, source_distance, angle = eye_geometry(landmarks)
    target = (output_width / 2, output_height * eye_y)
    scale = (output_width * eye_distance_fraction) / source_distance
    # OpenCV's positive angle removes a positive slope in image coordinates
    # (whose y-axis points down).  Using the negative angle doubles the tilt.
    matrix = cv2.getRotationMatrix2D(midpoint, angle * rotation_strength, scale)
    transformed_midpoint = matrix[:, :2] @ np.asarray(midpoint) + matrix[:, 2]
    matrix[:, 2] += np.asarray(target) - transformed_midpoint
    return matrix


def render_aligned(
    image_bgr: np.ndarray,
    matrix: np.ndarray,
    output_size: tuple[int, int],
) -> np.ndarray:
    return cv2.warpAffine(
        image_bgr,
        matrix,
        output_size,
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REFLECT_101,
    )


def render_full_image(
    image_bgr: np.ndarray, output_size: tuple[int, int], background: str = "black"
) -> np.ndarray:
    """Passt das gesamte Foto ohne Zoom oder Ausschnitt in das Videoformat ein."""
    output_width, output_height = output_size
    source_height, source_width = image_bgr.shape[:2]
    scale = min(output_width / source_width, output_height / source_height)
    rendered_width = max(1, round(source_width * scale))
    rendered_height = max(1, round(source_height * scale))
    resized = cv2.resize(image_bgr, (rendered_width, rendered_height), interpolation=cv2.INTER_CUBIC)
    value = 255 if background == "white" else 0
    canvas = np.full((output_height, output_width, 3), value, dtype=np.uint8)
    x = (output_width - rendered_width) // 2
    y = (output_height - rendered_height) // 2
    canvas[y:y + rendered_height, x:x + rendered_width] = resized
    return canvas


def face_anchored_scale(
    image_size: tuple[int, int], eye_midpoint: tuple[float, float], output_size: tuple[int, int], eye_y: float
) -> float:
    """Größter Maßstab, der das ganze Foto zeigt und den Augenanker erreicht."""
    source_width, source_height = image_size
    output_width, output_height = output_size
    eye_x, source_eye_y = eye_midpoint
    target_x, target_y = output_width / 2, output_height * eye_y
    limits = [output_width / source_width, output_height / source_height]
    if eye_x > 0:
        limits.append(target_x / eye_x)
    if eye_x < source_width:
        limits.append((output_width - target_x) / (source_width - eye_x))
    if source_eye_y > 0:
        limits.append(target_y / source_eye_y)
    if source_eye_y < source_height:
        limits.append((output_height - target_y) / (source_height - source_eye_y))
    return max(0.001, min(limits))


def render_face_anchored_full_image(
    image_bgr: np.ndarray,
    eye_midpoint: tuple[float, float],
    output_size: tuple[int, int],
    eye_y: float,
    background: str = "black",
) -> tuple[np.ndarray, float]:
    """Zeigt das vollständige Foto und positioniert die Augen am gemeinsamen Zielanker."""
    output_width, output_height = output_size
    source_height, source_width = image_bgr.shape[:2]
    scale = face_anchored_scale((source_width, source_height), eye_midpoint, output_size, eye_y)
    rendered_width = max(1, round(source_width * scale))
    rendered_height = max(1, round(source_height * scale))
    resized = cv2.resize(image_bgr, (rendered_width, rendered_height), interpolation=cv2.INTER_CUBIC)
    value = 255 if background == "white" else 0
    canvas = np.full((output_height, output_width, 3), value, dtype=np.uint8)
    target_x, target_y = output_width / 2, output_height * eye_y
    x = min(max(0, round(target_x - eye_midpoint[0] * scale)), output_width - rendered_width)
    y = min(max(0, round(target_y - eye_midpoint[1] * scale)), output_height - rendered_height)
    canvas[y:y + rendered_height, x:x + rendered_width] = resized
    return canvas, scale


def render_face_normalized_image(
    image_bgr: np.ndarray,
    landmarks: Landmarks,
    output_size: tuple[int, int],
    eye_y: float,
    eye_distance_fraction: float,
    rotation_strength: float = 0.0,
) -> tuple[np.ndarray, float]:
    """Normalisiert Gesichtslage und -größe, ohne den Bildkontext verschwinden zu lassen."""
    background = render_full_image(image_bgr, output_size, "black")
    background = cv2.addWeighted(background, 0.42, np.zeros_like(background), 0.58, 0.0)
    matrix = similarity_matrix(
        landmarks, output_size, eye_y, eye_distance_fraction, rotation_strength
    )
    foreground = cv2.warpAffine(
        image_bgr, matrix, output_size, flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0),
    )
    source_mask = np.full(image_bgr.shape[:2], 255, dtype=np.uint8)
    mask = cv2.warpAffine(
        source_mask, matrix, output_size, flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )
    result = background.copy()
    result[mask > 0] = foreground[mask > 0]
    return result, float(matrix[0, 0])
