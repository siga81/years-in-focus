# Years in Focus

*Ein Leben in Bildern – im Fokus der Zeit.*

Years in Focus (YiF) ist eine lokale Windows-Anwendung für zeitübergreifende
Foto-Filme. Sie richtet Fotos anhand einer bereits markierten Person aus,
überblendet sie oder erstellt einen Zeitraffer. Die Originalbilder bleiben
unverändert.

> **Prototype:** YiF befindet sich in einer frühen Entwicklungsphase. Bitte
> verwende Sicherungskopien deiner Projektdateien und prüfe erzeugte Videos vor
> einer Weitergabe.

## Was YiF kann

- JPG/JPEG-Import sowie Auswahl aus einer digiKam-Personenbibliothek;
- lokale Auswertung vorhandener Gesichtsregionen und Augengeometrie;
- Qualitätsbewertung für zu kleine oder seitlich aufgenommene Gesichter;
- Kartenansicht zur Auswahl, Sortierung und manuellen Reihenfolge;
- manuelle Augenkorrektur für einzelne Karten;
- regulärer Years-in-Focus-Film oder schneller Zeitraffer;
- lokaler MP4-Export mit optionaler Musik sowie Start- und Endfolien;
- deutsch- und englischsprachige Oberfläche.

YiF verwendet kein Cloud-Backend, keine Nutzerkonten und keine Telemetrie.
Details stehen in [PRIVACY.md](PRIVACY.md).

## Installation unter Windows

Die jeweilige Windows-Ausgabe wird als Installer in den GitHub-Releases
bereitgestellt. Nach dem Start des Installers führt der Assistent durch die
Installation. Bei unsignierten Prototype-Versionen kann Windows SmartScreen
einen Hinweis anzeigen.

## digiKam-Verbindung

YiF unterstützt die in digiKam üblichen lokalen Datenbankvarianten:

- SQLite;
- digiKams internen MySQL/MariaDB-Server;
- einen extern betriebenen MySQL/MariaDB-Server.

Die Verbindung liest nur die für die gewählte Person benötigten Bildpfade und
Gesichtsrechtecke. Sie verändert die digiKam-Datenbank nicht.

## Projektdateien

Neue Projekte verwenden die Endung `.yif.json`. Ältere
`.facemovie.json`-Projekte werden weiterhin geöffnet und können weiterverwendet
werden. Projektdateien enthalten lokale Dateipfade und gehören normalerweise
nicht in ein öffentliches Repository.

## Entwicklung

Voraussetzung ist Python 3.11 oder neuer. Für eine Entwicklungsumgebung:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Die grafische Anwendung startet über `run_storyboard.pyw`.

```powershell
.\.build-venv\Scripts\python.exe -m compileall -q src
.\.build-venv\Scripts\python.exe -m ruff check --select F src tests
.\.build-venv\Scripts\python.exe -m pytest -q
```

## Lizenz, Datenschutz und Drittkomponenten

Der eigene YiF-Quellcode steht unter der [MIT-Lizenz](LICENSE), Copyright © 2026
Simon Gaschler. Hinweise zu gebündelten Komponenten stehen in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) und
[LICENSE_REVIEW.md](LICENSE_REVIEW.md). Sicherheitsmeldungen behandelt
[SECURITY.md](SECURITY.md).

Die Freigabeschritte für eine öffentliche Prototype-Version sind in
[PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md) zusammengefasst.

