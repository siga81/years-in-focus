import json
from types import SimpleNamespace

from PIL import Image

from facemovie.models import FaceRegion, Landmarks
from facemovie.project import StoryboardProject
from facemovie.storyboard import StoryboardApp


def test_mwg_preview_rectangle_uses_converted_left_top():
    image = Image.new("RGB", (100, 100))
    StoryboardApp._draw_preview_region(image, {
        "x": .4, "y": .3, "width": .2, "height": .2,
        "coordinate_system": "normalized_center",
    })
    assert image.getpixel((40, 30)) == (0, 230, 118)
    assert image.getpixel((30, 20)) == (0, 0, 0)


def test_region_correction_retains_pose_for_automatic_selection(monkeypatch, tmp_path):
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (800, 600)).save(source)
    analysis = tmp_path / "analysis.json"
    analysis.write_text(json.dumps([{"path": str(source)}]), encoding="utf-8")
    app = object.__new__(StoryboardApp)
    app.project = StoryboardProject(analysis_path=str(analysis), person_name="Test")
    app.project_path = tmp_path / "project.yif.json"
    app._yunet_model_path = lambda: tmp_path / "model.onnx"
    app._mark_project_saved = lambda: None
    landmarks = Landmarks((100, 100), (200, 100), (150, 140), (120, 180), (180, 180), .9, (70, 60, 170, 240))
    monkeypatch.setattr("facemovie.storyboard.YuNetLandmarker", lambda _: SimpleNamespace(detect=lambda *_: landmarks))

    class Detector:
        def __init__(self, *_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def detect(self, *_):
            return SimpleNamespace(head_pose_degrees=lambda: {"pose_yaw_degrees": 8.0})

    monkeypatch.setattr("facemovie.storyboard.MediaPipeFaceLandmarker", Detector)
    app._apply_face_region_override(source, FaceRegion("Test", 50, 50, 300, 300, "pixel_left_top", "yif_manual_confirmed"))
    record = json.loads(analysis.read_text(encoding="utf-8"))[0]
    assert record["metrics"]["pose_yaw_degrees"] == 8.0
    assert app._pose_is_accepted(record)
