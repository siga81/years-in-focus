# Änderungsprotokoll

Dieses Protokoll trennt unveröffentlichte Änderungen im Arbeitsordner von den
versionierten Release-Ständen von **Years in Focus**.

## 0.1.5 – 6. Oktober 2026

Windows Pre-release. Quellcode und Installer werden gemeinsam als v0.1.5
bereitgestellt; offene Abnahmepunkte stehen in den Release Notes.

- Optional steuerbare Randüberblendungen, robustere EXIF-Aufnahmedaten und
  lokalisierte Datumsverarbeitung; die Augenkorrektur merkt sich ihre Fenstergröße
  und zeigt zurückhaltendere Augenpunkte. Die Daueranzeige wurde nachgeführt.
- Deutsche/englische Kurzanleitung erklärt Filmprobe, Augenprüfung, gespeicherte
  Ansichtseinstellungen und Projektumzüge sowie die aktuellen Tab-Zuständigkeiten.
- Strg+Mausrad in der Augenkorrektur zoomt am Mauszeiger und erhält den
  darunterliegenden Bildpunkt sowie bereits verschobene Ansichten.
- Augenkorrektur zeichnet Augenringe/Linie in konstanten Fensterpixeln nach der
  Bildskalierung, mit kontrastierender Kontur und konstantem Greifbereich.
  „Übernehmen und zurück“ navigiert zur vorherigen aktiven Karte.
  Dialogaktionen sind gruppiert: Zoom links, Automatik mittig, Navigation und
  „Übernehmen und Schließen“ rechts.
- Manueller Filmprobe-Übergang nutzt vorbereitete Float-Bildebenen direkt im
  Fenster. Reglerbewegungen werden auf den neuesten Wert zusammengefasst,
  ohne erneute Bildvorbereitung oder Worker-Rundlauf.
- Karten-Filmprobe mit vollständigem Stapel, globaler Normalisierung und
  gemeinsamer Exportauswahl einschließlich Zeitraffer-Regeln. Wiedergabe/Pause,
  Zeitleiste, manuelle Überblendung, Fortschritt und begrenzte Bild-Caches;
  ohne Musik/Folien, Videoexport oder Projektänderung.
- Kartenansicht-Seitenwechsel beginnt nach dem Rasteraufbau wieder oben,
  unabhängig vom aktiven Filter und ohne einen alten Scrollanker zu übernehmen.
- Kartengröße, Filterkategorien und Sortieransicht werden projektbezogen gespeichert
  und beim Öffnen wiederhergestellt; alte Projekte behalten die bisherigen Defaults.
- Aktivieren/Deaktivieren aktualisiert bei unveränderter Filterzugehörigkeit nur
  die Karte. Nötige Raster-Neuaufbauten erhalten eine überlebende Karte samt
  Pixelabstand als Scrollanker, einschließlich ihrer aktuellen Rasterseite.
- Bilddetails im Storyboard zeigen Auflösung (EXIF-orientiert) und Dateigröße
  des ausgewählten Originalbilds, mit Hinweis bei fehlender Originaldatei.
- Neue Importe verwenden DateTimeOriginal oder DateTimeDigitized und speichern
  die Datumquelle. DateTime entfällt als Fallback; Altanalysen bleiben unverändert.
- Projektinterne Analysepfade werden relativ gespeichert. Verschobene ältere
  Projekte erkennen passende Datenordner automatisch; fehlende Analysedaten
  erhalten eine eigene Meldung und einen Ordnersuchdialog.
- Karten werden beim Stapel-Export einzeln vorbereitet. Ein unbegrenzter Stapel
  speichert eine zusammengesetzte Fläche, begrenzte Stapel nur die benötigten
  Karten. Der Speicherbedarf hängt damit nicht mehr von sämtlichen Bildern ab.
- Auch die paketierte Vorschau erhält Kartennummern und Dateinamen, wenn aktiviert.
- Wiederverknüpfung prüft EXIF-orientierte Abmessungen. MWG-Gesichtsregionen werden
  in der Vorschau an derselben Position wie in der Analyse dargestellt.
- Nachimporte und manuelle Regionenänderungen berücksichtigen die MediaPipe-
  Kopfpose. Qualitätswarnungen verwenden die bereits geladenen Analysedaten.
- Projektdateien werden über eine temporäre Datei atomar ersetzt; ein Fehler
  beim Ersetzen lässt die bisherige Projektdatei bestehen. Dies ist keine
  gemeinsame Transaktion für Projekt, Analyse und Regionsdatei.
- Regressionstests und Entwicklungs-, Architektur-, Roadmap- und Release-Dokumente
  wurden an den tatsächlichen Quellstand angepasst.

## 0.1.4 – 16. August 2026

- Das Storyboard wurde optisch weiter vereinheitlicht: ruhigerer Kopfbereich,
  kompaktere Steuerungen, klarere Bereichstitel und besser nutzbare Scrollbereiche
  bei kleinen Fenstern.
- Die Augenkorrektur lässt sich über Karte oder Bildvorschau öffnen. Sie bietet eine
  zentrierte, zoombare Detailansicht und speichert bewusst übernommene Korrekturen
  nur im jeweiligen Projekt.
- Die Auswahl berücksichtigt sichtbare Qualitätsstufen und die maximale
  Seitenansicht konsistent. Die gewünschte Bildzahl bezieht sich direkt auf die
  aktuell passenden Bilder; widersprüchliche Doppelanzeigen wurden entfernt.
- Der Film-Tab bietet zusätzlich einen Zeitraffer-Modus mit Frames je Bild,
  Überblendung, Jahreslimit und optionaler Begrenzung auf frontal geeignete Bilder.
- Neue Projekte verwenden die Endung `.yif.json`; ältere `.facemovie.json`-Projekte
  und bisherige lokale Einstellungen bleiben lesbar.
- Neue Windows-Builds heißen `YearsInFocus.exe` und `YearsInFocusCLI.exe`.
- Kurzanleitung, strukturierteres Bilder-Menü und ein Ko-fi-Link im Über-Dialog
  erleichtern den Einstieg und die Unterstützung des Projekts.

## 0.1.3 – 12. August 2026

- Vorschauen übernehmen nun immer das Seitenverhältnis des final gewählten
  Videoformats. Hochkant- und quadratische Filme erhalten damit auch eine echte
  Hochkant- beziehungsweise quadratische Vorschau; 480p, 720p und 1080p bleiben
  dabei als unabhängige Vorschau-Größenstufen verfügbar.
- Die geschätzte Filmlänge steht nun zusätzlich gut sichtbar im festen Kopfbereich
  neben der Kartenübersicht. Sie aktualisiert sich mit Kartenauswahl, Standzeit,
  Überblendung sowie Start- und Endfolien und lässt sich damit direkt mit der
  Musiklaufzeit vergleichen.
- Die automatische zeitliche Auswahl kann optional gelbe **Grenzfälle** zusätzlich
  berücksichtigen. Standard bleibt die konservative Auswahl nur technisch geeigneter
  Bilder; rote, ungeeignete Karten bleiben stets ausgeschlossen. Die Auswahl richtet
  sich dabei strikt nach der sichtbaren Ampelfarbe, nicht nach dem breiteren
  internen Analyse-Status `review`.
- Der Windows-Installer bringt nun FFmpeg und ffprobe als geprüften LGPLv3-Build
  mitsamt Lizenzdatei mit. Hintergrundmusik, Laufzeitmessung für MP3 & Co. sowie
  optionale Qualitätsprofile funktionieren damit ohne separate Nutzerinstallation.

## 0.1.2 – 12. August 2026

- Die Tabs wurden weiter entzerrt: **Allgemein** enthält Ausgabeformat und Bildrate,
  **Storyboard** trennt Bildauswahl deutlich von der Serienbildlogik, während Film,
  Audio & Folien sowie Export ihre klaren Zuständigkeiten behalten.
- Ausgabe-Presets ergänzen 480p, 720p, 1080p und 4K um Hochkant (1080 × 1920) sowie
  quadratisch (1080 × 1080). Über **Ansicht → Erweiterte Ausgabeoptionen** können
  erfahrene Nutzer zusätzlich „höhere Qualität“ oder „kleinere Datei“ wählen.
  Der bewährte Standardexport bleibt unverändert aktiv, solange der Expertenmodus
  ausgeschaltet ist.
- Der Export-Tab fasst vor dem finalen Start nun Zielformat, Bildrate,
  Qualitätsprofil, Bildanzahl, vorhandene Start-/Endfolien, Musik und geschätzte
  Filmdauer zusammen. Die schneller gedachte Vorschau steht als klar getrennte,
  optionale Kontrolle darunter.

- Optionale Start- und Endfolien können als fertige JPG/JPEG- oder PNG-Bilder
  gewählt werden. Sie werden proportional und ohne
  Gesichtsanalyse angezeigt, in die Laufzeitschätzung aufgenommen und damit
  auch durch die Hintergrundmusik-Schleife abgedeckt. Fehlende Folienbilder
  verhindern den Export mit einer verständlichen Meldung.
- Start- und Endfolien schließen nun auch an den schwarzen Videorahmen weich an:
  die Startfolie blendet ein, die Endfolie blendet innerhalb ihrer gewählten
  Standzeit aus. Die vorhandene Überblendungsdauer bestimmt dabei das Tempo.
- Die Standzeit von Start- und Endfolien lässt sich nun einheitlich zwischen
  einer und acht Sekunden einstellen. Die Vorschauauflösung ist unabhängig vom
  Zielvideo wählbar (480p, 720p oder 1080p), damit schnelle Kontrollausgaben
  nicht unnötig groß werden.
- Der seitliche Arbeitsbereich kann nicht mehr versehentlich auf eine unbrauchbare
  Breite gezogen werden und belegt maximal etwa die halbe Fensterbreite. Über den
  Menüpunkt **Ansicht → Arbeitsbereich rechts anzeigen** lässt er sich vollständig
  ein- und wieder ausklappen.
- Startfolie geht nun mit der eingestellten Überblendungsdauer in die erste Karte
  über; die letzte sichtbare Karte blendet ebenso weich in die Endfolie. Die
  zusätzliche Endüberblendung wird in der Laufzeitprognose berücksichtigt.
- Die Sprachwahl speichert auch eine unmittelbare Rückkehr zur aktuell sichtbaren
  Sprache zuverlässig: Die zuletzt gewählte Sprache gewinnt beim nächsten Start.
- Hintergrundmusik kann nun als geordnete Wiedergabeliste mit bis zu zehn lokalen
  Dateien gewählt werden. Titel können per Drag & Drop umsortiert oder einzeln
  entfernt werden; YiF zeigt die Gesamtlaufzeit, wiederholt die komplette Liste
  bei Bedarf und blendet erst am Filmende aus.
- Die rechte Arbeitsseite ist als erster Layoutentwurf in die Tabs **Allgemein**,
  **Storyboard**, **Film**, **Audio & Folien** und **Export** gegliedert.
  Auflösung und Bildrate stehen bewusst vor der Kartenauswahl; der Export-Tab
  bündelt Vorschau und finalen Export. Bestehende Einstellungen wurden nur
  umsortiert und bleiben unverändert projektbezogen gespeichert.
- Projekte mit verschobenen Originalbildern melden den Rettungsfall beim Öffnen.
  Einzelne rote Karten lassen sich per Rechtsklick wiederverknüpfen; ein
  Sammelassistent durchsucht einen ausdrücklich gewählten neuen Stammordner im
  Hintergrund. Nur eindeutige Dateinamen mit passenden gespeicherten Bildmaßen
  werden nach einer sichtbaren Bestätigung übernommen. Auswahl, Reihenfolge,
  Regionen und Einstellungen bleiben dabei erhalten; YiF legt vorher eine
  `.before-relink.bak`-Sicherung der Projektdatei an.
 Beim Wiederverknüpfen einer einzelnen Karte nennt der Dateidialog das fehlende
 Original ausdrücklich und trägt dessen Namen vor. Wird die gleichnamige Datei
 am neuen Ort gewählt, übernimmt YiF den Pfad ohne die verwirrende A-gegen-A-
 Bestätigungsfrage.
- Beim Videoexport darf eine bereits vorhandene Zieldatei nach einer eindeutigen
  Nachfrage ersetzt werden. YiF rendert zunächst in eine temporäre Datei und tauscht
  das vorhandene Video erst nach erfolgreichem Export aus; bei Fehler oder Abbruch
  bleibt die frühere Datei erhalten.
- Sind Originalbilder während einer geöffneten Sitzung verschoben worden, prüft YiF
  dies vor dem Export. Statt eines technischen Fehlers wird der Export nicht
  gestartet und die Wiederverknüpfung der fehlenden Bilder angeboten.
- Der Audio-Fortschritt verwendet nun einen protokollstabilen, sprachneutralen
  Phasenwert und wird in der Oberfläche korrekt als „Hintergrundmusik hinzufügen“
  beziehungsweise „Adding background music“ angezeigt.
- Auch ältere deutsch gespeicherte Hinweise zu zeitlich nahen Serienaufnahmen
  erscheinen in der englischen Oberfläche übersetzt.
- Die Bildvorschau öffnet per Doppelklick das jeweilige Originalbild; per Rechtsklick
  lassen sich Originalbild oder sein Explorer-Ordner öffnen. Der überflüssige Button
  „Markierungen fertigstellen“ wurde aus dem Markierungsdialog entfernt.
- Das Bild in der separaten Bildvorschau passt sich nach einer kurzen, unmerklichen
  Verzögerung proportional an die aktuelle Fenstergröße an. Das Neuberechnen läuft
  im Hintergrund und begrenzt sehr große Vorschauen bewusst auf eine sinnvolle Größe.
- Die Bildvorschau ist ein reguläres Windows-Fenster: Sie kann über Windows-11-
  Snap-Layouts angedockt werden und bleibt nicht mehr zwangsläufig über dem Hauptfenster.
- Der Über-Dialog zeigt das YiF-Logo nun groß und zentral statt lediglich als kleines
  Begleitsymbol neben dem Text.
- Optional kann eine lokale Hintergrundmusik gewählt werden (MP3, WAV, M4A/AAC,
  FLAC, OGG). Beim Export wird sie bei Bedarf wiederholt und in den letzten drei
  Sekunden des Films ausgeblendet; die fertige MP4 erhält eine AAC-Tonspur.
 Der Audio-Tab zeigt für verfügbare Musikdateien ihre lokal ermittelte Laufzeit
 und erklärt das Wiederholen beziehungsweise Ausblenden. Verschobene oder
 gelöschte Musikdateien werden dort und vor dem Export verständlich gemeldet;
 eine Ersatzdatei kann direkt ausgewählt werden.
- Optionale Jahreslinien im Kartenraster: Bei Datumssortierung wird jedes neue
  Aufnahmejahr mit einem dezenten Vollbreiten-Trenner markiert. Die Einstellung
  liegt unter **Ansicht**, ist projektbezogen gespeichert und hat keinen Einfluss
  auf Reihenfolge, Bildauswahl oder Videoexport.
- Beim Scrollen bleibt das aktuelle Aufnahmejahr dezent als Kontextmarke sichtbar,
  bis der nächste Jahresabschnitt erreicht wird. Mausrad-Ereignisse in offenen
  Dialogen (etwa bei der digiKam-Personenauswahl) bewegen nicht mehr das
  Kartenraster im Hintergrund.

## 0.1.1 – 9. August 2026

Erster stabiler Windows-Installer nach dem V1.1-Markierungs- und Projektpflege-Test.

- Manuelle Hauptpersonenmarkierung für JPG/JPEG-Bilder ohne verwertbare
  XMP-Gesichtsregion: Vorschlagsrahmen lokal prüfen, Gesicht anklicken oder
  selbst ein Rechteck ziehen.
- Gemischte Ordner werden unterstützt: vorhandene XMP-Regionen bleiben erhalten;
  nur fehlende Zielregionen können direkt manuell ergänzt werden.
- Einzelbildkorrektur einer Gesichtsmarkierung über die Bildvorschau.
- Nachimport in geöffnete Projekte erkennt bereits vorhandene Originalpfade und
  analysiert nur neue Bilder. Bestehende Auswahl und Reihenfolge bleiben erhalten.
- Karten können per Rechtsklick projektlokal entfernt werden; Originalbilder und
  eingebettete Metadaten werden nie gelöscht.
- Schutz vor versehentlichem Datenverlust beim Beenden, beim Öffnen eines anderen
  Projekts und beim Anlegen eines neuen Projekts.
- Projektmenü mit bis zu fünf zuletzt verwendeten Projektdateien.
- Englische Übersetzungen für die üblichen kartenbezogenen Qualitätswarnungen.
- Neue Projekte zeigen die Gesichtsmarkierung in der großen Bildvorschau standardmäßig.
- Installer: 64-Bit-Inno-Setup-Ausgabe mit Startmenü, optionalem Desktop-Symbol und
  Deinstallation.

**Prüfstand:** 10 automatisierte Tests erfolgreich; manuelle Tests für Import,
Kartenpflege, Projektöffnung sowie Vorschau- und Videoexport erfolgreich.

## 0.1.0 – 6. August 2026

Erster installierbarer Windows-Teststand mit Storyboard, XMP-/digiKam-Import,
global ausgerichtetem Kartenstapel-Export, Qualitätsanzeige, Filterung und
Thumbnail-Cache.
