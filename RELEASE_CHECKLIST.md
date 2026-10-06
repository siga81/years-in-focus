# Release-Checkliste

Stand: 6. Oktober 2026. Für jede neue Windows-Ausgabe erneut ausführen.
Quelltests allein geben weder Installer noch Veröffentlichung frei.

## Vor dem Build

- Versionsnummer in `pyproject.toml`, `src/facemovie/__init__.py` und
  `installer/YearsInFocus.iss` synchron aktualisieren.
- Unveröffentlichte Änderungen aus `CHANGELOG.md` einer neuen Ausgabe zuordnen;
  Release Notes, README und Roadmap abgleichen.
- Eine saubere Entwicklungs-/Build-Umgebung im aktuellen Projektordner installieren.
  Nach Verschieben des Ordners editierbare Installationen erneut installieren.
- Keine privaten Projekte, Bilder, Datenbanken, Caches, Logs oder Zugangsdaten
  in Paketierung und öffentlichen Quell-Snapshot aufnehmen.

## Technische Prüfung und Build

Aus dem Projektordner; `.build-venv` muss die Dev- und Build-Werkzeuge enthalten:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.\.build-venv\Scripts\python.exe -m compileall -q src tests
.\.build-venv\Scripts\python.exe -m ruff check --select F src tests
.\.build-venv\Scripts\python.exe -m pytest -q
.\tools\build_windows.ps1
.\tools\build_installer.ps1
Get-FileHash '.\release\installer\YearsInFocus-Setup-<VERSION>-x64-system.exe' -Algorithm SHA256
```

`unittest discover` ist unzureichend: Die Suite enthält auch pytest-Funktionstests.
Nach jedem fehlgeschlagenen Schritt zuerst den Fehler beheben. Abhängigkeiten,
Modelle und FFmpeg-Version/Hashes für den tatsächlich gebauten Stand erfassen.

## Abnahme

- Sauberes Windows-Benutzerkonto/Testrechner: Installation, Startmenü,
  optionales Desktop-Symbol und Deinstallation prüfen.
- Neue/alte Projekte, XMP/MWG und EXIF-Rotation, digiKam-Import/Nachimport,
  manuelle Regionen und Augen, fehlende Originale und Wiederverknüpfung testen.
- Regulären Export und Zeitraffer, große Projekte/4K, Hochkant/Quadrat,
  Vorschau-Beschriftungen sowie begrenzte/unbegrenzte Stapel prüfen.
- Start-/Endfolien und Randüberblendungen; Musikliste, Wiederholung,
  Ton-Ausblendung und fehlende Tondateien testen.
- Exportabbruch einschließlich FFmpeg und temporärer Dateien prüfen.
- Installer-Hash, bekannte Einschränkungen und Abnahmeergebnisse in den
  Release Notes festhalten. Alte Installer erst nach erfolgreicher Abnahme ersetzen.

## Öffentliche Veröffentlichung

`PUBLIC_RELEASE_CHECKLIST.md` auf den neuen Stand anwenden. Notices und
`LICENSE_REVIEW.md` müssen die tatsächlich ausgelieferten Komponenten beschreiben.
Einen sauberen öffentlichen Quell-Export separat erzeugen; ein bestehender
`public-release-staging`-Ordner aktualisiert sich nicht automatisch.

Der lokale Build-/Abnahmestand von 0.1.5 steht in `RELEASE_NOTES_0.1.5.md`.
Eine öffentliche Freigabe ist ein separater Schritt. Der 0.1.4-Installer bleibt erhalten.
