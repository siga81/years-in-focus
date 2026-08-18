# Lizenz- und Referenzprüfung

Stand: 18. August 2026

## Release-Status 0.1.4

Der Installer `0.1.4` ist ein technisch getesteter Windows-Stand fuer die
Projektarbeit und manuelle Erprobung. Die oeffentliche Prototype-
Veroeffentlichung erfolgt erst nach der Abnahme nach
`PUBLIC_RELEASE_CHECKLIST.md`. Dieses Dokument ist eine technische
Projektentscheidung und keine Rechtsberatung.

## Hintergrundmusik und FFmpeg

- Der Installer `0.1.4` enthält einen bewusst ausgewählten **LGPLv3**-Build von
  BtbN/FFmpeg-Builds: `ffmpeg-N-126086-ge5ecfe8970-20260812-win64-lgpl`.
  Beigefügt werden ausschließlich `ffmpeg.exe`, `ffprobe.exe` und die originale
  `LICENSE.txt` als `licenses\\LICENSE-FFmpeg-LGPLv3.txt`.
- Der vorher auf dem Entwicklungsrechner vorhandene Build unter `C:\\ffmpeg` wurde
  **nicht** übernommen, da er mit `--enable-gpl` erstellt war. Der gewählte Build
  weist `--disable-libx264`, `--disable-libx265`, `--disable-libxvid` und kein
  `--enable-gpl` aus.
- Vor einer öffentlichen oder kommerziellen Veröffentlichung: FFmpeg-Quellarchiv
  mit exakt passender Buildkennung bereitstellen, Herkunft/Hash dokumentieren,
  Drittanbieter-Notices und About-/Download-Hinweise abschließend rechtlich prüfen.
- Die Audioquelle des Nutzers wird nur gelesen und im Projekt lediglich als Pfad
  referenziert. Sie wird weder in YiF hochgeladen noch in den Projektordner kopiert.

## Produktname und interne Namen

Der sichtbare Produktname lautet **Years in Focus**. Ältere interne Paket-, Dateinamen
und Referenzpfade mit `FaceMovie` sind keine Codeübernahme und keine Lizenzbehauptung;
sie bleiben vorerst aus Kompatibilitätsgründen bestehen.

## MediaPipe Face Landmarker / Face Mesh V2

- Lokales Modell: `models/mediapipe/face_landmarker.task`
- Offizielle Quelle: Google AI Edge, Face Landmarker `float16/latest`.
- Lizenz: Face-Mesh-V2-Modell laut offizieller Modellkarte Apache-2.0;
  MediaPipe-Quellcode ebenfalls Apache-2.0.
- Relevanz: 478 dreidimensionale Gesichtslandmarken einschliesslich Iris- und
  Augenkonturen sowie optionale Gesichtstransformationsmatrix.
- Entscheidung: bevorzugte Geometriequelle fuer die FaceMovie-Ausrichtung. XMP
  oder digiKam bestimmen weiterhin die Identitaet; MediaPipe wird nur innerhalb
  der bereits markierten Personenregion ausgefuehrt.
- Die digiKam-`FaceMatrices` sind SFace-Identitaetsvektoren und keine
  geometrischen Landmarken.

Diese Prüfung ist eine technische Projektentscheidung, keine Rechtsberatung. Vor
einer Veröffentlichung mit gebündelten Modellen oder FFmpeg ist eine abschließende
Lizenzprüfung erforderlich.

## Historisch geprüfte, nicht eingebundene Referenzen

- Commit: `2a3d2eee17c45f2550a7c26b8126388210873c7c`
- Lizenz: GPL-3.0, explizite `LICENSE`-Datei vorhanden.
- Relevanz: globale Ausrichtung von Bildern anhand von Landmarken sowie getrennte
  Video- und Morphing-Schritte.
- Entscheidung: Kein Quellcode wird übernommen. Die Similarity-Transform wird
  eigenständig implementiert. Dadurch bleibt die Lizenzwahl von FaceMovie offen.

## dullage/eyelign

- Commit: `70372e832523fe661e6d5a04de51c3808fdf4f62`
- Lizenz: Im Repository wurde keine Lizenzdatei gefunden.
- Relevanz: Augenpositionen cachen, Bilder über Augenposition, Rotation, Skalierung
  und Zuschnitt normalisieren sowie fehlerhafte Fälle manuell korrigieren.
- Entscheidung: Nur die fachlichen Ideen werden verwendet. Kein Code wird kopiert
  oder eingebunden, solange keine eindeutige Lizenz vorliegt.

## alyssaq/face_morpher

- Commit: `7a30611cd9d33469e843cec9cfa23ccf819386a8`
- Lizenz: Die Paketmetadaten und README nennen MIT; eine eigenständige
  Lizenzdatei wurde im Repository nicht gefunden.
- Relevanz: Referenz für Delaunay-Triangulation und lokale Dreiecksverformung.
- Entscheidung: Keine Architekturgrundlage für den Standardmodus. Nur als
  Vergleichsmaterial für einen gegebenenfalls später ausdrücklich auswählbaren
  Morphing-Modus; bis zur abschließenden Lizenzprüfung kein Code-Import.

## Konsequenz für Years in Focus

Phase 1 implementiert ausschließlich die globale Similarity Transform des
vollständigen Fotos. Die Identität der Hauptperson kommt aus XMP oder digiKam;
Landmarken dienen nur der Ausrichtung. Morphing bleibt eine offene, getrennte
Produktentscheidung und wird nicht nebenbei in den Standardmodus eingeführt.
