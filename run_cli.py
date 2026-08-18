"""Console helper for the bundled Years in Focus application."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from facemovie.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
