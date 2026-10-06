import numpy as np
from facemovie.film_probe import blend_pair


def test_pair_dissolve_endpoints_and_midpoint_leave_inputs_unchanged():
    first = np.full((4, 6, 3), 20, dtype=np.uint8)
    second = np.full((4, 6, 3), 100, dtype=np.uint8)
    assert np.array_equal(blend_pair(first, second, 0), first)
    assert np.array_equal(blend_pair(first, second, 1), second)
    assert np.all(blend_pair(first, second, .5) == 60)
    assert np.all(first == 20) and np.all(second == 100)


from dataclasses import asdict
from pathlib import Path
import pytest
from facemovie.models import Landmarks
from facemovie.project import StoryboardProject, StoryboardCard
from facemovie.rendering import stack, probe
from facemovie.rendering.project_sequence import prepare_project_sequence


@pytest.mark.parametrize("limit", [0, 1, 3])
@pytest.mark.parametrize("edge_fades", [True, False])
def test_seekable_probe_matches_every_export_frame(monkeypatch, limit, edge_fades):
    rng = np.random.default_rng(7)
    layers = [(rng.integers(0, 256, (4, 6, 3), dtype=np.uint8),
               rng.integers(0, 256, (4, 6), dtype=np.uint8)) for _ in range(5)]
    def layer(path, *_):
        return layers[int(path.stem)]
    monkeypatch.setattr(stack, "_card_layer", layer)
    monkeypatch.setattr(probe, "_card_layer", layer)
    frames = []
    class Writer:
        def isOpened(self): return True
        def write(self, frame): frames.append(frame.copy())
        def release(self): pass
    monkeypatch.setattr(stack.cv2, "VideoWriter", lambda *_: Writer())
    landmarks = Landmarks((1,1),(3,1),(2,2),(1,3),(3,3),1,(0,0,4,4))
    entries = [(Path(f"{i}.jpg"), landmarks, 4) for i in range(5)]
    project = StoryboardProject(analysis_path="", max_visible_cards=limit, edge_fades_enabled=edge_fades)
    stack.render_stack_mp4(entries, Path("unused.mp4"), (6,4), 10, .3, .2, .38, .033,
                          max_visible_cards=limit, edge_fades=edge_fades)
    timeline = probe.CardTimeline(5, 10, .3, .2, edge_fades)
    renderer = probe.CardProbeRenderer(entries, project, (6,4))
    assert timeline.length == len(frames)
    # Exercise both forward playback and backwards/random seeks, not just holds.
    for frame_index in [*range(len(frames)), *reversed(range(len(frames)))]:
        index, opacity = timeline.position(frame_index)
        assert np.array_equal(renderer.frame(index, opacity), frames[frame_index])
    assert len(renderer.layers) <= 4
    assert len(renderer.checkpoints) <= 4


def test_probe_aborts_between_cards(monkeypatch):
    landmarks = Landmarks((1,1),(3,1),(2,2),(1,3),(3,3),1,(0,0,4,4))
    project = StoryboardProject(analysis_path="")
    renderer = probe.CardProbeRenderer([(Path("x.jpg"), landmarks, 4)], project, (6,4), cancelled=lambda: True)
    with pytest.raises(InterruptedError):
        renderer.frame(0, 1)


def test_timelapse_sequence_uses_export_year_limit_and_frontal_filter(tmp_path):
    landmarks = Landmarks((1,1),(3,1),(2,2),(1,3),(3,3),1,(0,0,4,4))
    cards, records = [], {}
    for index, yaw in enumerate((3, 5, 8, 20)):
        path = tmp_path / f"{index}.jpg"
        path.touch()
        cards.append(StoryboardCard(str(path), True))
        records[str(path.resolve())] = {"path":str(path), "capture_time":"2016-09-17T12:00:00",
            "landmarks":asdict(landmarks), "metrics":{"face_height_px":1000,"yunet_score":.9,"pose_yaw_degrees":yaw}}
    project = StoryboardProject(analysis_path="", cards=cards, movie_mode="timelapse",
                                timelapse_max_images_per_year=2, timelapse_frontal_only=True)
    entries, skipped = prepare_project_sequence(project, records)
    assert [entry[0].name for entry in entries] == ["0.jpg", "2.jpg"]
    assert not skipped


def test_large_unlimited_sequence_has_bounded_pixel_cache_and_correct_random_seeks(monkeypatch):
    landmarks = Landmarks((1,1),(3,1),(2,2),(1,3),(3,3),1,(0,0,4,4))
    entries = [(Path(f"{i}.jpg"), landmarks, 4) for i in range(600)]
    def layer(path, *_):
        index = int(path.stem)
        return np.full((4,6,3), index % 255, np.uint8), np.full((4,6), 128, np.uint8)
    monkeypatch.setattr(probe, "_card_layer", layer)
    renderer = probe.CardProbeRenderer(entries, StoryboardProject(analysis_path=""), (6,4))
    for index in (599, 100, 540, 2):
        expected = stack._compose([(*layer(entry[0]), 1.0) for entry in entries[:index+1]], (6,4))
        assert np.array_equal(renderer.frame(index, None), expected)
        assert len(renderer.layers) <= 4 and len(renderer.checkpoints) <= 4


def test_geometry_preparation_can_be_cancelled_without_changing_cards(tmp_path):
    path = tmp_path / "photo.jpg"
    path.touch()
    card = StoryboardCard(str(path), True, eye_override=[[1,2],[3,4]])
    project = StoryboardProject(analysis_path="", cards=[card])
    with pytest.raises(InterruptedError):
        prepare_project_sequence(project, {}, cancelled=lambda: True)
    assert card.enabled and card.eye_override == [[1,2],[3,4]]


@pytest.mark.parametrize("opacity", [0, .13, .5, .91, 1])
def test_prepared_dissolve_matches_export_without_reloading(opacity):
    rng = np.random.default_rng(13)
    base = rng.integers(0, 256, (4,6,3), dtype=np.uint8)
    color = rng.integers(0, 256, (4,6,3), dtype=np.uint8)
    alpha = rng.integers(0, 256, (4,6), dtype=np.uint8)
    static = np.zeros_like(base)
    prepared = probe.PreparedDissolve(base, color, alpha, static)
    expected = stack._compose([(base, np.full((4,6),255,np.uint8),1), (color,alpha,opacity)], (6,4))
    assert np.array_equal(prepared.frame(opacity), expected)
    assert prepared.frame(None) is static
