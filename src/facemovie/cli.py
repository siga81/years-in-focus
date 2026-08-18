"""Kommandozeile für Years in Focus."""

from __future__ import annotations

import argparse
import json
import logging
import uuid
from pathlib import Path

import cv2
from PIL import Image, ImageOps

from facemovie.alignment import (
    eye_geometry,
    render_aligned,
    render_face_anchored_full_image,
    render_face_normalized_image,
    render_full_image,
    similarity_matrix,
)
from facemovie.importing import paths_from_input_list
from facemovie.metadata.xmp import find_region
from facemovie.models import ImageAnalysis, Landmarks
from facemovie.project import StoryboardProject
from facemovie.quality import assess
from facemovie.rendering.audio import mux_background_audio, transcode_video_quality
from facemovie.rendering.contact_sheet import write_contact_sheet
from facemovie.rendering.stack import card_fits, median_face_ratio, render_stack_mp4, source_size
from facemovie.rendering.video import render_mp4
from facemovie.runtime import bundled_asset_root
from facemovie.selection import capture_time, reduce_series
from facemovie.storyboard import launch as launch_storyboard
from facemovie.vision.mediapipe_landmarker import MediaPipeFaceLandmarker
from facemovie.vision.yunet import YuNetLandmarker


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


def _regions_from_manifest(path: Path | None) -> dict[str, object]:
    """Load database-sourced regions keyed by normalized source path."""
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_regions = payload.get("regions", {})
    if not isinstance(raw_regions, dict):
        raise ValueError("Die Regionsdatei enthält keine gültige Zuordnung.")
    return {
        str(Path(source).resolve()): region
        for source, region in raw_regions.items()
        if isinstance(region, dict)
    }


def _oriented_bgr(path: Path):
    with Image.open(path) as image:
        rgb = ImageOps.exif_transpose(image).convert("RGB")
        return cv2.cvtColor(__import__("numpy").asarray(rgb), cv2.COLOR_RGB2BGR)


def _image_paths(directory: Path) -> list[Path]:
    suffixes = {".jpg", ".jpeg"}
    return sorted(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in suffixes)


def _write_jpeg(path: Path, image_bgr) -> None:
    """Write JPEG bytes through pathlib so Windows Unicode paths stay intact."""
    ok, encoded = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise OSError(f"JPEG-Kodierung fehlgeschlagen: {path}")
    path.write_bytes(encoded.tobytes())


def _progress(args: argparse.Namespace, phase: str, current: int, total: int) -> None:
    if getattr(args, "progress", False):
        print(f"FM_PROGRESS\t{phase}\t{current}\t{total}", flush=True)


def align(args: argparse.Namespace) -> int:
    if args.series_keep < 1:
        raise ValueError("--series-keep muss mindestens 1 sein.")
    if args.input_files:
        input_paths = [path.resolve() for path in args.input_files]
    elif args.input_list:
        input_paths = paths_from_input_list(args.input_list)
    else:
        input_paths = _image_paths(args.input.resolve())
    output_dir = args.output.resolve()
    accepted_dir = output_dir / "aligned"
    rejected_dir = output_dir / "rejected"
    output_dir.mkdir(parents=True, exist_ok=True)
    if not args.reference_originals:
        accepted_dir.mkdir(parents=True, exist_ok=True)
        rejected_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=output_dir / "run.log", level=logging.INFO, encoding="utf-8")
    landmarker = YuNetLandmarker(args.yunet_model, args.yunet_score_threshold)
    dense_landmarker = MediaPipeFaceLandmarker(args.mediapipe_model) if args.mediapipe_model else None
    excluded_files = set(args.exclude)
    review_files = set(args.review)
    accepted_files = set(args.accept)
    imported_regions = _regions_from_manifest(args.regions_json)
    items: list[ImageAnalysis] = []

    for index, path in enumerate(input_paths, start=1):
        _progress(args, "Analyse", index - 1, len(input_paths))
        try:
            image = _oriented_bgr(path)
            height, width = image.shape[:2]
            timestamp = capture_time(path)
            item = ImageAnalysis(
                path=str(path), source_size=(width, height),
                capture_time=timestamp.isoformat() if timestamp else None,
            )
            if path.name in excluded_files:
                if args.reference_originals:
                    target = path
                else:
                    target = rejected_dir / path.name
                    target.write_bytes(path.read_bytes())
                item.status = "excluded"
                item.manual_decision = "exclude"
                item.warnings.append("Manuell vom Rendern ausgeschlossen.")
                item.output_path = str(target)
                items.append(item)
                logging.info("%s: excluded", path.name)
                continue
            item.region = _region_from_data(imported_regions.get(str(path))) or find_region(path, args.person)
            if item.region is None:
                item.warnings.append(f"Keine Gesichtsregion für {args.person!r} gefunden.")
            else:
                item.landmarks = landmarker.detect(image, item.region)
                dense = dense_landmarker.detect(image, item.region) if dense_landmarker else None
                warnings, metrics = assess(
                    (width, height), item.landmarks, args.height,
                    dense.head_pose_degrees() if dense else None,
                )
                item.warnings.extend(warnings)
                item.metrics.update(metrics)
                if item.landmarks is not None:
                    midpoint, distance, angle = eye_geometry(item.landmarks)
                    item.metrics.update({
                        "eye_midpoint_x": midpoint[0], "eye_midpoint_y": midpoint[1],
                        "eye_distance_px": distance, "eye_angle_degrees": angle,
                    })
                    if args.reference_originals:
                        item.output_path = str(path)
                    else:
                        if args.framing == "face-normalized":
                            aligned, framing_scale = render_face_normalized_image(
                                image, item.landmarks, (args.width, args.height), args.eye_y,
                                args.eye_distance, args.rotation_strength,
                            )
                            item.metrics["framing_scale"] = framing_scale
                        elif args.framing == "face-anchored-full":
                            midpoint, _, _ = eye_geometry(item.landmarks)
                            aligned, framing_scale = render_face_anchored_full_image(
                                image, midpoint, (args.width, args.height), args.eye_y, args.background
                            )
                            item.metrics["framing_scale"] = framing_scale
                        elif args.framing == "full":
                            aligned = render_full_image(image, (args.width, args.height), args.background)
                        else:
                            matrix = similarity_matrix(
                                item.landmarks, (args.width, args.height), args.eye_y,
                                args.eye_distance, args.rotation_strength,
                            )
                            aligned = render_aligned(image, matrix, (args.width, args.height))
                        target = accepted_dir / f"{path.stem}.jpg"
                        _write_jpeg(target, aligned)
                        item.output_path = str(target)
                    item.status = "accepted" if not item.warnings else "review"
                    if path.name in review_files:
                        item.warnings.append("Manuell als Review-Fall markiert.")
                        item.status = "review"
                        item.manual_decision = "review"
                    if path.name in accepted_files:
                        item.warnings.append("Manuell trotz technischer Warnung akzeptiert.")
                        item.status = "accepted"
                        item.manual_decision = "accept"
            if item.output_path is None:
                if args.reference_originals:
                    target = path
                else:
                    target = rejected_dir / path.name
                    target.write_bytes(path.read_bytes())
                item.output_path = str(target)
            logging.info("%s: %s %s", path.name, item.status, "; ".join(item.warnings))
        except Exception as exc:  # Per-image fault isolation is intentional.
            item = ImageAnalysis(path=str(path), source_size=(0, 0), warnings=[f"Fehler: {type(exc).__name__}: {exc}"])
            if args.reference_originals:
                target = path
            else:
                target = rejected_dir / path.name
                target.write_bytes(path.read_bytes())
            item.output_path = str(target)
            logging.exception("Fehler bei %s", path)
        items.append(item)

    if dense_landmarker:
        dense_landmarker.close()
    _progress(args, "Analyse", len(input_paths), len(input_paths))

    # The final image has been read at this point, but reducing burst shots and
    # creating the contact sheet can still take noticeable time on large imports.
    # Report these as their own phases instead of leaving the UI at N of N.
    _progress(args, "Reihenaufnahmen prüfen", 0, 1)
    reduce_series(items, args.series_minutes, args.series_keep)
    _progress(args, "Reihenaufnahmen prüfen", 1, 1)
    _progress(args, "Projektdaten schreiben", 0, 1)
    (output_dir / "analysis.json").write_text(
        json.dumps([item.as_dict() for item in items], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _progress(args, "Projektdaten schreiben", 1, 1)
    # The contact sheet is intentionally capped.  Its purpose is a quick
    # overview; rendering every image can create a multi-hundred-megapixel
    # JPEG and delay or even prevent very large imports from finishing.
    write_contact_sheet(
        items,
        output_dir / "contact_sheet.jpg",
        progress=lambda current, total: _progress(args, "Kontaktbogen erstellen", current, total),
    )
    accepted = sum(item.status == "accepted" for item in items)
    review = sum(item.status == "review" for item in items)
    deferred = sum(item.status == "deferred" for item in items)
    print(
        f"Analysiert: {len(items)}; akzeptiert: {accepted}; Review: {review}; "
        f"Serienrückstellung: {deferred}; abgelehnt: {len(items) - accepted - review - deferred}"
    )
    return 0


def render_video(args: argparse.Namespace) -> int:
    analysis_path = args.analysis.resolve()
    records = json.loads(analysis_path.read_text(encoding="utf-8"))
    eligible = [record for record in records if record["status"] == "accepted" and record["output_path"]]
    eligible.sort(key=lambda record: (record.get("capture_time") is None, record.get("capture_time") or "", record["path"]))
    result = render_mp4(
        [Path(record["output_path"]) for record in eligible],
        args.output.resolve(), args.fps, args.hold_seconds, args.transition_seconds,
    )
    manifest = {
        "settings": {
            "hold_seconds": args.hold_seconds,
            "transition_seconds": args.transition_seconds,
            "fps": args.fps,
            "codec": "mp4v",
        },
        "source_analysis": str(analysis_path),
        "images": [Path(record["path"]).name for record in eligible],
        "result": result.as_dict(),
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Video geschrieben: {args.output}; Bilder: {result.image_count}; Frames: {result.frame_count}")
    return 0


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


def render_stack_video(args: argparse.Namespace) -> int:
    analysis_path = args.analysis.resolve()
    records = json.loads(analysis_path.read_text(encoding="utf-8"))
    eligible = [record for record in records if record["status"] == "accepted" and _landmarks_from_record(record)]
    eligible.sort(key=lambda record: (record.get("capture_time") is None, record.get("capture_time") or "", record["path"]))
    eligible_landmarks = [_landmarks_from_record(record) for record in eligible]
    eligible_face_heights = [
        _face_reference_height(record, landmarks)
        for record, landmarks in zip(eligible, eligible_landmarks, strict=True)
    ]
    face_ratio = median_face_ratio(eligible_landmarks, eligible_face_heights)
    stack_entries: list[tuple[Path, Landmarks, float]] = []
    skipped: list[dict[str, object]] = []
    for record in eligible:
        path = Path(record["path"])
        landmarks = _landmarks_from_record(record)
        face_height = _face_reference_height(record, landmarks)
        if args.max_card_fraction <= 0:
            stack_entries.append((path, landmarks, face_height))
        else:
            fits, projected_size = card_fits(
                source_size(path), landmarks, (args.width, args.height), args.eye_distance,
                args.border_pixels, args.max_card_fraction, face_ratio,
                args.eye_size_balance, face_height,
            )
            if fits:
                stack_entries.append((path, landmarks, face_height))
            else:
                skipped.append({
                    "filename": path.name,
                    "reason": "Karte wäre bei fester Gesichtsgröße zu groß.",
                    "projected_size": [round(projected_size[0]), round(projected_size[1])],
                })
    result = render_stack_mp4(
        stack_entries,
        args.output.resolve(), (args.width, args.height), args.fps, args.hold_seconds,
        args.transition_seconds, args.eye_y, args.eye_distance, args.border_pixels,
        "#ffffff", args.max_visible_cards, args.eye_size_balance,
    )
    manifest = {
        "settings": vars(args), "source_analysis": str(analysis_path),
        "images": [path.name for path, _, _ in stack_entries], "skipped": skipped,
        "result": result.as_dict(),
    }
    manifest["settings"] = {key: str(value) if isinstance(value, Path) else value for key, value in manifest["settings"].items() if key != "func"}
    args.output.with_suffix(".json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Stapelvideo geschrieben: {args.output}; Bilder: {result.image_count}; "
        f"übersprungen: {len(skipped)}; Frames: {result.frame_count}"
    )
    return 0


def render_project_video(args: argparse.Namespace) -> int:
    """Render the enabled storyboard cards in exactly their saved order."""
    project_path = args.project.resolve()
    project = StoryboardProject.load(project_path)
    output_path = args.output.resolve()
    if output_path.exists() and not getattr(args, "overwrite", False):
        raise FileExistsError(f"Output file already exists: {output_path}")
    analysis_path = Path(project.analysis_path).resolve()
    records = json.loads(analysis_path.read_text(encoding="utf-8"))
    by_path = {str(Path(record["path"]).resolve()): record for record in records if record.get("path")}
    stack_entries: list[tuple[Path, Landmarks, float]] = []
    skipped: list[dict[str, str]] = []
    dense_detector = None
    if args.mediapipe_model:
        if not args.person:
            raise ValueError("--person ist zusammen mit --mediapipe-model erforderlich.")
        dense_detector = MediaPipeFaceLandmarker(args.mediapipe_model.resolve())
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
    unavailable_slides = [
        Path(path) for path in (project.opening_slide_path, project.closing_slide_path)
        if path and not Path(path).is_file()
    ]
    if unavailable_slides:
        raise FileNotFoundError(
            "Start- oder Endfolie ist nicht mehr erreichbar: "
            + ", ".join(path.name for path in unavailable_slides)
        )
    _progress(args, "Gesichtsgeometrie", 0, max(1, len(enabled_cards)))
    try:
        for index, card in enumerate(enabled_cards, start=1):
            _progress(args, "Gesichtsgeometrie", index - 1, len(enabled_cards))
            source_path = Path(card.source_path).resolve()
            record = by_path.get(str(source_path))
            if dense_detector:
                region = _region_from_data(record.get("region") if record else None) or find_region(source_path, args.person)
                dense = dense_detector.detect(_oriented_bgr(source_path), region) if region else None
                landmarks = dense.as_sparse_landmarks(args.eye_anchor) if dense else None
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
    _progress(args, "Gesichtsgeometrie", len(enabled_cards), max(1, len(enabled_cards)))
    if project.movie_mode == "timelapse":
        by_year: dict[str, list[tuple[Path, Landmarks, float]]] = {}
        for entry in stack_entries:
            record = by_path.get(str(entry[0].resolve()), {})
            metrics = record.get("metrics") or {}
            face_height = float(metrics.get("face_height_px", 0.0))
            score = float(metrics.get("yunet_score", 0.0))
            yaw = abs(float(metrics.get("pose_yaw_degrees", 0.0)))
            required_height = args.height * 0.22
            quality_level = 0
            if face_height <= 0 or score <= 0 or face_height < required_height * 0.65 or score < 0.42:
                quality_level = 2
            elif face_height < required_height or score < 0.65 or yaw > project.maximum_side_view_degrees:
                quality_level = 1
            if quality_level > project.selection_quality_level:
                continue
            if project.timelapse_frontal_only and yaw > 12.0:
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
    eye_distance = args.eye_distance if args.eye_distance is not None else project.eye_distance
    music_paths = [Path(path).expanduser() for path in project.background_audio_paths[:10]]
    if not music_paths and project.background_audio_path:
        music_paths = [Path(project.background_audio_path).expanduser()]
    rendered_output = output_path.with_name(f".{output_path.stem}.yif-render-{uuid.uuid4().hex}.mp4")
    silent_output = rendered_output
    quality_output: Path | None = None
    if music_paths:
        silent_output = output_path.with_name(f".{output_path.stem}.yif-silent-{uuid.uuid4().hex}.mp4")
    hold_seconds = project.hold_seconds
    transition_seconds = project.transition_seconds
    max_visible_cards = project.max_visible_cards
    if project.movie_mode == "timelapse":
        hold_seconds = project.timelapse_frames_per_image / project.fps
        transition_seconds = project.timelapse_transition_frames / project.fps
        max_visible_cards = 1
    try:
        result = render_stack_mp4(
            stack_entries, silent_output, (args.width, args.height), project.fps,
            hold_seconds, transition_seconds, project.eye_y, eye_distance,
            project.border_pixels if project.border_enabled else 0,
            project.border_color,
            max_visible_cards, args.eye_size_balance,
            Path(project.opening_slide_path) if project.opening_slide_path else None,
            Path(project.closing_slide_path) if project.closing_slide_path else None,
            project.slide_seconds,
            progress=lambda phase, current, total: _progress(args, phase, current, total),
        )
        if music_paths:
            _progress(args, "add_audio", 0, 1)
            mux_background_audio(
                silent_output, music_paths, rendered_output, result.frame_count / result.fps,
                asset_root=bundled_asset_root(),
            )
            _progress(args, "add_audio", 1, 1)
        if project.output_quality != "standard":
            quality_output = output_path.with_name(f".{output_path.stem}.yif-quality-{uuid.uuid4().hex}.mp4")
            _progress(args, "encode_quality", 0, 1)
            transcode_video_quality(
                rendered_output, quality_output, project.output_quality,
                asset_root=bundled_asset_root(),
            )
            _progress(args, "encode_quality", 1, 1)
            rendered_output.unlink(missing_ok=True)
            rendered_output = quality_output
        rendered_output.replace(output_path)
    finally:
        silent_output.unlink(missing_ok=True)
        rendered_output.unlink(missing_ok=True)
        if quality_output is not None:
            quality_output.unlink(missing_ok=True)
    manifest = {
        "source_project": str(project_path),
        "source_analysis": str(analysis_path),
        "images": [path.name for path, _, _ in stack_entries],
        "skipped": skipped,
        "settings": {
            "width": args.width, "height": args.height, "fps": project.fps,
            "movie_mode": project.movie_mode, "hold_seconds": hold_seconds, "transition_seconds": transition_seconds,
            "eye_y": project.eye_y, "eye_distance": eye_distance,
            "border_enabled": project.border_enabled, "border_pixels": project.border_pixels,
            "border_color": project.border_color,
            "max_visible_cards": project.max_visible_cards, "eye_size_balance": args.eye_size_balance,
            "geometry": "mediapipe" if args.mediapipe_model else "analysis",
            "eye_anchor": args.eye_anchor if args.mediapipe_model else None,
            "background_music": [path.name for path in music_paths],
            "opening_slide": Path(project.opening_slide_path).name if project.opening_slide_path else None,
            "closing_slide": Path(project.closing_slide_path).name if project.closing_slide_path else None,
            "slide_seconds": project.slide_seconds,
            "output_quality": project.output_quality,
        },
        "result": result.as_dict(),
    }
    args.output.with_suffix(".json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Projektvideo geschrieben: {args.output}; Bilder: {result.image_count}; Frames: {result.frame_count}")
    return 0


def storyboard(args: argparse.Namespace) -> int:
    launch_storyboard(args.analysis, args.project)
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Lokales Years-in-Focus-Werkzeug")
    sub = root.add_subparsers(dest="command", required=True)
    command = sub.add_parser("align", help="XMP-markierte Bilder analysieren und ausrichten")
    input_source = command.add_mutually_exclusive_group(required=True)
    input_source.add_argument("--input", type=Path, help="Ordner mit JPG/JPEG-Dateien")
    input_source.add_argument("--input-file", dest="input_files", action="append", type=Path, help="Einzelne JPG/JPEG-Datei; mehrfach verwendbar")
    input_source.add_argument("--input-list", type=Path, help="JSON-Liste von Bildpfaden; geeignet für große Importe")
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--person", required=True)
    command.add_argument(
        "--regions-json", type=Path,
        help="Optionale, von digiKam gelesene Gesichtsregionen; ersetzt XMP nur für enthaltene Bilder.",
    )
    command.add_argument("--yunet-model", type=Path, required=True)
    command.add_argument(
        "--mediapipe-model", type=Path,
        help="Optionales lokales Modell zur Erfassung der Kopfpose als QualitÃ¤tsmerkmal.",
    )
    command.add_argument("--width", type=int, default=1920)
    command.add_argument("--height", type=int, default=1080)
    command.add_argument("--eye-y", type=float, default=0.38)
    command.add_argument("--eye-distance", type=float, default=0.11)
    command.add_argument("--rotation-strength", type=float, default=0.0)
    command.add_argument(
        "--framing", choices=("face-normalized", "face-anchored-full", "full", "face-aligned"),
        default="face-normalized",
        help="face-normalized vereinheitlicht Gesichtsgröße und zeigt das Foto zusätzlich im Hintergrund.",
    )
    command.add_argument(
        "--background", choices=("black", "white"), default="black",
        help="Hintergrund für nicht vom vollständigen Foto belegte Flächen.",
    )
    command.add_argument("--yunet-score-threshold", type=float, default=0.42)
    command.add_argument(
        "--reference-originals", action="store_true",
        help="Keine Arbeitskopien erzeugen; Analyse, Kontaktbogen und Storyboard referenzieren die Originalbilder.",
    )
    command.add_argument("--progress", action="store_true", help="Maschinenlesbare Fortschrittszeilen ausgeben")
    command.add_argument(
        "--series-minutes", type=float, default=0.0, metavar="MINUTEN",
        help="Akzeptierte Bilder innerhalb dieses zeitlichen Abstands zu Serien clustern (0 = aus).",
    )
    command.add_argument(
        "--series-keep", type=int, default=1, metavar="ANZAHL",
        help="Anzahl der besten akzeptierten Bilder, die je Seriencluster erhalten bleiben.",
    )
    command.add_argument(
        "--exclude", action="append", default=[], metavar="DATEINAME",
        help="Datei manuell ausschließen; kann mehrfach angegeben werden.",
    )
    command.add_argument(
        "--review", action="append", default=[], metavar="DATEINAME",
        help="Datei manuell als Review markieren; kann mehrfach angegeben werden.",
    )
    command.add_argument(
        "--accept", action="append", default=[], metavar="DATEINAME",
        help="Datei trotz technischer Warnung akzeptieren; kann mehrfach angegeben werden.",
    )
    command.set_defaults(func=align)
    video = sub.add_parser("render-video", help="Akzeptierte ausgerichtete Bilder als MP4 rendern")
    video.add_argument("--analysis", type=Path, required=True, help="analysis.json eines align-Laufs")
    video.add_argument("--output", type=Path, required=True, help="Neue MP4-Ausgabedatei")
    video.add_argument("--fps", type=float, default=30.0)
    video.add_argument("--hold-seconds", type=float, default=4.0)
    video.add_argument("--transition-seconds", type=float, default=0.8)
    video.set_defaults(func=render_video)
    stack = sub.add_parser("render-stack-video", help="Gerahmte Fotos als bleibenden Years-in-Focus-Stapel rendern")
    stack.add_argument("--analysis", type=Path, required=True)
    stack.add_argument("--output", type=Path, required=True)
    stack.add_argument("--width", type=int, default=1920)
    stack.add_argument("--height", type=int, default=1080)
    stack.add_argument("--fps", type=float, default=30.0)
    stack.add_argument("--hold-seconds", type=float, default=4.0)
    stack.add_argument("--transition-seconds", type=float, default=0.8)
    stack.add_argument("--eye-y", type=float, default=0.38)
    stack.add_argument("--eye-distance", type=float, default=0.065)
    stack.add_argument("--border-pixels", type=int, default=10)
    stack.add_argument(
        "--eye-size-balance", type=float, default=0.0,
        help="1 = nur Augenabstand, 0 = XMP-Gesichtsregion; Standard stabilisiert die wahrgenommene Größe.",
    )
    stack.add_argument("--max-visible-cards", type=int, default=4)
    stack.add_argument(
        "--max-card-fraction", type=float, default=0.0,
        help="Optionale Obergrenze für Breite/Höhe einer vollständigen Karte (0 = keine harte Grenze).",
    )
    stack.set_defaults(func=render_stack_video)
    project_video = sub.add_parser("render-project-video", help="Aktives Storyboard in gespeicherter Reihenfolge als Stapelvideo rendern")
    project_video.add_argument("--project", type=Path, required=True, help="Gespeicherte .yif.json-Datei (ältere .facemovie.json wird ebenfalls unterstützt)")
    project_video.add_argument("--output", type=Path, required=True, help="Neue MP4-Ausgabedatei")
    project_video.add_argument("--width", type=int, default=1920)
    project_video.add_argument("--height", type=int, default=1080)
    project_video.add_argument("--mediapipe-model", type=Path)
    project_video.add_argument("--person")
    project_video.add_argument("--eye-anchor", choices=("contour", "iris"), default="contour")
    project_video.add_argument("--eye-distance", type=float, help="Optionale Ziel-Augendistanz relativ zur Videobreite")
    project_video.add_argument(
        "--eye-size-balance", type=float, default=1.0,
        help="1 = identischer Augenabstand; 0 = nur XMP-Gesichtsregion.",
    )
    project_video.add_argument("--progress", action="store_true", help="Maschinenlesbare Fortschrittszeilen ausgeben")
    project_video.add_argument("--overwrite", action="store_true", help="Bestehende Ausgabe erst nach erfolgreichem Export ersetzen")
    project_video.set_defaults(func=render_project_video)
    board = sub.add_parser("storyboard", help="Lokalen Storyboard-Editor öffnen")
    board.add_argument("--analysis", type=Path)
    board.add_argument("--project", type=Path)
    board.set_defaults(func=storyboard)
    return root


def main() -> int:
    args = parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
