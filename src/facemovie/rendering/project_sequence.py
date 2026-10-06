"""Shared project geometry and selection for MP4 export and interactive preview."""
from pathlib import Path
from facemovie.metadata.xmp import find_region
from facemovie.models import Landmarks
from facemovie.rendering.stack import _oriented_bgr
from facemovie.vision.mediapipe_landmarker import MediaPipeFaceLandmarker

def _region_from_data(data: dict | None):
    if not data:
        return None
    try:
        from facemovie.models import FaceRegion
        return FaceRegion(
            str(data["name"]), float(data["x"]), float(data["y"]),
            float(data["width"]), float(data["height"]),
            str(data["coordinate_system"]), str(data["source"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _landmarks_from_record(record: dict) -> Landmarks | None:
    data = record.get("landmarks")
    if not data:
        return None
    return Landmarks(
        tuple(data["left_eye"]), tuple(data["right_eye"]), tuple(data["nose"]),
        tuple(data["left_mouth"]), tuple(data["right_mouth"]), data["score"], tuple(data["face_box"]),
    )


def _face_reference_height(record: dict, landmarks: Landmarks) -> float:
    region = record.get("region")
    source_size_value = record.get("source_size")
    if region and source_size_value and region.get("height"):
        return float(region["height"]) * float(source_size_value[1])
    return float(landmarks.face_box[3])


def _landmarks_with_eye_override(
    landmarks: Landmarks, override: list[list[float]] | None,
) -> Landmarks:
    """Apply a validated project-only iris correction to otherwise automatic geometry."""
    if not isinstance(override, list) or len(override) != 2:
        return landmarks
    try:
        left_eye = tuple(float(value) for value in override[0])
        right_eye = tuple(float(value) for value in override[1])
    except (TypeError, ValueError):
        return landmarks
    if len(left_eye) != 2 or len(right_eye) != 2:
        return landmarks
    return Landmarks(
        left_eye=left_eye, right_eye=right_eye, nose=landmarks.nose,
        left_mouth=landmarks.left_mouth, right_mouth=landmarks.right_mouth,
        score=landmarks.score, face_box=landmarks.face_box,
    )


def prepare_project_sequence(project, by_path, model_path=None, person="", eye_anchor="iris",
                             progress=lambda *_: None, cancelled=lambda: False):
    stack_entries: list[tuple[Path, Landmarks, float]] = []
    skipped: list[dict[str, str]] = []
    dense_detector = None
    if model_path:
        if not person:
            raise ValueError("--person ist zusammen mit --mediapipe-model erforderlich.")
    enabled_cards = [card for card in project.cards if card.enabled]
    unavailable_sources = [
        Path(card.source_path)
        for card in enabled_cards
        if not Path(card.source_path).is_file()
    ]
    if unavailable_sources:
        filenames = ", ".join(path.name for path in unavailable_sources[:5])
        remaining = len(unavailable_sources) - 5
        suffix = f" (+{remaining} more)" if remaining > 0 else ""
        raise FileNotFoundError(
            "Original image(s) selected for this movie are unavailable: "
            f"{filenames}{suffix}"
        )
    progress("Gesichtsgeometrie", 0, max(1, len(enabled_cards)))
    try:
        if cancelled():
            raise InterruptedError("Preparation cancelled")
        if model_path:
            dense_detector = MediaPipeFaceLandmarker(model_path.resolve())
        for index, card in enumerate(enabled_cards, start=1):
            progress("Gesichtsgeometrie", index - 1, len(enabled_cards))
            if cancelled():
                raise InterruptedError("Preparation cancelled")
            source_path = Path(card.source_path).resolve()
            record = by_path.get(str(source_path))
            if dense_detector:
                region = _region_from_data(record.get("region") if record else None) or find_region(source_path, person)
                dense = dense_detector.detect(_oriented_bgr(source_path), region) if region else None
                landmarks = dense.as_sparse_landmarks(eye_anchor) if dense else None
                if landmarks is not None:
                    landmarks = _landmarks_with_eye_override(landmarks, card.eye_override)
                missing_reason = "MediaPipe fand in der markierten Personenregion keine Geometrie."
            else:
                landmarks = _landmarks_from_record(record) if record else None
                if landmarks is not None:
                    landmarks = _landmarks_with_eye_override(landmarks, card.eye_override)
                missing_reason = "Keine verwendbaren Gesichtsmarkierungen im Analyseergebnis."
            if not record or not landmarks:
                skipped.append({"filename": source_path.name, "reason": missing_reason})
                continue
            face_height = landmarks.face_box[3] if dense_detector else _face_reference_height(record, landmarks)
            stack_entries.append((source_path, landmarks, face_height))
    finally:
        if dense_detector:
            dense_detector.close()
    progress("Gesichtsgeometrie", len(enabled_cards), max(1, len(enabled_cards)))
    if project.movie_mode == "timelapse":
        by_year: dict[str, list[tuple[Path, Landmarks, float]]] = {}
        for entry in stack_entries:
            record = by_path.get(str(entry[0].resolve()), {})
            metrics = record.get("metrics") or {}
            face_height = float(metrics.get("face_height_px", 0.0))
            score = float(metrics.get("yunet_score", 0.0))
            try:
                yaw = abs(float(metrics["pose_yaw_degrees"]))
            except (KeyError, TypeError, ValueError):
                yaw = None
            required_height = project.output_height * 0.22
            quality_level = 0
            if face_height <= 0 or score <= 0 or face_height < required_height * 0.65 or score < 0.42:
                quality_level = 2
            elif face_height < required_height or score < 0.65 or yaw is None or yaw > project.maximum_side_view_degrees:
                quality_level = 1
            if quality_level > project.selection_quality_level:
                continue
            if project.timelapse_frontal_only and (yaw is None or yaw > 12.0):
                continue
            year = str(record.get("capture_time") or "unbekannt")[:4]
            by_year.setdefault(year, []).append(entry)
        stack_entries = []
        limit = max(0, project.timelapse_max_images_per_year)
        for entries_for_year in by_year.values():
            if limit == 0 or len(entries_for_year) <= limit:
                stack_entries.extend(entries_for_year)
                continue
            positions = [round(index * (len(entries_for_year) - 1) / (limit - 1)) for index in range(limit)] if limit > 1 else [len(entries_for_year) // 2]
            stack_entries.extend(entries_for_year[index] for index in positions)
        if not stack_entries:
            raise ValueError("Kein technisch geeignetes, frontales Bild für den Zeitraffer vorhanden.")
    if not stack_entries:
        raise ValueError("Keine verwendbare Kartengeometrie vorhanden.")
    return stack_entries, skipped
