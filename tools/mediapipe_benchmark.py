"""Compare old YuNet eye points with MediaPipe Face Mesh on selected images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from facemovie.metadata.xmp import find_region
from facemovie.rendering.stack import render_stack_mp4
from facemovie.vision.mediapipe_landmarker import MediaPipeFaceLandmarker


def oriented_bgr(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        rgb = ImageOps.exif_transpose(image).convert("RGB")
    return cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)


def crop_around(points: list[np.ndarray], image: np.ndarray, scale: float = 2.5) -> tuple[np.ndarray, int, int]:
    all_points = np.vstack(points)
    center = all_points.mean(axis=0)
    span = max(float(np.ptp(all_points[:, 0])), float(np.ptp(all_points[:, 1])), 100.0) * scale
    x1 = max(0, round(center[0] - span))
    y1 = max(0, round(center[1] - span * 0.75))
    x2 = min(image.shape[1], round(center[0] + span))
    y2 = min(image.shape[0], round(center[1] + span * 0.95))
    return image[y1:y2, x1:x2].copy(), x1, y1


def draw_diagnostic(
    image: np.ndarray, dense, old_record: dict, title: str,
) -> np.ndarray:
    old = old_record["landmarks"]
    old_eyes = [np.asarray(old["left_eye"]), np.asarray(old["right_eye"])]
    new_eyes = [dense.right_eye_center, dense.left_eye_center]
    irises = [dense.right_iris_center, dense.left_iris_center]
    crop, x1, y1 = crop_around(new_eyes + irises, image)

    def point(value: np.ndarray, color: tuple[int, int, int], radius: int) -> None:
        xy = np.rint(value - (x1, y1)).astype(int)
        cv2.circle(crop, tuple(xy), radius, color, -1, cv2.LINE_AA)

    for value in old_eyes:
        point(value, (0, 0, 255), 16)
    for value in new_eyes:
        point(value, (255, 255, 0), 13)
    for value in irises:
        point(value, (0, 255, 0), 9)
    cv2.putText(crop, title, (20, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.putText(crop, "Rot: YuNet | Cyan: Augenkontur | Gruen: Iris", (20, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
    target_height = 640
    factor = target_height / crop.shape[0]
    return cv2.resize(crop, (round(crop.shape[1] * factor), target_height), interpolation=cv2.INTER_AREA)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--person", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("images", nargs="+")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    records = json.loads(args.analysis.read_text(encoding="utf-8"))
    by_name = {Path(record["path"]).name: record for record in records}
    panels: list[np.ndarray] = []
    contour_entries = []
    iris_entries = []
    report = []
    with MediaPipeFaceLandmarker(args.model) as detector:
        for name in args.images:
            record = by_name[name]
            path = Path(record["path"])
            image = oriented_bgr(path)
            region = find_region(path, args.person)
            dense = detector.detect(image, region)
            if dense is None:
                raise RuntimeError(f"MediaPipe fand keine Landmarken in {name}")
            panels.append(draw_diagnostic(image, dense, record, name))
            contour = dense.as_sparse_landmarks("contour")
            iris = dense.as_sparse_landmarks("iris")
            contour_entries.append((path, contour, contour.face_box[3]))
            iris_entries.append((path, iris, iris.face_box[3]))
            old = record["landmarks"]
            old_distance = float(np.linalg.norm(np.asarray(old["right_eye"]) - np.asarray(old["left_eye"])))
            report.append({
                "filename": name,
                "yunet_eye_distance": old_distance,
                "mediapipe_eye_distance": dense.eye_distance,
                "eye_centers": [dense.right_eye_center.tolist(), dense.left_eye_center.tolist()],
                "iris_centers": [dense.right_iris_center.tolist(), dense.left_iris_center.tolist()],
            })

    width = max(panel.shape[1] for panel in panels)
    padded = [cv2.copyMakeBorder(panel, 0, 0, 0, width - panel.shape[1], cv2.BORDER_CONSTANT, value=(25, 25, 25)) for panel in panels]
    cv2.imwrite(str(args.output / "landmark-vergleich.jpg"), np.hstack(padded))
    (args.output / "landmark-vergleich.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    render_stack_mp4(
        contour_entries, args.output / "mediapipe-zwei-bilder-kontur.mp4", (1920, 1080), 30.0,
        3.0, 1.2, 0.38, 0.04, 10, 0.0, 0, 1.0,
    )
    render_stack_mp4(
        iris_entries, args.output / "mediapipe-zwei-bilder-iris.mp4", (1920, 1080), 30.0,
        3.0, 1.2, 0.38, 0.04, 10, 0.0, 0, 1.0,
    )
    print(f"Benchmark geschrieben: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
