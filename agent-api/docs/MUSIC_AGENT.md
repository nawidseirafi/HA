# Musiklicht V1

Stand: 2026-10-15. Implementierung und lokale Prüfung; noch kein Test mit echten Lampen/iPad.

## Architektur

`/wall` analysiert Mikrofon-Audio lokal mit Web Audio. Nur Bass, Mitten, Höhen,
Pegel und Beat verlassen den Browser, maximal 20 Nachrichten/s. Keine Aufzeichnung,
kein MediaRecorder, keine Audiodateien, keine Übertragung an LLMs.

Steve entdeckt `backend/agents/music/manifest.yaml`. Start/Stop/Konfiguration laufen
über den bestehenden Agent-Control-Vertrag. Ein authentifizierter WebSocket vermittelt
Kennwerte an den separaten Worker `python -m backend.agents.music.runtime`.
Dieser startet weder HomeHub noch Telegram oder andere Agenten.
Unix-Socket `data/music/runtime.sock`, Verzeichnis 0700, gleicher Dienstbenutzer wie Steve.
Kein öffentlicher Worker-Port. Der lokale Benutzer ist die Vertrauensgrenze.

Pure Engine: `engine.py`; Sitzungs-/Stoplogik: `session.py`; HA-Ausgabe:
`backends/home_assistant.py`, über vorhandenen HomeAssistantService.
Entertainment ist nur als spätere Backend-Erweiterung vorgesehen.

## Bedienung

Wall → Musiklicht. Einzelne dimmbare Lampen auswählen, Player und Profil wählen,
Auswahl speichern, Musik am Player abspielen, „Musiklicht starten“ antippen.
Erst der Klick fordert das Mikrofon an. Ein Agentenstart allein aktiviert kein Mikrofon.
Nicht dimmbare Lampen und HA-Lichtgruppen sind in V1 nicht auswählbar.
Profile: Ruhig, Dynamisch, Party; alle ohne Stroboskop-Effekte.
Stop bleibt auf Wall erreichbar. Sonos/Media-Player-Pause stoppt die Show.

## Ausfallsicherheit

Ein Besitzer, ein Worker (Dateisperre), kein automatischer Neustart einer Show.
Journal vor erster Änderung unter `data/music/journal.json`, Einstellungen in
`settings.json`; Dateien atomar geschrieben und fsync. Beide ins Backup aufnehmen.
Vollständiger Snapshot ist Startvoraussetzung. Leere Auswahl verweigert Start.
Watchdog: 12 Sekunden bis erste Audiodaten, danach 3 Sekunden ohne gültige Daten.
HA-/Player-Ausfall stoppt die Ausgabe. Stop sperrt sofort neue Befehle; bereits
laufende HA-Aufrufe können bis zu ihrem Timeout dauern. Wiederherstellung danach.
Ein beendeter Worker hinterlässt offene Einträge zur ausdrücklich ausgelösten Recovery.
Nach mehr als fünf Minuten werden alte Zustände nicht mehr auf Geräte zurückgespielt.
Geänderte Lampen werden bei Recovery nicht überschrieben.

Manuelle Wall-Schaltungen passieren eine Worker-Barriere: betroffene Lampen verlassen
die Sitzung vor dem Schalten. Änderungen außerhalb Steve werden vor dem nächsten
Effekt konservativ anhand Zustand/Helligkeit/Farbe erkannt. Das ist keine perfekte
Urhebererkennung; identische Änderungen sind nicht unterscheidbar.

Global maximal zwei Effektbefehle/s, Round-Robin über ausgewählte Lampen. Viele Lampen
bedeuten entsprechend langsamere Reaktion. Keine Zusage einer taktgenauen Lichtshow.

## Anmeldung / HTTPS

Bestehender Bearer-Login → kurzlebiges, einmaliges Ticket → erste WSS-Nachricht.
Keine Tokens in URLs; Origin-Prüfung; begrenzte Nachrichtengröße und Rate; erneute
Token-/Anwesenheitsprüfung während der Sitzung. Beobachtungsmodus blockiert Ausgabe.
`MUSIC_ALLOWED_ORIGIN=https://ai-agent.local` im Steve-Dienst setzen. Alternativ wird
ROBOTERSTEVE_PASSKEY_ORIGIN verwendet, sonst HTTPS mit identischem Host verlangt.
Für lokale Entwicklung Origin ausdrücklich setzen; produktiv nur HTTPS/WSS.
Zertifikatswarnung vor Mikrofontest beheben: siehe `passkeys-ipad.md`.

## Installation / Updates

Nicht auf HA OS installieren; Worker läuft auf Steves Debian-Mini-PC.
1. Bestehende Deployment-Pfade und Dienstbenutzer prüfen.
2. `music-agent.service` an diese Pfade/Benutzer anpassen. Auf dem Server
   `Environment="HA_URL=..."` und `Environment="HA_TOKEN=..."` mit denselben
   Werten wie in `agent-api.service` ergänzen. Keine Zugangsdaten einchecken.
3. Unit nach `/etc/systemd/system/music-agent.service` installieren.
4. `systemctl daemon-reload`, danach `systemctl enable --now music-agent`.
5. Steve neu starten; Worker-Status auf Wall prüfen.

`PartOf=agent-api.service` koppelt Stop/Restart an Steve. Bei einem Update Show zuerst
stoppen und Wiederherstellung abwarten. Während laufender Show kein Update ausführen.
Bei Rollback beide Dienste auf denselben Code-Stand zurücksetzen. Persistente Daten
nicht überschreiben. Kein HA-Token oder Benutzerpasswort in Dienstvorlagen eintragen.

## Abnahme

Automatisierte Tests mit Fake-Backend, ohne Netzwerk: Auswahlvalidierung, deterministische
Engine, Snapshotfehler, Rate, Sequenzvalidierung, Stop, manuelle Übernahme, Player-Pause,
Watchdog und Recovery. Frontend-Typecheck/Build und bestehende Agent-Control-Tests.
Danach auf iPad: HTTPS ohne Warnung, Mikrofon ablehnen/erlauben, Profil, Bildschirmwechsel,
Abmelden, Sperren, Verbindungsausfall; zuerst eine ausdrücklich ausgewählte Testlampe.

## Implementierungsstand und Grenzen

- Wall-Navigation und Startseiten-Kachel führen zur Musikseite; direkter Link:
  `/wall?section=music`. Agentenkarte/Agent Map verlinken ebenfalls dorthin.
- Auswahl wird nach Etage/Raum aus dem vorhandenen HomeHub-Inventar gruppiert.
  Maximal 50 einzelne dimmbare Lampen; Hue-/HA-Gruppen ausgeschlossen, soweit als
  Gruppe gemeldet. Nur gespeicherte Auswahl wird verwendet, keine automatische Erweiterung.
- Profil, Intensität und Geräteauswahl werden in V1 vor dem Start gespeichert.
  Zum Ändern eine laufende Show zuerst stoppen. `run` unterstützt `configure` und `recover`.
- Navigation innerhalb Wall erhält die Mikrofonsitzung. Verlassen von Wall, verborgenes
  Dokument, Mikrofonverlust oder Authentifizierungsverlust schließt die Audioverbindung.
- Globale Rate gilt auch für Wiederherstellungsbefehle. Eine Recovery-Runde ist zeitlich
  begrenzt; verbleibende Einträge bleiben sichtbar und können erneut geprüft werden.
- Manuelle Übernahme über den Wall-Service-Endpunkt ist synchronisiert. HA-Taster und
  andere Automationen können nur anhand beobachteter Zustandsabweichungen erkannt werden;
  absolut konfliktfreies Schalten außerhalb dieses Endpunkts wird nicht zugesichert.
- Wenn der Worker bei offenen Besitz-/Recovery-Einträgen nicht erreichbar ist, wird eine
  konkurrierende Wall-Schaltung mit Fehler abgelehnt. Zuerst Worker wiederherstellen.
- Der Update-Service verweigert Installation bei offenem Musik-Journal. Während eines
  Updates keine neue Sitzung starten. systemd-PartOf koppelt Worker-Restarts an Steve.
- Die vorhandene `agent-api.service` enthält bereits lokale Geheimnisse. Sie wurde nicht
  verändert. Vor Verteilung eines Deployment-Pakets die vorhandene Vorlage bereinigen
  und echte Zugangsdaten in die externe EnvironmentFile verschieben; der bestehende
  Builder kopiert diese Datei weiterhin. Kein Release-Paket wurde hier erstellt.

## Geänderte Integrationspunkte

`backend/api/homeassistant_routes.py`: manuelle Übernahme vor Licht-Serviceaufrufen.
`backend/services/update_service.py`: Update-Sperre bei offenem Licht-Journal.
`deployment_build.py`: Music-Dienstvorlage im Paket.
`frontend/src/apps/personal/pages/WallDashboardPage.tsx`: Menü, Kachel, Musikseite und Stop.
`frontend/src/apps/personal/App.tsx`, `routes/routes.ts`, `AgentsPage.tsx`, `AgentMap.tsx`:
Music-Verlinkung. `frontend/src/shared/api/client.ts`: API-URL für WSS wiederverwenden.
`frontend/vite.config.ts`: WebSocket-Proxy. `requirements.txt`: explizite HTTPX-,
Pydantic-2- und AnyIO-Abhängigkeiten. `frontend/package.json`: `test:music`.

## Lokale Prüfbefehle

Im Verzeichnis `agent-api`, mit der zum Projekt gehörenden Python-Umgebung:

```sh
ROBOTERSTEVE_DATA_DIR=/tmp/steve-music-test-data .venv/bin/python -m pytest \
  tests/test_music.py tests/test_music_api.py tests/test_agent_control.py \
  tests/test_orchestrator_map.py tests/test_wall_calendar.py -q
npm run test:music --prefix frontend
npm run build --prefix frontend
```

Update-Tests getrennt in einem frischen Prozess ausführen und geerbte `UPDATE_*`-
Variablen entfernen: lokale Deployment-Einstellungen überschreiben sonst Test-Fixtures.
Ein kombinierter Lauf zeigte dadurch zehn Fehler; isoliert bestanden alle 20 Update-Tests.

Browser-/iPad-Sichtprüfung ist noch offen: In dieser Entwicklungsumgebung war kein
Browser für UI-Automation verbunden. Eine lokale Vorschau mit Fake-API wurde vorbereitet
und wieder beendet, ohne reale HA-Verbindung. Kein Mikrofon, keine echten Lampen und
kein produktiver systemd-Dienst wurden bei der Entwicklung angesprochen.

### Prüfergebnis dieser Umsetzung

- 37 Python-Tests für Music-Engine, Lifecycle, WebSocket, Runtime, manuelle Wall-
  Übernahme, Update-Sperre und bestehende Agent-Control-/Orchestrator-/Wall-Funktionen: bestanden.
- 20 bestehende Update-Tests separat mit bereinigten `UPDATE_*`-Umgebungsvariablen: bestanden.
- 3 Node-Tests der Audioanalyse (Stille, Frequenzbänder/Wertebereich, Cleanup): bestanden.
- TypeScript-Prüfung und Vite-Produktionsbuild: bestanden. Vite meldet große Bundles;
  bestehende Bibliotheken melden Deprecations. Keine neuen Testfehler verblieben.
- `git diff --check`: ohne Fehler.
- Keine Bereitstellung auf dem Mini-PC. Kein Test mit echten Lampen oder iPad-Mikrofon.

## Korrektur Agent Map (2026-10-16)

Musiklicht erhielt vorher eine überlappende Fallback-Position und ein Blitz-Symbol.
Die Map verwendet jetzt das Music-Symbol und ein deterministisches Reihenlayout mit
maximal vier Fachagenten pro Reihe; weitere Agenten erhalten eigene Plätze.
Die Backend-Map liefert `orchestrator → music` und `music → homeassistant`.
Keine fiktive Scheduler-/OpenAI-/Datenbank-Verbindung: V1 ist manuell gestartet,
deterministisch und speichert sein Journal als JSON-Dateien.
Neue nicht zeitgesteuerte Agenten erhalten grundsätzlich eine Orchestrator-Verbindung.
Regressionstests prüfen Beziehungen, Musik-Symbol, Überlappungsfreiheit und stabile
Positionen bei geänderter API-Reihenfolge.

Prüfergebnis der Map-Korrektur: zwei Backend-Map-Tests und zwei Layout-Tests bestanden;
TypeScript/Vite-Build und `git diff --check` erfolgreich. Noch keine visuelle Prüfung
auf dem iPad und keine Bereitstellung auf dem Mini-PC.

### DJ-Studio-Oberfläche (2026-10-16)

Die Musikseite unter `/wall?section=music` verwendet jetzt eine eigenständige dunkle
Studio-Oberfläche mit Cyan-, Violett- und Pink-Akzenten, großer Frequenzanzeige,
Profilkarten (Ambient, Dynamic, Party) und einer hervorgehobenen Start-/Stopp-Leiste.
Die Lampenauswahl bleibt nach Etage und Raum gruppiert. Die Darstellung passt sich
an schmale Bildschirme an; Bedienelemente sind mindestens 48 px hoch und haben
sichtbare Tastatur-Fokusringe. Reduzierte Bewegung deaktiviert Übergänge und senkt
die Aktualisierungsrate der Anzeige.

Geänderte Integrationspunkte:
- `frontend/src/apps/personal/components/wall/WallMusicSection.tsx`: Studio, Profile, Transport und lokaler Equalizer.
- `frontend/src/apps/personal/components/wall/wall-music.css`: dunkle Studio-Gestaltung und responsive Touch-Bedienung.
- `frontend/src/apps/personal/features/music/audioAnalyzer.ts`: 48 logarithmische lokale Frequenzbänder zwischen 40 Hz und 12 kHz.
- `frontend/src/apps/personal/features/music/useMusicSession.ts`: Frequenzwerte in einer React-Ref; keine zusätzlichen Wall-Renders pro Audioframe.

Die Frequenzbänder werden ausschließlich lokal angezeigt. Das WebSocket-Protokoll
überträgt weiterhin nur die bisherigen aggregierten Features. Ohne aktive
Mikrofonsitzung zeigt der Equalizer eine ruhende Grundlinie, keine simulierte Musik.
Mikrofonfreigabe, Startbedingungen, Wiederherstellung und Stopplogik bleiben erhalten.
Der Hinweis auf einen nicht erreichbaren Music-Dienst bleibt sichtbar; das Redesign
installiert oder startet keinen Dienst auf dem Mini-PC.

Validierung: TypeScript-/Vite-Produktionsbuild und die Audioanalyse-Tests.
Eine visuelle Prüfung in iPad Safari und ein Test mit echten Lampen stehen aus.
Keine neuen Abhängigkeiten.

### Übersichtliche Lichtbühne (2026-10-16)

Die zuvor vollständig aufgeklappte Lampenliste wurde durch kompakte Raumkarten
ersetzt. Jede Karte zeigt Raum, Etage und den aktuellen Auswahlzähler. Über
„Raum auswählen“ werden nur die auswählbaren Lampen dieses Raums ergänzt;
„Raum abwählen“ entfernt die Auswahl des Raums. Einzelne Lampen sind über ein
natives, per Tastatur bedienbares Details-Element erreichbar. Die Etagenfilterung
ändert keine bestehende Auswahl. Der Gesamtzähler zählt auch ausgewählte Lampen
anderer Etagen; nicht mehr vorhandene gespeicherte Lampen bleiben entfernbar.

Der globale Knopf zum Auswählen aller angezeigten Lampen entfällt zugunsten der
gezielten Raumauswahl. „Auswahl leeren“ bleibt verfügbar. Lampennamen erhalten
explizite helle Textfarben, damit globale Wall-Label-Stile sie nicht abdunkeln.
Desktop/iPad: zwei Raumkarten pro Zeile; schmale Ansichten: eine Karte pro Zeile.
Speichern, 50-Lampen-Limit und Sperre während einer Sitzung bleiben bestehen.

Dateien: `WallMusicSection.tsx` und `wall-music.css` unter
`frontend/src/apps/personal/components/wall/`.
Validierung: TypeScript-/Vite-Build. Sichtprüfung auf dem echten iPad steht aus.

### Lampenauswahl mit Wall-Schaltern (2026-10-16)

Die Checkboxen der Lichtbühne wurden durch die bereits in der Wall verwendeten
pillenförmigen `.wall-switch`-Schalter ersetzt. Die gesamte Lampenzeile ist ein
per Touch und Tastatur bedienbarer Button mit `aria-pressed`. Der Schalter zeigt
die Auswahl für die Lichtshow, nicht den tatsächlichen Einschaltzustand an.
Nicht mehr vorhandene Lampen können über dieselbe Darstellung abgewählt werden.
Die bestehende Sitzungssperre und Verfügbarkeitsprüfung bleiben erhalten.
Änderungen: `WallMusicSection.tsx`, `wall-music.css`. Prüfung: Produktionsbuild.

### Abgleich mit vorhandener agent-api.service (2026-10-16)

Die vorliegende Steve-Unit nutzt `/opt/roboterSteve` als WorkingDirectory und
`/opt/roboterSteve/venv/bin/uvicorn` als ausführbares Programm. HA_URL und HA_TOKEN
stehen dort als direkte Environment-Einträge; eine gemeinsame EnvironmentFile ist
nicht eingerichtet. Die Music-Unit erbt diese Variablen nicht durch PartOf.
Der Verweis auf `/etc/robotersteve-agent-api.env` ist daher weiterhin eine nicht
bereitgestellte Voraussetzung, kein Nachweis einer existierenden Datei.

Empfohlene Einrichtung: HA_URL und HA_TOKEN auf dem Server in eine geschützte
Konfigurationsdatei auslagern und diese aus beiden Units über EnvironmentFile
laden. Erst danach die bisherigen gleichnamigen Environment-Einträge entfernen.
Keine Geheimnisse in die Music-Unit oder die Dokumentation kopieren. Die laufende
Serverkonfiguration wurde bei diesem lokalen Abgleich nicht verändert.

### Korrektur der Dienstvorlage (2026-10-16)

Der Benutzer bestätigt: `/etc/robotersteve-agent-api.env` existiert nicht.
Der EnvironmentFile-Verweis wurde aus `music-agent.service` entfernt.
Die zuvor vorgeschlagene Auslagerung in eine gemeinsame Datei wird nicht
vorausgesetzt. Stattdessen folgt die Einrichtung den vorhandenen direkten
Environment-Einträgen: HA_URL und HA_TOKEN müssen auf dem Server auch für den
Music-Dienst gesetzt werden. Die Vorlage enthält nur einen entsprechenden
Kommentar, keine Geheimnisse. Ohne diese Einrichtung ist die Vorlage noch
nicht für die Lichtsteuerung betriebsbereit. Keine Serveränderung vorgenommen.

### Python-Abhängigkeiten beim systemd-Update (2026-10-16)

Der aktuelle ApplicationZipInstaller kopiert die Anwendungsdateien einschließlich
requirements.txt. Der lokale systemd-Updatepfad startet anschließend Steve neu,
führt aber kein pip install aus. Neue oder geänderte Python-Abhängigkeiten müssen
somit vor dem ersten Music-Start auf dem Mini-PC in der bestehenden Umgebung
installiert werden (nach Bereitstellung der neuen requirements.txt):

```sh
/opt/roboterSteve/venv/bin/python -m pip install -r /opt/roboterSteve/requirements.txt
/opt/roboterSteve/venv/bin/python -m pip check
```

Dies sind Server-Anweisungen; bei dieser Prüfung wurde keine Installation ausgeführt.
Auch die erstmalige Installation der music-agent.service in systemd erfolgt nicht
automatisch durch das Kopieren der Dienstvorlage im Anwendungspaket.

### Diagnose „HA nicht erreichbar“ (2026-10-16)

Beim lokalen Vergleich sind HA_URL und HA_TOKEN in beiden Dienstdateien vorhanden
und identisch (Werte nicht ausgegeben). Der gemeldete letzte Stopp `ha_error` wurde
bisher irreführend als Nichterreichbarkeit übersetzt. Tatsächlich erfasst dieser
Fehlerpfad auch Statusabfragen, Lichtberechnung, Journal-Schreibfehler und
abgelehnte Service-Aufrufe. Die tatsächliche Ursache auf dem Mini-PC ist noch offen.

Die Oberfläche nennt diesen Stopp nun „Fehler bei der Lichtsteuerung“. Eine neue
Diagnose enthält Arbeitsschritt, Exception-Klassen und ggf. HTTP-Statuscode; keine
Exception-Texte, URLs, Tokens oder Antwortinhalte. Sie wird im Worker-Journal
protokolliert und im Status angezeigt; sie bleibt auch nach Wiederherstellung
bis zum nächsten Start erhalten. Nach Deployment ist der Fehler erneut auszulösen,
um die neue Diagnose zu erhalten. Historische Stopps enthalten noch keine Details.
Validierung: Music-Backendtests und Frontend-Produktionsbuild.

### Vorzeitiger Stopp „Manuell übernommen“ (2026-10-16)

Ein reproduzierbarer Fehler im Zustandsvergleich führte dazu, dass unveränderte
Lampen mit `hs_color: null` als manuell verändert galten. Ausgeschaltete Lampen
konnten dadurch bereits vor dem ersten Lichtbefehl freigegeben werden. Ein
`brightness: null` konnte zudem einen Rechenfehler verursachen.

Korrektur in `backend/agents/music/session.py`: Bei übereinstimmendem Zustand
„off“ werden inaktive Helligkeits-/Farbattribute ignoriert. Nicht gesetzte
Sollattribute werden nicht verglichen; fehlende Ist-Helligkeit bei konkretem
Sollwert bleibt eine Abweichung. Nach einem erfolgreich gesendeten Befehl darf
HA maximal zwei Sekunden noch den vorherigen Zustand melden. Während dieser
Wartezeit werden keine weiteren Befehle an diese Lampe gesendet. Der Timeout
wird nicht verlängert. Andere Abweichungen führen weiterhin zur Freigabe;
explizites manuelles Schalten über die Wall wirkt weiterhin sofort.

Die Korrektur akzeptiert keine beliebigen Farbabweichungen. Ohne Rückmeldung des
echten Systems ist nicht bewiesen, dass jede dortige Abweichung hiermit behoben ist.
Ein Diagnosehinweis kennzeichnet verbleibende Abweichungen. Regressionstests decken
Nullwerte, Start und Wiederherstellung ausgeschalteter Lampen, verzögerte und
fehlende Rückmeldungen sowie explizite Freigabe ab. Music-Tests: 26 bestanden.
Nach Deployment muss der Music-Prozess den neuen Code laden; für diese Änderung
sind keine zusätzlichen Python-Pakete erforderlich. Realer Hue-Test steht aus.

### ConnectError beim Lampenstatus (2026-10-17)

Gemeldete Kette: RuntimeError → ConnectError → ConnectError → OSError.
Dies ist ein Transportfehler beim Lesen des Zustands, kein Beleg für falsche
Zugangsdaten und kein Fehler des Zustandsvergleichs. Die lokale Dienstvorlage
verwendet `http://homeassistant.local:8123`; mDNS-Auflösung ist eine mögliche,
noch nicht bestätigte Ursache. Laufende Server-Unit und Netzwerk wurden nicht
remote geprüft. Direkt auf dem Mini-PC ohne Token prüfen:

```sh
getent ahosts homeassistant.local
curl --noproxy '*' --connect-timeout 5 --max-time 10 -sS -o /dev/null -w 'HTTP %{http_code}\n' http://homeassistant.local:8123/api/
```

HTTP 401 ist bei diesem absichtlich unauthentifizierten Test ein erfolgreicher
Nachweis der HTTP-Erreichbarkeit; er prüft nicht den Token. Bei Fehlern denselben
Test mit der tatsächlichen LAN-IP von HA durchführen. IP-Erfolg bei Namensfehler
spricht für ein Auflösungs-/Adressauswahlproblem. Ein einmaliger Erfolg schließt
sporadische Verbindungsprobleme nicht aus. Keine erfundene IP in die Unit eintragen.
Die Diagnose ergänzt jetzt verfügbare OSError-Fehlercodes (z. B. ECONNREFUSED,
EAI_NONAME) ohne Exception-Texte oder Zugangsdaten. Regressionstest prüft dies.

### Aktive Sitzung ohne sichtbare Lichtänderung (2026-10-17)

Benutzer bestätigt bewegten Equalizer, aktive Sitzung und Einschalten einer Lampe,
aber keine weiteren sichtbaren Farb-/Helligkeitsänderungen. Die genaue Ursache auf
dem Gerät bleibt offen. Ein zusätzlicher reproduzierbarer Logikfehler wurde behoben:
20-Hz-Audioframes konnten Beat-Ereignisse überschreiben, bevor die begrenzte
Lichtschleife sie liest. Ein sitzungsbezogener Beat-Merker hält das Ereignis bis zur
nächsten Lichtberechnung. Mehrere Beats werden zusammengefasst; die Befehlsrate
bleibt unverändert. Es wird keine taktgenaue Ausgabe zugesichert.

Status enthält jetzt flüchtige Telemetrie: letzte Audiosequenz, Pegel/Bass,
Anzahl erfolgreich beantworteter Lichtbefehle und letzter Befehl. Die Wall zeigt
sie im aufklappbaren Bereich „Signal & Lichtausgabe“. Der Zähler bestätigt nur
den erfolgreichen HA-Service-Aufruf, nicht die physische Ausführung durch Hue.
Keine Rohdaten oder zusätzlichen Aufnahmen werden gespeichert. Beim Sitzungsstart
werden Zähler und Beat-Merker zurückgesetzt. Tests prüfen erhaltene Beats,
einmaligen Verbrauch und das Nichtzählen fehlgeschlagener Befehle.

Nächster Praxisschritt: Mit einer Lampe die Anzeige im Abstand einiger Sekunden
vergleichen. Steigende Sequenz ohne steigenden Befehlszähler grenzt den Fehler
auf die Ausgabeschleife ein; steigende Zähler mit wechselnden Sollwerten lenken
die Prüfung auf HA/Hue und etwaige konkurrierende Automationen. Neue Pakete sind
nicht erforderlich. Backend und Frontend müssen gemeinsam aktualisiert werden.

### Deutlichere Reaktion bei Raumlautstärke (2026-10-17)

Der Nutzer bestätigt den sichtbaren Farbwechsel von Ambient zu Party. HA/Hue
setzt somit Farbkommandos um. Bei gemeldeten Pegeln um 10 % und Bass um 18 %
führte die lineare Energieabbildung jedoch zu niedriger, wenig variierender
Helligkeit. Dynamic und Party verwenden jetzt die stetige Verstärkung
`1 - (1 - energy)^gain` (Gain 3 bzw. 4), ohne hartes Abschneiden normaler Pegel.
Die Glättung reagiert mit Faktor 0,55 bzw. 0,7 schneller; Beat-Akzente betragen
0,12 bzw. 0,18. Ambient behält seine bisherige Kennlinie und Glättung.

Beispiel bei konstant Bass 0,18 / Mitten 0,08 / Höhen 0,04, Intensität 100 %,
ohne Beat: Party nähert sich ca. 100/255 statt bisher 44/255 Helligkeit an.
Das Beispiel beschreibt die Berechnung, keine Messung an der echten Lampe.
Stille bleibt bei der bisherigen Mindesthelligkeit; Beat-Akzente greifen nicht
bei Energie unter 0,015. Helligkeit bleibt zwischen 20 und 200, Übergänge bei
mindestens 0,25 Sekunden und die globale Begrenzung bei zwei Befehlen pro Sekunde.
Kein Ein-/Ausschalt-Stroboskop und keine automatische Mikrofonkalibrierung.

Dateien: `backend/agents/music/engine.py`, `tests/test_music.py`.
Regressionstests prüfen niedrige Raumpegel, verbleibenden Dynamikbereich,
Beat-Kontrast, Ambient-Verhalten, Intensität und Ausgabegrenzen. Nach Deployment
Music-Dienst neu starten; keine zusätzlichen Pakete erforderlich. Die visuelle
Wirkung muss auf dem iPad mit der echten Lampe geprüft werden.

### Einstellungen automatisch speichern (2026-10-17)

Player, Profil, Intensität und Lampenauswahl werden in der Wall jetzt automatisch
350 ms nach der letzten Änderung gespeichert. Der bisherige Speicherknopf und der
Hinweis „Änderungen vor dem Start speichern“ entfallen. Schnelle Eingaben werden
zu einem Schreibvorgang zusammengefasst; während der Anfrage sind die Einstellungen
gesperrt. Der Start bleibt bei ungespeicherten Änderungen gesperrt. Erst nach
erfolgreicher Speicherung und Statusaktualisierung wird er wieder freigegeben.
Bei Fehlern bleiben die lokalen Änderungen erhalten; ein Fehlerhinweis und
„Erneut versuchen“ ermöglichen eine erneute Speicherung. Es gibt keine endlose
automatische Fehlerschleife. Über 50 Lampen wird nicht gespeichert. Während einer
laufenden Show bleiben Änderungen wie bisher gesperrt. Beim Verlassen der Seite
wird ein noch nicht gestarteter Speichertimer abgebrochen.

Datei: `frontend/src/apps/personal/components/wall/WallMusicSection.tsx`.
Prüfung: TypeScript-/Vite-Produktionsbuild. Keine neuen Abhängigkeiten oder
Backendänderungen erforderlich. Frühere Anleitungen zum manuellen Speichern
sind für diese Oberfläche damit überholt.
