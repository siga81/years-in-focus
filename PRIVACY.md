# Privacy and local data processing

Last updated: 18 August 2026

Years in Focus is a local Windows application. It creates video sequences from
photos that you select yourself, either directly or from your own digiKam
library.

## No data sent to Years in Focus

Years in Focus does not transmit photos, video files, face regions, names,
project files or digiKam database contents to a project server. There are no
user accounts, telemetry, analytics or advertising services.

The Ko-fi button opens your default browser at `https://ko-fi.com/siga81` only
after you explicitly click it. From that point, Ko-fi's privacy policy applies,
not this document.

## Data stored locally

- Project files (`.yif.json`) contain your selected image order, settings, local
  file paths and, where present, local face and eye corrections.
- The application stores local settings, recently used project paths and a
  digiKam connection description in `%APPDATA%\YearsInFocus\settings.json`.
  Database passwords are not stored permanently.
- Thumbnail caches and generated videos remain on your computer or at the
  output location you choose.

## digiKam

When you explicitly configure a digiKam connection, YiF reads confirmed people,
image paths and face rectangles from the database you selected. The connection
is read-only; YiF does not modify the digiKam database.

## Your responsibility

Photos and face metadata may be personal data. You are responsible for
processing and publishing only images for which you have the necessary rights
and consent.
