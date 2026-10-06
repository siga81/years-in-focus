# Years in Focus 0.1.2

*A lifetime of photos, aligned in motion.*

## Neu in diesem Test-Release

- Die rechte Arbeitsseite ist in klarere Tabs gegliedert und der Storyboard-Tab
  trennt Bildauswahl sowie Serienbildlogik besser.
- Export-Presets umfassen 480p, 720p, 1080p, 4K, Hochkant (1080 × 1920) und
  quadratisch (1080 × 1080).
- Der Export-Tab zeigt Zielformat, Bildrate, Qualitätsprofil, Bildanzahl,
  Start-/Endfolien, Musik und die geschätzte Filmdauer. Die Vorschau ist eine
  separate, optionale Kontrolle.
- Startfolien blenden aus Schwarz ein, Endfolien blenden weich nach Schwarz aus.
- Eine Wiedergabeliste mit bis zu zehn lokalen Musikdateien kann als Tonspur
  genutzt werden; YiF wiederholt die Liste bei Bedarf und blendet am Ende aus.
- Verschobene Originalbilder können einzeln oder gesammelt wiederverknüpft werden.
- Unter **Ansicht → Erweiterte Ausgabeoptionen** stehen optional die Profile
  „höhere Qualität“ und „kleinere Datei“ bereit. Der Standardexport bleibt die
  schnellste, unveränderte Voreinstellung.

## Installation

Die 64-Bit-Installationsdatei heißt nach dem Build:

`release\installer\YearsInFocus-Setup-0.1.2-x64-system.exe`

Windows fragt während der Installation selbst nach der erforderlichen Berechtigung.
Die Anwendung wird standardmäßig unter `C:\Program Files\Years in Focus` installiert.
Ein Desktop-Symbol kann optional ausgewählt werden.

## Wichtig

- YiF arbeitet lokal und verändert weder Originalbilder noch XMP-Daten oder die
  digiKam-Datenbank.
- Direkte digiKam-Importe bleiben optional und lesend.
- JPG/JPEG sind weiterhin die unterstützten Bildformate.
- Für Hintergrundmusik sowie die erweiterten Qualitätsprofile wird die mit YiF
  lokal verfügbares FFmpeg benötigt. Es ist in diesem Test-Installer noch nicht
  enthalten; die gebündelte, lizenzgeprüfte Auslieferung ist vor einem externen
  Beta-Test vorgesehen.
