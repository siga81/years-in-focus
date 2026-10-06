# Architektur

Stand: 6. Oktober 2026, Version 0.1.5. Build und Abnahme werden in
`RELEASE_NOTES_0.1.5.md` dokumentiert. `public-release-staging` ist der separat geprüfte öffentliche
Quell-Snapshot für 0.1.5.

## Identität, Geometrie und Ausgabe

XMP (Microsoft Photo Regions oder MWG), digiKam-`tagRegion` oder eine vom Nutzer
bestätigte manuelle Region bestimmen die Zielperson. YuNet liefert lokale
Gesichts-/Augengeometrie und sichtbare Kandidaten für die manuelle Auswahl.
MediaPipe ergänzt beim Import die Kopfpose; beim Export dienen Iriszentren der
präzisen Augenausrichtung. Manuelle Augenpunkte haben Vorrang. Landmarken
identifizieren keine Person über eine Bibliothek hinweg.

Bilder werden EXIF-orientiert gelesen. MWG-Zentrumskoordinaten werden beim
XMP-Lesen in linke obere Rechteckkoordinaten umgerechnet. Alle nachfolgenden
Verbraucher verwenden diese bereits umgerechneten Werte.

Die Ausrichtung des vollständigen Fotos verwendet ausschließlich Translation,
uniforme Skalierung und Rotation. Augenabstand und Gesichtshöhe können als
Größenreferenz gewichtet werden. Es gibt kein Morphing oder lokale Verformung.
Die Standard-Augenlinie liegt bei 38 % von oben, der Ziel-Augenabstand bei 3,3 %
der Ausgabebreite. Projekt- und CLI-Vorgaben können diese Werte überschreiben.

## Arbeitsoberfläche und Module

Die Tkinter-Oberfläche in `storyboard.py` hat die Tabs Allgemein, Storyboard,
Film, Audio & Folien und Export. Sie orchestriert Auswahl, Review, Import und
Export. Zeitverteilung, Qualitätsfilter, Serienreduktion und Zeitraffer-Auswahl
liegen in `selection.py`; die Qualitätsmetriken in `quality.py`.

- `metadata/xmp.py`: Personenregionen und Aufnahmedatum.
- `digikam.py`: SQLite im Nur-Lese-Modus und parameterisierte SELECT-Abfragen
  für MariaDB/MySQL; keine Änderung oder Steuerung des Datenbankservers.
- `importing.py`, `manual_regions.py`, `vision/`: Import, projektlokale Regionen,
  YuNet und MediaPipe.
- `alignment.py`, `models.py`: globale Geometrie und Datenstrukturen.
- `project.py`, `settings.py`, `relink.py`: Persistenz und Quellenreparatur.
- `thumbnail_cache.py`: persistente Vorschauen mit Dateigröße/Änderungszeit als
  Quellvalidierung. Bereits im GUI-Speicher gehaltene Bilder werden nicht laufend
  auf externe Änderungen geprüft.
- `rendering/stack.py`, `video.py`, `audio.py`, `contact_sheet.py`: Stapel,
  Einzelbildfolge, FFmpeg-Nachverarbeitung und Kontaktbogen.
- `cli.py`, `runtime.py`, `branding.py`, `i18n.py`: Prozesssteuerung, gebündelte
  Ressourcen, Produktnamen und Übersetzungen.

Die Kartenansicht zeigt höchstens 240 Karten pro Seite mit maximal zwölf Spalten.
Der Kontaktbogen begrenzt große Bestände auf eine Auswahl von 200 Bildern.
Die Projektdatei und der Export behalten den vollständigen Bestand.

## Rendering und Speicher

OpenCV erzeugt das lautlose MP4 mit dem Codec `mp4v` (MPEG-4 Part 2).
Der Stapel-Renderer bereitet jeweils die nächste Karte vor. Bei unbegrenzter
Sichtbarkeit (`max_visible_cards = 0`) bewahrt ein Float-Komposit die bisherige
Bildfolge einschließlich der bisherigen Rundungspräzision. Bei einer festen
Grenze bleiben nur die benötigten Kartenebenen erhalten. Die Pixelpuffer wachsen
somit mit der Ausgabeauflösung beziehungsweise der sichtbaren Kartenzahl statt
mit dem gesamten Bestand. Einträge und Analysemetadaten bleiben im Speicher.
Der separate ältere Einzelbild-Renderer besitzt diese Stapeloptimierung nicht.

Standzeit, Überblendung, Rahmen, Auflösung und Bildrate sind projektbezogen.
Zeitraffer bietet Frames pro Bild/Übergang, Jahreslimit und Frontalitätsfilter.
Vorschauen mit 480p, 720p oder 1080p behalten das gewählte Ausgabe-Seitenverhältnis;
Kartennummern und Dateinamen sind optionale Vorschau-Beschriftungen.

Bis zu zehn lokale Musikdateien werden in Reihenfolge wiederholt. FFmpeg fügt
AAC-Ton hinzu und blendet ihn am Ende aus; optionale Ausgabeprofile verwenden
zusätzliche MPEG-4-Nachkodierung. Audioquellen bleiben unverändert. Start- und
Endfolien sind fertige Nutzerbilder mit einstellbarer Standzeit von 1–8 Sekunden.
Randüberblendungen sind separat steuerbar. Ohne Endfolie endet der Stapel derzeit
mit dem letzten Kartenbild; eine Überblendung ins Schwarz wird nicht erzeugt.

## Persistenz und Integrität

Neue Projekte heißen `.yif.json`; `.facemovie.json` bleibt lesbar. Der Paketname
`facemovie` bleibt intern bestehen. Einstellungen liegen unter
`%APPDATA%\YearsInFocus`, mit Lesefallback auf `%APPDATA%\FaceMovie`.
Passwörter bleiben in der Sitzung und werden nicht in den Einstellungen gespeichert.

Analyse, manuelle Regionen, Vorschaubilder und gegebenenfalls Sicherungen liegen
projektlokal. Originalbilder, XMP und digiKam bleiben unverändert. Nachimporte
überspringen bestehende Quellen und hängen neue Karten zunächst deaktiviert an.
Manuelle Regionenänderungen aktualisieren auch die Kopfpose.

Fehlende Originale werden angezeigt und können einzeln oder nach Suche in einem
vom Nutzer gewählten Stammordner wiederverknüpft werden. Die Sammelsuche verlangt
bei vorhandener Analyse passende EXIF-orientierte Maße und eindeutige Treffer.
Ein Dateifingerabdruck und stabile digiKam-Bild-IDs sind noch nicht implementiert;
die Einzelzuordnung benötigt weiterhin eine bewusste Prüfung durch den Nutzer.

Projektdateien werden im selben Verzeichnis temporär geschrieben und atomar
ersetzt. Projekt, Analyse und Regionsdatei bilden dennoch keine gemeinsame
Transaktion. Prozessabbruch und Wiederherstellung über alle Dateien bleiben
wichtige weitere Robustheitsarbeiten.

## Verschieben von Projekten

Projektdatei und zugehörigen Datenordner gemeinsam verschieben. Analysepfade
innerhalb des Projektordners werden beim Speichern relativ hinterlegt und beim
Öffnen vom aktuellen Projektordner aus aufgelöst. Externe Originalbild-, Musik-
und Folienpfade bleiben davon getrennt.

Bei älteren absoluten Analysepfaden prüft YiF den gleichnamigen Datenordner neben
der Projektdatei sowie den üblichen `<Projektdatei-Stamm>-Daten`-Ordner. Nur ein
lesbarer, eindeutiger Treffer mit allen Projektbildpfaden wird automatisch genutzt.
Die Anwendung meldet die Wiederherstellung; beim nächsten Speichern wird der Pfad
aktualisiert. Mehrdeutige Treffer werden nicht automatisch übernommen.

Fehlen Analysedaten oder sind sie unlesbar, bietet YiF beim Öffnen die Ordnersuche
an. Sie ist später auch im Bilder-Menü über **Datenordner suchen…** erreichbar.
Karten zeigen **Analysedaten fehlen**, statt fehlende Daten als unbekanntes
Aufnahmedatum oder unzuverlässige Augengeometrie auszugeben. Export bleibt bis zur
Wiederherstellung gesperrt. Die Ordnersuche prüft die Zuordnung zu allen Bildern.

## Aufnahmedatum bei neuen Importen

Neue Importe verwenden zuerst EXIF `DateTimeOriginal` (einschließlich des
verschachtelten EXIF-Bereichs), ersatzweise `DateTimeDigitized`. Das allgemeine
`DateTime` wird nicht als Aufnahmedatum verwendet, da es eine spätere Bearbeitung
beschreiben kann. Fehlen beide gültigen Werte, bleibt das Aufnahmedatum unbekannt.
Die Analyse speichert die Quelle in `capture_time_source` als `DateTimeOriginal`,
`DateTimeDigitized` oder `null`. Ein Digitalisierungsdatum kann bei gescannten
Bildern vom ursprünglichen Aufnahmezeitpunkt abweichen.

Bestehende Analysen werden nicht migriert oder beim Öffnen neu datiert.
Auch ein Nachimport aktualisiert die Datumswerte bereits vorhandener Bilder nicht.

## Interaktive Karten-Filmprobe

`rendering/project_sequence.py` bereitet die gemeinsame Export-/Probe-Geometrie
und Zeitraffer-Auswahl vor; die Auswahl nutzt stets die finale Projektauflösung.
`rendering/probe.py` bildet eine framebasierte Karten-Zeitleiste ab und verwendet
die Kartenebenen/Komposition des Stapel-Renderers. Die globale Normalisierung
bezieht sämtliche tatsächlich exportierbaren Einträge ein. Vier Kartenebenen und
vier Float-Stapel-Zwischenstände begrenzen den Bildcache auch bei Rückwärtssprüngen.
`film_probe.py` hält eine Projekt-Momentaufnahme, steuert Hintergrundberechnung,
aktuellste Sprunganfrage, Wiedergabe und Tk-Anzeige. Kein Tk-Aufruf erfolgt aus dem
Worker. Die Probe schreibt keine Dateien. Musik und Folien bleiben beim MP4-Export.
