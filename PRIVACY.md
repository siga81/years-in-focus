# Datenschutz und lokale Datenverarbeitung

Stand: 6. Oktober 2026 (aktueller Quellstand)

Years in Focus ist eine lokale Windows-Anwendung. Sie erstellt Videosequenzen
aus Fotos, die der Nutzer selbst auswählt oder über seine eigene digiKam-
Bibliothek auswählt.

## Keine Übertragung an Years in Focus

Years in Focus überträgt keine Fotos, Videodateien, Gesichtsregionen,
Personennamen, Projektdateien oder digiKam-Datenbankinhalte an einen Server des
Projekts. Es gibt keine Nutzerkonten, Telemetrie, Analyse- oder Werbedienste.

Die Schaltfläche zu Ko-fi öffnet nur nach einem ausdrücklichen Klick den
Standardbrowser mit `https://ko-fi.com/siga81`. Ab diesem Zeitpunkt gelten die
Datenschutzbestimmungen von Ko-fi, nicht diese Datei.

## Lokal gespeicherte Daten

- Projektdateien (`.yif.json`, ältere `.facemovie.json`) enthalten die vom
  Nutzer gewählte Bildreihenfolge, Einstellungen, lokale Dateipfade und – sofern
  vorhanden – lokale Gesichts-/Augenkorrekturen.
- Die Anwendung speichert unter `%APPDATA%\YearsInFocus\settings.json` lokale
  Einstellungen, zuletzt verwendete Projektpfade sowie eine digiKam-
  Verbindungsbeschreibung. Datenbankpasswörter werden nicht dauerhaft
  gespeichert.
- Projektlokale Analyse- und Regionsdateien enthalten Bildpfade, Zielregionen,
  Landmarken und Qualitäts-/Kopfposewerte. Arbeitsausgaben können Kontaktbögen,
  ausgerichtete Bilder und Protokolle enthalten; Sicherungen können frühere
  Projektpfade bewahren. Diese Dateien sind ebenfalls privat zu behandeln.
- Ältere Einstellungen können aus `%APPDATA%\FaceMovie` eingelesen werden.
- Thumbnail-Caches und erzeugte Videos bleiben auf dem lokalen Rechner bzw. am
  vom Nutzer gewählten Ausgabeort.

## digiKam

Bei einer ausdrücklich eingerichteten digiKam-Verbindung liest YiF bestätigte
Personen, Bildpfade und Gesichtsrechtecke aus der vom Nutzer ausgewählten
Datenbank. Die Verbindung wird nur lesend verwendet; YiF verändert die
digiKam-Datenbank nicht.

## Eigene Verantwortung

Fotos und Gesichtsmetadaten können personenbezogene Daten sein. Nutzer sind
selbst dafür verantwortlich, nur Bilder zu verarbeiten und zu veröffentlichen,
für die sie die erforderlichen Rechte und Einwilligungen besitzen.
