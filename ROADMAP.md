# Years in Focus – Roadmap

Stand: 6. Oktober 2026. Version 0.1.5 als lokale Windows-Ausgabe. Diese Roadmap beschreibt Fähigkeiten und nächste Arbeiten,
keine bereits zugesagten Versionsnummern oder Veröffentlichungstermine.

## Produktziel und Leitplanken

Ein Leben in Bildern – im Fokus der Zeit. Vollständige Fotos werden anhand einer
bestätigten Person global ausgerichtet und als Fotostapel oder Zeitraffer exportiert.
Verarbeitung erfolgt lokal, Originale und digiKam bleiben unverändert. Keine
lokale Gesichtsverformung und kein Morphing. Landmarken bestimmen die Geometrie,
XMP/digiKam oder manuelle Bestätigung bestimmen die Identität. Legacy-Projekte
und Einstellungen bleiben lesbar.

## Implementiert

- [x] Tkinter-Arbeitsoberfläche mit fünf Tabs, Deutsch/Englisch, Projektmenü,
  zuletzt verwendeten Projekten und Speichern-/Verwerfen-Abfrage.
- [x] XMP- und digiKam-Import (SQLite/MySQL/MariaDB), lokale Konfigurationserkennung,
  manuelle Zielregionen, Nachimport deaktivierter Karten und digiKam-Nachimport.
- [x] EXIF-orientierte Bildprüfung, YuNet-Geometrie, MediaPipe-Kopfpose,
  manuelle Augenkorrektur und Iris-Ausrichtungsprobe.
- [x] Qualitätsfilter, maximale Seitenansicht, zeitliche Auswahl und Serienreduktion.
- [x] Kartenreihenfolge, Jahresmarken, 240 Karten pro Seite, persistenter
  Thumbnail-Cache und begrenzter Kontaktbogen.
- [x] Quellenreparatur einzeln und per eindeutiger Sammelsuche mit Maßprüfung.
- [x] Stapel-Export und Zeitraffer mit Frames pro Bild, Jahreslimit und Frontalfilter.
- [x] Ausgabe-Presets bis 4K sowie Hochkant/Quadrat; Vorschau in passendem
  Seitenverhältnis; optionale Qualitätsprofile.
- [x] Musikliste bis zehn Dateien, Laufzeitanzeige und Wiederholung; Start-/Endfolien.
- [x] Windows-Paketierung, Inno-Setup-Installer und gebündelte Modelle/FFmpeg.
- [x] Speicherbegrenzte Vorbereitung des Stapel-Exports, atomarer Projektdatei-Ersatz
  und Regressionstests für die im Oktober korrigierten Fehler.

## Nächste Prioritäten

- [ ] Abbruch von Export und FFmpeg unter Windows zuverlässig gemeinsam behandeln,
  einschließlich temporärer Dateien und wiederholtem Start nach Abbruch.
- [ ] Konsistente Wiederherstellung von Projekt, Analyse und Regionen nach Fehlern;
  robustere Prüfung beschädigter oder unvollständiger Projektdateien.
- [ ] Dauerprognose für gefilterten Zeitraffer und Folien exakt mit dem Renderer
  abgleichen; Verhalten am Filmende ohne Endfolie ausdrücklich gestalten.
- [ ] Wiederverknüpfung durch Fingerabdruck/Datum und stabile digiKam-Bild-IDs
  absichern; verschobene Musikquellen komfortabel reparieren.
- [ ] Reale große Fotoarchive und 4K-Ausgabe hinsichtlich Spitzen-RAM, Laufzeit,
  Abbruch und visueller Ausrichtung prüfen. Automatisierte Tests ersetzen diese
  Windows-/Archiv-Abnahme nicht.
- [ ] Umfangreiche GUI-Orchestrierung schrittweise aus `storyboard.py` auslagern,
  insbesondere Prozesssteuerung und Projektaktionen.
- [ ] Reproduzierbare Build-Abhängigkeiten dokumentieren/fixieren, doppelte OpenCV-
  Distributionen im Build prüfen und sauberen Installer erneut abnehmen.
- [ ] Seltene Fehlerdialoge auf vollständige Übersetzung prüfen.
- [ ] Öffentlichen Quell-Snapshot, Release-Dokumente, tatsächlichen Installer und
  Modell-/FFmpeg-Herkunft gemäß Release-Checklisten gemeinsam freigeben.

## Spätere Produktoptionen

- [ ] Zentraler Einstellungsdialog, Ereignis-/Ordnerfilter und transparentere
  Erklärung automatischer Auswahlentscheidungen.
- [ ] Windows-Datei-Drag&Drop und geführter Einstieg mit Beispielprojekten.
- [ ] Zusätzliche Gestaltungsvorlagen und sichtbare Übergangshinweise.
- [ ] Optional bestätigte Zielpersonen-Gruppierung ausschließlich innerhalb der
  ausdrücklich importierten Serie, erst nach Modell-, Lizenz- und Datenschutzprüfung.
- [ ] Weitere Plattformen nach stabilem Windows-Workflow.

Nicht vorgesehen sind eine vollständige Fotoverwaltung, unbeaufsichtigte
Identitätssuche in der gesamten Bibliothek oder cloudbasierte Gesichtserkennung.
