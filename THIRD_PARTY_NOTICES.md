# Third-Party Notices

Stand: 18. August 2026. Diese Datei dokumentiert die beim Build von Years in
Focus 0.1.4 verwendeten externen Komponenten. Sie ersetzt keine vollständige
rechtliche Freigabe für eine öffentliche oder kommerzielle Verteilung.

## Python-Komponenten

Die Anwendung wird mit Python und PyInstaller paketiert. Der geprüfte
Build-Umgebungssatz enthält insbesondere die folgenden Laufzeitkomponenten:

| Komponente | geprüfte Version | Lizenz / Hinweis |
| --- | --- | --- |
| Python | 3.11 (Build-Umgebung) | PSF License |
| Pillow | 12.3.0 | HPND |
| NumPy | 2.4.6 | BSD-3-Clause; Lizenztexte liegen im Paket |
| OpenCV / opencv-contrib-python | 5.0.0.93 | Apache-2.0; Lizenztexte liegen im Paket |
| MediaPipe | 0.10.35 | Apache-2.0; Lizenztext liegt im Paket |
| PyMySQL | 1.2.0 | MIT; wird für den optionalen MariaDB-digiKam-Import gebündelt |
| PyInstaller | 6.21.0 | GPL-2.0-or-later mit Bootloader-Ausnahme |

Weitere indirekte Python-Abhängigkeiten werden von PyInstaller entsprechend
ihres Bedarfs eingebunden. Die erzeugte portable Ausgabe enthält die jeweils
mitgelieferten Paket-Lizenztexte, soweit diese im Paket vorhanden sind.

## Modelle

| Datei | SHA-256 | Herkunft / Lizenzhinweis |
| --- | --- | --- |
| `models/mediapipe/face_landmarker.task` | `64184E229B263107BC2B804C6625DB1341FF2BB731874B0BCC2FE6544E0BC9FF` | Google AI Edge Face Landmarker / Face Mesh V2, laut Modellkarte Apache-2.0 |
| `models/yunet/face_detection_yunet_2023mar.onnx` | `8F2383E4DD3CFBB4553EA8718107FC0423210DC964F9F4280604804ED2552FA4` | OpenCV Zoo YuNet; Lizenz vor öffentlicher Verteilung nochmals gegen die konkrete Quelle prüfen |

## FFmpeg

- Build: `N-126086-ge5ecfe8970-20260812`, Windows x64, LGPL-Variante.
- Anbieter: BtbN/FFmpeg-Builds.
- Interne Buildreferenz: `ffmpeg-win64-lgpl.zip`
- SHA-256 der geprüften Buildreferenz: `AD8310426EF419E2ACCABBE57CC7B9970A1B976F6515AE1BB00ECC5CE31D73F2`
- Quellrevision: `e5ecfe8970`; Quelle: <https://github.com/FFmpeg/FFmpeg/tree/e5ecfe8970>
- Der Release enthält `ffmpeg.exe`, `ffprobe.exe`, die LGPLv3-Lizenz und
  `FFMPEG-NOTICE.txt` unter `licenses/`.
- Vor jeder öffentlichen Ausgabe wird die Verfügbarkeit des exakt zugehörigen
  FFmpeg-Quellstands anhand von Revision und Buildreferenz erneut geprüft; dies
  ist ein expliziter Punkt in `PUBLIC_RELEASE_CHECKLIST.md`.

## Projektlizenz

Der eigene Produktcode steht unter der MIT-Lizenz. Die Lizenz gilt nicht
automatisch für die oben genannten Drittkomponenten; deren Hinweise und Lizenzen
sind jeweils zu beachten.
