# Years in Focus 0.1.1

*A lifetime of photos, aligned in motion.*

## Installation

Die 64-Bit-Installationsdatei heißt:

`release\installer\YearsInFocus-Setup-0.1.1-x64-system.exe`

SHA-256:

`28DB38036C3883F6934A5548E13592DB62E104390CE38E2805FE56FB48632E82`

Windows fragt während der Installation selbst nach der erforderlichen Berechtigung.
Die Anwendung wird standardmäßig unter `C:\Program Files\Years in Focus` installiert.
Ein Desktop-Symbol kann optional ausgewählt werden.

## Wichtig für Anwender

- YiF verarbeitet Bilder lokal und verändert weder Originalbilder noch XMP-Daten
  oder die digiKam-Datenbank.
- digiKam ist optional. Für direkte digiKam-Importe muss die lokale digiKam-MariaDB
  erreichbar sein; der Zugriff durch YiF bleibt lesend.
- Ein Projekt speichert Kartenreihenfolge, Aktivierung und Videoeinstellungen in
  einer `.facemovie.json`-Datei. Die zugehörigen Bilder bleiben an ihren Originalorten.
- Vor dem Schließen oder Projektwechsel fragt YiF bei ungespeicherten Änderungen
  ausdrücklich nach.

## Bekannte Grenzen dieses Stands

- Unterstützt werden zunächst JPG/JPEG-Bilder.
- YuNet-Vorschlagsrahmen im manuellen Modus bestimmen keine Identität. Die Auswahl
  muss immer durch den Nutzer bestätigt werden.
- Kein Morphing und keine lokale Gesichtsverformung.
- Musik, Start-/Endbilder, Jahreslinien und automatische Zielpersonen-Clusterung
  gehören zu späteren Versionen.

Details stehen im [Änderungsprotokoll](CHANGELOG.md) und in der
[Roadmap](ROADMAP.md).
