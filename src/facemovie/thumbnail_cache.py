"""Persistent, project-local thumbnails for the storyboard."""

from __future__ import annotations

import json
import tempfile
from hashlib import sha256
from pathlib import Path

from PIL import Image, ImageOps


class ThumbnailCache:
    """Keep rendered card previews on disk without touching original images."""

    # All three supported card sizes are derived from this one high-quality source.
    # It makes a later small/medium/large switch independent of the original photo.
    BASE_WIDTH = 420
    BASE_HEIGHT = 300

    def __init__(self, project_path: Path) -> None:
        self.directory = project_path.parent / f"{project_path.stem}-Cache" / "thumbnails"

    @staticmethod
    def _source_signature(source_path: Path) -> dict[str, int]:
        stat = source_path.stat()
        return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}

    def _paths(self, source_path: Path) -> tuple[Path, Path]:
        identity = sha256(str(source_path.resolve()).encode("utf-8")).hexdigest()[:24]
        return self.directory / f"{identity}.jpg", self.directory / f"{identity}.json"

    def load_or_create(self, source_path: str, width: int, height: int) -> Image.Image:
        """Return a card board, rebuilding it only when its original changed."""
        source = Path(source_path)
        try:
            signature = self._source_signature(source)
            image_path, metadata_path = self._paths(source)
            if image_path.is_file() and metadata_path.is_file():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata == signature:
                    with Image.open(image_path) as cached:
                        base = cached.convert("RGB")
                    return self._resize(base, width, height)
            base = self._render(source)
            self._store(image_path, metadata_path, base, signature)
            return self._resize(base, width, height)
        except (OSError, ValueError, json.JSONDecodeError):
            return self._fallback(width, height)

    @staticmethod
    def _render(source: Path) -> Image.Image:
        with Image.open(source) as image:
            preview = ImageOps.exif_transpose(image).convert("RGB")
            preview.thumbnail((ThumbnailCache.BASE_WIDTH, ThumbnailCache.BASE_HEIGHT), Image.Resampling.LANCZOS)
            preview = preview.copy()
        board = Image.new("RGB", (ThumbnailCache.BASE_WIDTH + 10, ThumbnailCache.BASE_HEIGHT + 10), "#1f1f1f")
        board.paste(preview, ((board.width - preview.width) // 2, (board.height - preview.height) // 2))
        return board

    @staticmethod
    def _resize(base: Image.Image, width: int, height: int) -> Image.Image:
        return base.resize((width + 10, height + 10), Image.Resampling.LANCZOS)

    @staticmethod
    def _fallback(width: int, height: int) -> Image.Image:
        return Image.new("RGB", (width + 10, height + 10), "#7a1f1f")

    def _store(self, image_path: Path, metadata_path: Path, board: Image.Image, signature: dict[str, int]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.directory, suffix=".jpg", delete=False) as file:
            temporary_image = Path(file.name)
        try:
            board.save(temporary_image, format="JPEG", quality=88, optimize=True)
            temporary_image.replace(image_path)
            metadata_path.write_text(json.dumps(signature), encoding="utf-8")
        finally:
            if temporary_image.exists():
                temporary_image.unlink(missing_ok=True)
