# Öffentliche Prototype-Veröffentlichung – Freigabekriterien

Diese Liste beschreibt die Mindestschritte vor einer öffentlichen
Prototype-Version. Sie ist ein technischer Organisationsleitfaden und keine
Rechtsberatung.

## Quellcode und Datenschutz

- [ ] Öffentlichen Quellordner aus einem sauberen Export erzeugen – niemals den
  persönlichen Arbeitsordner ungeprüft veröffentlichen.
- [ ] Sicherstellen, dass keine Projekte, Fotos, Videos, Datenbankdateien,
  Thumbnails, Logs, lokale Pfade oder Zugangsdaten enthalten sind.
- [ ] `.gitignore` prüfen und einen letzten Secret-Scan ausführen.
- [ ] `PRIVACY.md` und `SECURITY.md` für den gewählten Veröffentlichungsweg
  aktualisieren; insbesondere den echten Sicherheitskontakt ergänzen.

## Lizenz und Drittkomponenten

- [ ] MIT-Lizenz und Copyright-Angabe prüfen.
- [ ] `THIRD_PARTY_NOTICES.md` und `LICENSE_REVIEW.md` für den tatsächlichen
  Build aktualisieren.
- [ ] FFmpeg-Build, Lizenzdatei, Notice und Herkunft/Hash gegen den Installer
  abgleichen.
- [ ] Modellherkunft und Lizenz der tatsächlich gebündelten Modelle prüfen.

## Technische Abnahme

- [ ] Tests, Linting und Kompilierung ausführen.
- [ ] Installer auf einem unabhängigen Windows-Benutzerkonto installieren und
  Deinstallation prüfen.
- [ ] JPG/XMP-Import, digiKam-Import, Augenkorrektur, regulären Export und
  Zeitraffer testen.
- [ ] Prüfsumme des Installers erstellen und in den Release Notes veröffentlichen.

## Veröffentlichung

- [ ] GitHub-Repository zunächst als privates Release-Draft prüfen.
- [ ] Release als **Pre-release / Prototype** markieren.
- [ ] Bekannte Einschränkungen, fehlende Code-Signatur und Supportumfang offen
  benennen.
- [ ] Erst nach dieser Abnahme das Repository und die Release-Datei öffentlich
  schalten.

