from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from facemovie.thumbnail_cache import ThumbnailCache


def test_thumbnail_cache_creates_project_local_preview(tmp_path: Path) -> None:
    source = tmp_path / "original.jpg"
    Image.new("RGB", (800, 400), "#d22").save(source)
    cache = ThumbnailCache(tmp_path / "Mein Film.facemovie.json")

    preview = cache.load_or_create(str(source), 210, 150)

    assert preview.size == (220, 160)
    images = list(cache.directory.glob("*.jpg"))
    metadata = list(cache.directory.glob("*.json"))
    assert len(images) == len(metadata) == 1
    assert json.loads(metadata[0].read_text(encoding="utf-8"))["size"] == source.stat().st_size


def test_thumbnail_cache_rebuilds_when_original_changes(tmp_path: Path) -> None:
    source = tmp_path / "original.jpg"
    Image.new("RGB", (400, 400), "#d22").save(source)
    cache = ThumbnailCache(tmp_path / "Mein Film.facemovie.json")
    cache.load_or_create(str(source), 210, 150)
    metadata_path = next(cache.directory.glob("*.json"))
    first_signature = json.loads(metadata_path.read_text(encoding="utf-8"))

    Image.new("RGB", (800, 400), "#22d").save(source)
    cache.load_or_create(str(source), 210, 150)

    assert json.loads(metadata_path.read_text(encoding="utf-8")) != first_signature
