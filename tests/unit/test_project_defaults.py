from facemovie.project import StoryboardProject


def test_new_project_uses_the_current_movie_defaults() -> None:
    project = StoryboardProject(analysis_path="")

    assert project.movie_mode == "years_in_focus"
    assert project.eye_distance == 0.033
    assert project.eye_y == 0.38
    assert project.hold_seconds == 3.3
    assert project.transition_seconds == 0.8
    assert project.border_pixels == 5
    assert project.border_color == "#ffffff"
