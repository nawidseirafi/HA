# Hauszentrale

Stand: 2026-09-12. Die Hauszentrale liegt in `backend/services/home_hub`.
Telegram und `/api/home-hub/chat` verwenden denselben `HouseAssistant`.
Die Webansicht ist unter `/home-hub` erreichbar und nutzt die bestehende Anmeldung.

## Datenfluss

1. `HomeHub` authentifiziert sich mit der bestehenden HA-Konfiguration an der WebSocket-API.
2. Er abonniert Zustands- und Registry-Ereignisse vor dem ersten Snapshot.
3. States, Entity-, Device-, Area- und Floor-Registry werden abgeglichen. Auch deaktivierte
   Entities und Devices ohne aktuelle States bleiben im jeweiligen Verzeichnis erhalten.
4. Gepufferte Zustandsereignisse werden anhand ihrer Zeitstempel mit dem Snapshot abgeglichen.
5. Registry-Aenderungen, Wiederverbindungen und ein Abgleich alle fuenf Minuten aktualisieren
   den Bestand. Wiederverbindungen verwenden Backoff bis maximal 30 Sekunden.
6. Der bestehende ContextService berechnet aus diesem Bestand den Hauskontext. Die laufende
   Instanz liefert diesen Snapshot auch an bestehende ContextService-Aufrufer.
7. HomeAssistantService.get_states verwendet den gemeinsamen Bestand bei gesunder Verbindung;
   andernfalls bleibt der bestehende REST-Leseweg erhalten. Aktionen lesen das Ziel erneut direkt.

Ein alter `last_updated` allein bedeutet keinen Sensorausfall. Verbindungsqualitaet (`live`,
`stale`, `unknown`), Registry-Fehler und Entity-Zustaende werden getrennt ausgewiesen.
Die Erreichbarkeitsansicht umfasst alle Integrationen, nicht nur Zigbee2MQTT. Sie beschreibt
Entity-Verfuegbarkeit und ist kein Nachweis physischer Netzwerkerreichbarkeit.

## KI und Agenten

Der Assistent kann Entities suchen und seitenweise laden, Verzeichnisse abfragen, Kontext,
Agentenstatus, Aufgaben, Meldungen, Ereignisse und Aktionen lesen. Die bestehenden
Agenten bleiben Eigentuemer ihrer Fachdaten. Explizit freigegebene Datenansichten umfassen:

- Rechnungen: Zusammenfassungen, Finanzuebersicht, Vertraege, Jahre.
- Garten: Zonen und Verlauf.
- Markt: Berichte, Watchlist und Zusammenfassung.
- MyWellness: Kurse und Buchungen.
- Urlaub: Verlauf.

Weitere Fachansichten werden bewusst als benannte Abfrage ergaenzt; es gibt keinen
beliebigen Methodenaufruf, SQL-Zugriff oder Shell-Zugriff durch das Modell.
Agentenzustaende werden zusaetzlich jede Minute beobachtet; Aenderungen erscheinen im Ereignisverlauf.
Der bestehende LLM-Provider wird weiterverwendet. Er erhaelt nur die angefragten Ergebnisse
und den Chatkontext, nicht pauschal alle Datenbanken. Schluessel mit Token-/Passwort-/Secret-Namen
werden aus Werkzeugergebnissen entfernt. Fachtexte koennen weiterhin private Daten enthalten.

Gespraeche sind nach angemeldetem Webbenutzer bzw. Telegram-Chat und Absender getrennt.
`/forget` entfernt den Verlauf dieses Gespraechs. Maximal 40 Nachrichten werden je Identitaet
gespeichert; maximal 12 werden fuer die aktuelle Anfrage verwendet.

## Aktionen und Beobachtungen

Eine KI-Aktion erzeugt nur einen gespeicherten Vorschlag. `/confirm <id>` oder der authentifizierte
Confirm-Endpunkt bestaetigt ihn fuer dieselbe Identitaet. Vorschlaege verfallen nach fuenf Minuten
und lassen sich nur einmal beanspruchen. Veraenderte Zielzustaende erfordern einen neuen Vorschlag.

Freigegeben sind Ein/Aus fuer light, switch, fan und input_boolean; Oeffnen/Schliessen fuer cover;
und Solltemperatur fuer climate innerhalb der vom Geraet gemeldeten Grenzen. Agentensteuerung
verwendet den vorhandenen Control-Vertrag. Andere HA-Domaenen bleiben lesbar.

Geraeteaktionen werden nach dem Service-Aufruf bis zu 20 Sekunden auf ihren Zielzustand geprueft:
`verified`, `unverified`, `failed` oder bei unklarer Service-Antwort `unknown`.
Eine Solltemperatur-Bestaetigung bedeutet, dass HA den Sollwert meldet, nicht dass der Raum ihn
bereits erreicht hat. Agentenauftraege werden als `accepted` protokolliert; ihr spaeteres fachliches
Ergebnis kommt aus Agentenstatus und Verlauf. Nach einem Prozessabbruch werden beanspruchte
Aktionen nicht automatisch wiederholt.

Neue KI-Regeln beginnen im Beobachtungsmodus: ein Entity-Wechsel auf einen angegebenen
Zustand protokolliert die vorgeschlagene Aktion. `/activate <id>` gibt eine Licht- oder
Ventilatorregel ausdruecklich frei; `/pause <id>` stellt sie zurueck auf Beobachtung.
Die KI selbst hat kein Aktivierungswerkzeug. Andere Aktionen bleiben einzeln zu bestaetigen.
Pro Ziel ist nur eine aktive Hub-Regel erlaubt, mit mindestens fuenf Minuten zwischen Versuchen.
Ausloeser verfallen nach 30 Sekunden in der Warteschlange; beim Verbindungsaufbau wird nicht
nachtraeglich geschaltet. Vor Ausfuehrung werden Freigabe, Ausloeser und Ziel erneut geprueft.
Erkannte fremde Zielaenderungen setzen die Regel fuer 30 Minuten aus.
Diese Erkennung ist best effort, keine atomare Sperre gegen andere HA-Automationen.
Die bestehenden Haushaltsautomationen behalten ihre Ausfuehrung und Schutzbedingungen.
Vor Aktivierung muss deshalb die Zustaendigkeit fuer das Ziel mit bestehenden Regeln geklaert sein.

## Benachrichtigungen

Household-Alarme werden je Empfaenger und Kanal in einer dauerhaften Warteschlange gespeichert.
Der Worker versucht faellige Sendungen alle 15 Sekunden. Fehler werden mit exponentiellem
Backoff bis zu einer Stunde erneut versucht, auch wenn der Alarm inzwischen beendet ist.
Bereits erfolgreiche Kanaele werden nicht erneut gesendet. Message-Center-Deduplizierung
verhindert dadurch keine Wiederholungen fehlgeschlagener Sendungen mehr.

`queued` bedeutet gespeichert, `sent` bedeutet vom Ziel-API angenommen, nicht vom Menschen
gelesen. Bei Prozessabbruch unmittelbar nach erfolgreicher Zustellung, vor dem lokalen Commit,
kann eine Nachricht doppelt erscheinen (At-least-once-Zustellung). Die Queue ist keine
Ersetzung der unabhaengigen HA- und lokalen Sicherheitsalarme.

## Betrieb

Ein Backend-Prozess / ein Uvicorn-Worker pro Datenverzeichnis. Keine parallelen Telegram-Poller
oder mehrfachen Hub-Instanzen mit demselben Bestand betreiben.

Normaler Start erfolgt wie bisher; die Hub-Worker werden mit dem Backend gestartet.
Fuer lokalen Beobachtungsbetrieb:

```sh
ROBOTERSTEVE_MONITOR_ONLY=1 ROBOTERSTEVE_DATA_DIR=/tmp/steve-hub-preview \
  .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8082
```

Dieser Modus startet keine Agenten-Scheduler, versendet keine Queue-Nachrichten und blockiert
Schaltaktionen. Leseabfragen an HA bleiben aktiv. Gespeicherte Beobachtungsregeln und Vorschlaege
sind weiterhin moeglich. `ROBOTERSTEVE_DATA_DIR` verschiebt relative `data/...`-Pfade; explizite
absolute Pfade und andere bestehende Agentenspeicher werden dadurch nicht umgeschrieben.
Konfigurationsaenderungen an der HA-Verbindung erfordern einen Backend-Neustart.

Persistenz: `data/home_hub/home_hub.db` (SQLite WAL). Inventar, Ereignisse, Gespraeche, Aktionen,
Regeln und Zustellwarteschlange gehoeren ins Backup. Ereignisse, alte Gespraeche und abgeschlossene
Aktionen werden beim regelmaessigen Abgleich nach 30 Tagen bereinigt. Die alten ContextService-
Historientabellen behalten ihre bisherige Aufbewahrung. Regeln und Queue haben keine automatische
Loeschung. Bei Verbindungsunterbrechung ist die lokale Ereignishistorie unvollstaendig.

Mit Start-/Endzeit kann das KI-Historienwerkzeug den HA-Recorder abfragen (maximal sieben Tage
je Anfrage, Ergebnisse paginiert). Verfuegbarkeit und Aufbewahrung dieser Daten bestimmt HA.

## Pruefung

```sh
.venv/bin/python -W ignore::ResourceWarning tests/run_home_hub_checks.py
cd frontend
npm run build
```

Der gezielte Testlauf isoliert relative Laufzeitdaten in einem temporaeren Verzeichnis und
blockiert externe Socket-Verbindungen. Er prueft unter anderem Registry-Zuordnung, Stale-Zustaende,
WebSocket-Nachrichten, Zustimmung und Ablauf, geaenderte Ziele, Ergebnisverifikation,
Versandwiederholung nach Neustart, Agentenfehler, API-Authentifizierung und Chatidentitaeten.
