"""Starthelfer für Years in Focus unter Windows."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_PYTHONW = ROOT / ".build-venv" / "Scripts" / "pythonw.exe"

# Windows associates .pyw with the global Python launcher.  The project uses a
# local virtual environment, so hand the double-click launch to that interpreter
# before importing Pillow/OpenCV/MediaPipe.  This keeps source testing as simple
# as it was before the standalone installer is rebuilt.
if VENV_PYTHONW.is_file() and Path(sys.executable).resolve() != VENV_PYTHONW.resolve():
    subprocess.Popen([str(VENV_PYTHONW), str(Path(__file__).resolve())], cwd=ROOT)
    raise SystemExit(0)

sys.path.insert(0, str(ROOT / "src"))

from facemovie.storyboard import launch  # noqa: E402


if __name__ == "__main__":
    launch(None, None)
