# Years in Focus

*A life in pictures – in focus over time.*

Years in Focus (YiF) is a local Windows application for creating videos from
photos taken over time. It aligns photos around a person already tagged in the
image, blends them into a Years-in-Focus movie, or creates a time-lapse. Your
original images remain unchanged.

> **Prototype:** YiF is in an early stage of development. Keep backups of your
> project files and review generated videos before sharing them.

## Features

- Import JPG/JPEG files or choose photos from a digiKam people collection.
- Locally evaluate existing face regions and eye geometry.
- Interactive card movie preview with the full stack, timeline and play/pause.
- Cursor-centred zoom and forward/backward navigation for eye correction.
- Project-specific card size, filters and sort view; stable card scrolling.
- Recover moved project data folders and show original resolution/file size.
- Flag faces that are too small or viewed from the side.
- Select, sort and manually order images in the card view.
- Correct eye positions manually for individual cards.
- Create a regular Years-in-Focus movie or a fast time-lapse.
- Export MP4 files locally, with optional music and opening/closing slides.
- Use the interface in German or English.

YiF has no cloud backend, user accounts or telemetry. See
[PRIVACY.md](PRIVACY.md) for details.

## Installing on Windows

Windows builds are provided as installers in GitHub Releases. Run the installer
and follow the setup wizard. Windows SmartScreen may show a warning for
unsigned prototype builds.

## digiKam integration

YiF supports the local database variants commonly used by digiKam:

- SQLite;
- digiKam's internal MySQL/MariaDB server;
- an externally operated MySQL/MariaDB server.

The connection only reads image paths and face rectangles needed for the
selected person. It does not modify the digiKam database.

## Project files

Projects use the `.yif.json` extension; legacy `.facemovie.json` projects remain readable.
Move the project file and its data folder together. Internal analysis paths are
saved relative to the project; old absolute paths can be recovered when a unique
matching data folder is found. Project files contain local file paths
and should normally not be committed to a public repository.

## Development

Python 3.11 or later is required. To create a development environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Start the graphical application with `python run_storyboard.pyw`.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m compileall -q src tests
python -m ruff check --select F src tests
python -m pytest -q
```

## License, privacy and third-party components

YiF's own source code is available under the [MIT License](LICENSE), Copyright
© 2026 Simon Gaschler. Notices for bundled components are available in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). See
[SECURITY.md](SECURITY.md) for security reporting.

## Version 0.1.5

See [release notes](RELEASE_NOTES_0.1.5.md) for changes, validation status and the
Windows installer SHA-256. The card movie preview covers the photo sequence;
opening/closing slides and music are checked through an exported MP4 preview.
New imports use EXIF DateTimeOriginal, or DateTimeDigitized if unavailable;
generic DateTime is no longer used as a capture date. Existing analyses are
not migrated automatically.

Windows build instructions are in [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).
FFmpeg build inputs are documented in [third_party/ffmpeg/README.md](third_party/ffmpeg/README.md).
