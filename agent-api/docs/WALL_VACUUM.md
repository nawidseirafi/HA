# Saugroboter im Wall-Dashboard

Die Startansicht und die passende Raumansicht zeigen `WallVacuumCard`. Die vorhandene
Wall-API liefert `vacuums` aus den aktuellen HA-Zustaenden. Zusaetzliche Sensoren,
Karten und Bedienelemente werden ausschliesslich ueber die gemeinsame Device-ID
zugeordnet, nicht anhand aehnlicher Geraetenamen. Fehlende Zuordnungen bleiben leer.

## Darstellung

- HA-Status, Akku, Ladestatus, aktuelle Karte oder Raum.
- Reinigungsflaeche und -zeit, Fortschritt nur waehrend der Reinigung.
- Echte HA-Bildkarten mit ihrem eigenen Zeitstempel. Die Ansicht passt den sichtbaren
  Kartenausschnitt an transparente Bildraender an, ohne die Quelldatei zu veraendern.
- Karten-Tabs aendern nur die Anzeige, niemals die aktive Karte des Roboters.
- Saugstaerke, Wisch-Einstellungen, aktive Karte, Programme, Schalter und Pflegewerte
  stehen unter Reinigung & Pflege. Nur von HA gelieferte Optionen werden angeboten.

## Steuerung

### KI und Telegram

`vacuum_status` liefert dieselben strukturierten Roboter-, Sensor-, Karten- und
Programmdaten wie die Wall, aus dem zentralen Hub-Bestand mit Datenqualitaet und
Registry-Fehlern. Bei Saugroboter-/Roborock-Fragen wird die Abfrage vor der ersten
Modellantwort ausgefuehrt. Bei mehreren Robotern muss das Ziel eindeutig sein.

`propose_vacuum_action` unterstuetzt `start`, `pause`, `stop` und `return_to_base`.
Es speichert nur einen Vorschlag. Erst `/confirm <id>` desselben Nutzers innerhalb
von fuenf Minuten fuehrt ihn einmalig aus. Verbindung, Zielzustand und unterstuetzte
Funktion werden erneut geprueft; danach wird der HA-Zustand beobachtet. `returning`
bestaetigt nur die Rueckfahrt, nicht die Ankunft. Programme, Saugstaerke und andere
Einstellungen bleiben vorerst ausschliesslich in der Wall steuerbar.
Eine dauerhafte automatische Freigabe neuer Saugroboterregeln ist nicht vorgesehen.

### Steve denkt

Eine gemeinsame Auswertung erzeugt Hinweise fuer Reinigung, Pause, Rueckfahrt,
Fehler, Wasserknappheit und Nichterreichbarkeit. Der ContextService und die Wall
nutzen dieselbe Auswertung. Normaler Lade-/Standbybetrieb erzeugt keinen offenen Punkt.
Ein gemeldetes Reinigungsende wird nur fuer 30 Minuten angezeigt, gemessen am echten
Endzeit-Sensor, nicht am letzten Statusupdate. Es wird kein fehlerfreier Abschluss
behauptet. Fehler haben Vorrang vor Fortschritt oder Abschluss; Sicherheitsalarme
des Hauses bleiben wichtiger als Roboterhinweise. Es werden dadurch keine neuen
Telegram-Pushnachrichten oder automatischen Reinigungsauftraege eingerichtet.

`POST /api/homeassistant/vacuums/{entity_id}/command` prueft die aktuelle Verfuegbarkeit,
die unterstuetzten Funktionen und bei Nebeneinheiten die Device-Zuordnung. Es gibt
keinen freien `send_command`-Durchgriff. Programme starten erst durch den separaten
Startknopf; eine Auswahl allein startet nichts. Einstellungen/Programme, die eine
ruhende Maschine brauchen, sind auf docked/idle/paused begrenzt.

Auftragsannahme wird als `accepted` gemeldet, nicht als bereits ausgefuehrte Reinigung.
Fehler bleiben sichtbar. Die Wall laedt anschliessend den aktuellen HA-Zustand erneut.
Im globalen Beobachtungsmodus sind alle POST-Aktionen gesperrt.

## Karten und Datenschutz

`GET /api/homeassistant/vacuums/{entity_id}/maps/{image_id}` ist durch die bestehende
Anmeldung geschuetzt und prueft die Device-Zuordnung. Der Backend-Proxy ruft nur den
festen HA-Bildpfad auf, ohne Weiterleitungen; akzeptiert PNG/JPEG/WebP bis 8 MiB.
HA-Tokens und Entity-Bild-URLs werden nicht an den Browser weitergegeben. Der Browser
laedt das Bild authentifiziert als Blob und gibt die temporaere URL wieder frei.
Karten koennen private Grundrisse enthalten; HTTP-Caching ist deaktiviert.

API-Grundlagen: [HA Vacuum](https://www.home-assistant.io/integrations/vacuum),
[Feature-Flags](https://github.com/home-assistant/core/blob/dev/homeassistant/components/vacuum/const.py),
[Image-Proxy](https://github.com/home-assistant/core/blob/dev/homeassistant/components/image/__init__.py).

Tests: `tests/test_vacuum_service.py` im isolierten `tests/run_home_hub_checks.py`.
UI-Pruefung mit echten, lesend geladenen Karten und simulierten Steuerbefehlen;
es wird fuer Tests kein Roboter gestartet.
