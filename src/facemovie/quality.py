"""Transparente Qualitätsbewertung für Phase 1."""

from __future__ import annotations

from facemovie.models import Landmarks


def minimum_face_height(output_height: int) -> float:
    # 480p≈106, 1080p≈238, 2160p≈475 pixel; passt zur vereinbarten Größenordnung.
    return output_height * 0.22


def assess(
    image_size: tuple[int, int], landmarks: Landmarks | None, output_height: int,
    pose: dict[str, float] | None = None,
) -> tuple[list[str], dict[str, float]]:
    if landmarks is None:
        return ["Die Augenposition für die automatische Ausrichtung konnte nicht sicher bestimmt werden."], {}

    image_width, image_height = image_size
    _, _, face_width, face_height = landmarks.face_box
    metrics = {
        "yunet_score": landmarks.score,
        "face_width_px": face_width,
        "face_height_px": face_height,
        "face_height_ratio": face_height / image_height,
        "required_face_height_px": minimum_face_height(output_height),
    }
    if pose:
        metrics.update(pose)
    warnings: list[str] = []
    if face_height < minimum_face_height(output_height):
        warnings.append(
            f"Gesicht zu klein für die Zielhöhe: {face_height:.0f}px < "
            f"{minimum_face_height(output_height):.0f}px."
        )
    if landmarks.score < 0.65:
        warnings.append(
            f"Augenposition für die automatische Ausrichtung unsicher (Erkennungswert: {landmarks.score * 100:.0f} %)."
        )
    if not (0 <= landmarks.left_eye[0] < image_width and 0 <= landmarks.right_eye[0] < image_width):
        warnings.append("Erkannte Augen liegen außerhalb des Bildbereichs.")
    yaw = abs(float(metrics.get("pose_yaw_degrees", 0.0)))
    if yaw >= 25.0:
        warnings.append(
            f"Starke Seitenansicht ({yaw:.0f}°); der Übergang zu frontalen Bildern kann unruhig wirken."
        )
    elif yaw >= 15.0:
        warnings.append(
            f"Leichte Seitenansicht ({yaw:.0f}°); bei der automatischen Auswahl wird eine frontalere Aufnahme bevorzugt."
        )
    return warnings, metrics
