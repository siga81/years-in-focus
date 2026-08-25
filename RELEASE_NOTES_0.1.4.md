# Years in Focus 0.1.4 – Public Prototype Release

25 August 2026

Years in Focus (YiF) is a local Windows application for creating photo movies
across time. This first public version is explicitly a **prototype / pre-release**:
please review generated videos before sharing them and keep backups of project
files.

## New in 0.1.4

- a calmer, clearly structured interface;
- manual eye correction from a card or the image preview;
- selection quality with side-view assessment and burst-photo interval;
- a time-lapse mode for larger photo collections;
- the `.yif.json` project format (older `.facemovie.json` projects remain readable);
- a revised quick guide, Ko-fi link and a more clearly structured Images menu.

## Installation

Run the installer and follow the setup wizard. YiF installs to
`C:\Program Files\Years in Focus` by default; a desktop shortcut is optional.

Windows SmartScreen may show a warning for a direct download because this
prototype version is not digitally signed. Obtain the installer only from this
project's GitHub release page.

## Known limitations

- YiF currently targets Windows 10 and 11.
- Face and head-geometry detection are automatic suggestions and can be wrong.
  Review the selection especially for small faces, occluded eyes or strong side
  views.
- digiKam connections are read-only, but differing local database setups may
  still require manual configuration.
- There is no automatic updater or code signing yet.

## Privacy and feedback

Image processing is local. YiF does not send photos, face regions or digiKam
database contents to a YiF server. See `PRIVACY.md` for details.

Use a GitHub issue for ordinary bugs and ideas. Do not attach photos, project
files, databases or other personal data publicly. Report security issues only
through GitHub's private vulnerability reporting channel.

## Installer checksum

`YearsInFocus-Setup-0.1.4-x64-system.exe`
SHA-256: `C19DC849C141E704ADE5A62E9554EF16D64F20A4F509B57AB72F3C249406A608`
