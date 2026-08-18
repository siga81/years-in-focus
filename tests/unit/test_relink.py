from __future__ import annotations

from pathlib import Path

from PIL import Image

from facemovie.relink import find_unique_matches, normalised_path


def _image(path: Path, size: tuple[int, int]) -> None:
    Image.new("RGB", size, "white").save(path)


def test_bulk_relink_accepts_one_same_name_and_saved_size(tmp_path: Path) -> None:
    root = tmp_path / "moved"
    root.mkdir()
    candidate = root / "family.jpg"
    _image(candidate, (640, 480))
    old = "D:/photos/family.jpg"
    result = find_unique_matches([old], root, {normalised_path(old): (640, 480)})
    assert result.matches[old] == candidate.resolve()
    assert not result.ambiguous
    assert not result.unresolved


def test_bulk_relink_never_chooses_same_name_with_wrong_or_multiple_size(tmp_path: Path) -> None:
    root = tmp_path / "moved"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    _image(root / "a" / "family.jpg", (640, 480))
    _image(root / "b" / "family.jpg", (640, 480))
    old = "D:/photos/family.jpg"
    result = find_unique_matches([old], root, {normalised_path(old): (640, 480)})
    assert not result.matches
    assert result.ambiguous == (old,)
