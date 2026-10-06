# Years in Focus 0.1.5

6. Oktober 2026 – Windows Pre-release, weiterhin frühe Entwicklungsphase.
GitHub: https://github.com/siga81/years-in-focus/releases/tag/v0.1.5

## Neu und verbessert

- Interaktive Karten-Filmprobe mit Exportfolge, vollständigem Stapel,
  Wiedergabe/Pause, Zeitleiste und manuellem Überblendungsregler.
- Verbesserte Augenkorrektur: konstante Bildschirm-Markierungen, Zoom am
  Mauszeiger, Navigation in beide Richtungen und geordnete Dialogaktionen.
- Projektbezogen gespeicherte Kartengröße, Filter und Sortieransicht;
  stabilere Scrollposition beim Umschalten und Seitenwechsel beginnt oben.
- Bildauflösung und Dateigröße in den Bilddetails; aktualisierte Kurzanleitung.
- Relative Analysepfade, automatische Erkennung gemeinsam verschobener
  Projektdaten und eigener Wiederherstellungsdialog.
- Neue Importe bevorzugen DateTimeOriginal, ersatzweise DateTimeDigitized;
  Datumquelle wird gespeichert. DateTime dient nicht mehr als Aufnahmedatum.
- Stapel-Export mit begrenztem Bildspeicher, atomarer Projektdatei-Speicherung
  und Korrekturen bei EXIF-Wiederverknüpfung, Regionen, Kopfpose und Vorschau.

## Kompatibilität und Grenzen

Bestehende Projekte bleiben lesbar; vorhandene Aufnahmedaten werden nicht
nachträglich geändert. Projektdatei und Datenordner gemeinsam verschieben.
Externe Originalbilder bleiben über die gesonderte Wiederverknüpfung reparierbar.

Die Karten-Filmprobe enthält keine Musik oder Start-/Endfolien; der vollständige
Film wird mit der MP4-Vorschau geprüft. Bei großen Beständen benötigt die globale
Geometrie eine Vorbereitung; Wiedergabe kann auf langsameren Systemen Frames
überspringen. Exportabbruch unter Windows und gemeinsame Wiederherstellung aller
Projektdateien bleiben weitere Robustheitsarbeiten.

## Build und Abnahme

- Versionskennung 0.1.5 in Paket, Anwendung und Inno-Setup synchronisiert.
- 121 pytest-Tests, Ruff-F-Prüfung und Python-Kompilierung erfolgreich.
- Portable GUI und CLI mit PyInstaller 6.21.0 neu gebaut; Inno Setup erfolgreich.
- Paketierte neue Filmprobe-/Renderer-Module und Versionskennung im GUI-Archiv geprüft.
- Paketierter Import mit YuNet/MediaPipe und EXIF-DateTimeOriginal einschließlich
  gespeicherter Quelle geprüft; paketierter MP4-Export mit relativen Analysepfaden
  erzeugt und alle drei Testframes (320 × 180) wieder eingelesen.
- Paketierte GUI erfolgreich gestartet (Startprüfung, keine vollständige GUI-Abnahme).
- Abhängigkeiten, Modell-/FFmpeg-Hashes und Quell-Hashes:
  `release/build-manifest-0.1.5.json`. Build-Protokolle liegen ebenfalls unter `release`.
- PyInstaller meldet fehlende optionale MediaPipe-LLM-Konverter-Abhängigkeiten
  (JAX/Torch/SentencePiece). Diese Konverter sind keine YiF-Funktion; die
  tatsächlich verwendeten Bildmodelle wurden im paketierten Helfer geprüft.

**Noch offen:** Installation/Deinstallation auf einem sauberen Windows-Konto,
GUI-Endabnahme von digiKam, Augenkorrektur, Filmprobe, Musik/Folien und großem/4K-
Export. Das Pre-release enthält diese offenen Abnahmepunkte; eine neue abschließende
rechtliche Freigabe wurde nicht durchgeführt.
Der 0.1.4-Installer bleibt erhalten; die frühere portable Ausgabe liegt unter
`release/archive/0.1.4-portable-before-0.1.5`.

## Installer-Prüfsumme

`YearsInFocus-Setup-0.1.5-x64-system.exe`
SHA-256: `AFB037EEA2A6F80D3E6D68345DB6C9FAE8709B54CF41E6567BAD1CE500963401`
