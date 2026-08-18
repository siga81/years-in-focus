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

New projects use the `.yif.json` extension. Older `.facemovie.json` projects
can still be opened and used. Project files contain local file paths and should
normally not be committed to a public repository.

## Development

Python 3.11 or later is required. To create a development environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Start the graphical application with `run_storyboard.pyw`.

```powershell
.\.build-venv\Scripts\python.exe -m compileall -q src
.\.build-venv\Scripts\python.exe -m ruff check --select F src tests
.\.build-venv\Scripts\python.exe -m pytest -q
```

## License, privacy and third-party components

YiF's own source code is available under the [MIT License](LICENSE), Copyright
© 2026 Simon Gaschler. Notices for bundled components are available in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[LICENSE_REVIEW.md](LICENSE_REVIEW.md). See [SECURITY.md](SECURITY.md) for
security reporting.

The steps for a public prototype release are listed in
[PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md).
