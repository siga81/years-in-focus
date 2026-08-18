from facemovie.models import Landmarks
from facemovie.quality import assess


def _landmarks() -> Landmarks:
    return Landmarks((100, 100), (200, 100), (150, 140), (120, 180), (180, 180), 0.9, (70, 60, 170, 240))


def test_strong_side_view_is_reported_for_review() -> None:
    warnings, metrics = assess((800, 600), _landmarks(), 1080, {"pose_yaw_degrees": 28.0})
    assert metrics["pose_yaw_degrees"] == 28.0
    assert any("Starke Seitenansicht" in warning for warning in warnings)


def test_frontal_pose_does_not_add_a_side_view_warning() -> None:
    warnings, _metrics = assess((800, 600), _landmarks(), 1080, {"pose_yaw_degrees": 8.0})
    assert not any("Seitenansicht" in warning for warning in warnings)
