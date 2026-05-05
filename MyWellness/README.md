# RoboterSteve - Das MyWellness Booking System für Home Assistant
7HN5-HGN5-QKU0-KD8L-G7P9-UJ8I-C2AX
Dieses Projekt automatisiert die Buchung von MyWellness-Kursen über Home Assistant.

Die Lösung besteht aus **einem Python-Script**, das in zwei Modi gestartet werden kann:

- `prepare` → Kurs-IDs vorab suchen und zwischenspeichern
- `book` → gespeicherte Kurs-IDs schnell buchen

Dadurch muss die Kursliste nicht erst um 21:00 Uhr geladen werden. Die eigentliche Buchung kann dadurch deutlich schneller erfolgen.

---

## Funktionsweise

### 1. Vorbereitung

Um ca. **20:58 Uhr** wird das Script im Modus `prepare` gestartet.

Dabei passiert Folgendes:

1. Ziel-Datum wird berechnet, z. B. heute + 2 Tage
2. MyWellness-Kalender wird abgefragt
3. gewünschte Kurse werden gesucht
4. Kurs-IDs werden in einer Cache-Datei gespeichert

Beispiel:

```json
{
  "created_at": "2026-04-27T20:58:00",
  "target_date": "20260429",
  "course_ids": {
    "Cross-Power": "abc123",
    "Body Workout": "xyz789"
  }
}
```

Die Datei wird z. B. hier gespeichert:

```text
/config/mywellness_course_ids_cache.json
```

---

### 2. Buchung

Um ca. **20:59:58 Uhr** wird das Script im Modus `book` gestartet.

Dabei passiert Folgendes:

1. gespeicherte Kurs-IDs werden geladen
2. beide Kurse werden parallel gebucht
3. falls MyWellness noch nicht geöffnet ist, wird mehrfach erneut versucht
4. Ergebnis wird per Home Assistant Notification gesendet

Das Script wartet nicht bis 21:00 Uhr, sondern versucht direkt zu buchen und wiederholt die Anfrage sehr schnell.

Beispiel:

```python
MAX_RETRIES = 30
RETRY_DELAY = 0.2
```

Das bedeutet ungefähr:

```text
30 Versuche × 0,2 Sekunden = ca. 6 Sekunden Zeitfenster
```

Wenn das Script um `20:59:58` startet, deckt es ungefähr den Zeitraum bis `21:00:04` ab.

---

## Voraussetzungen

- Home Assistant
- Python 3
- Python Virtual Environment, z. B.:

```text
/config/venv/bin/python
```

- installiertes Python-Paket:

```bash
pip install requests
```

- gültiger MyWellness Auth Token
- gültige MyWellness User ID
- gültiger Home Assistant Long-Lived Access Token
- Home Assistant Notification Service

---

## Dateistruktur

Empfohlene Struktur:

```text
/config/mywellness.py
/config/mywellness_course_ids_cache.json
/config/mywellness.log
```

Das Python-Script liegt hier:

```text
/config/Rmywellness.py
```

---

## Python-Script starten

Das Script verwendet einen Kommandozeilen-Parameter:

```bash
python RoboterSteve_multi.py prepare
```

oder:

```bash
python RoboterSteve_multi.py book
```

Im Script wird der Modus so gelesen:

```python
import sys

MODE = sys.argv[1] if len(sys.argv) > 1 else "book"
```

---

## Home Assistant `shell_command`

In der `configuration.yaml` eintragen:

```yaml
shell_command:
  mywellness_prepare: "/config/venv/bin/python /config/mywellness.py prepare"
  mywellness_book: "/config/venv/bin/python /config/mywellness.py book"
```

Danach Home Assistant neu starten oder YAML neu laden.

---

## Home Assistant Automationen

### Kurs-IDs vorbereiten

Diese Automation läuft vor der eigentlichen Buchung:

```yaml
- alias: Mywellness Kurs IDs vorbereiten
  trigger:
    - platform: time
      at: "20:58:00"
  action:
    - service: shell_command.mywellness_prepare
  mode: single
```

---

### Kurse buchen

Diese Automation startet die eigentliche Buchung:

```yaml
- alias: "MyWellness Booking System"
  trigger:
    - platform: time
      at: "20:59:58"
  action:
    - service: shell_command.mywellness_book
  mode: single
```

---

## Warum `20:59:58`?

MyWellness öffnet häufig um 21:00 Uhr, aber nicht immer exakt.

Deshalb startet das Script schon kurz vorher und versucht mehrfach zu buchen.

Vorteil:

- wenn MyWellness früher öffnet, bist du sofort dabei
- wenn MyWellness exakt um 21:00 öffnet, trifft einer der Retry-Versuche
- wenn MyWellness wenige Sekunden später öffnet, wird ebenfalls noch versucht

---

## Wichtige Konfiguration im Script

### Home Assistant

```python
HA_URL = "http://homeassistant.local:8123"
HA_TOKEN = "DEIN_HOME_ASSISTANT_TOKEN"
HA_NOTIFY_SERVICE = "notify.mobile_app_system_error_404"
```

### MyWellness

```python
auth_token = "DEIN_MYWELLNESS_TOKEN"
userId = "DEINE_USER_ID"
FACILITY_ID = "DEINE_FACILITY_ID"
```

### Kurse

```python
desired_courses = ["Cross-Power", "Body Workout"]
```

### Tage im Voraus

```python
days = 2
```

### Retry-Verhalten

```python
MAX_RETRIES = 30
RETRY_DELAY = 0.2
REQUEST_TIMEOUT = 2
```

---

## Cache-Verhalten

Die Kurs-IDs werden in dieser Datei gespeichert:

```text
mywellness_course_ids_cachejson
```

Der Cache enthält:

- Erstellungszeitpunkt
- Ziel-Datum
- Kursname → Kurs-ID

Wenn beim Prepare-Lauf keine Kurse gefunden werden, bleibt der alte Cache erhalten.

Dadurch wird verhindert, dass ein funktionierender Cache durch eine leere Antwort überschrieben wird.

---

## Fallback-Verhalten

Wenn beim Buchen keine Cache-Datei gefunden wird, versucht das Script automatisch, die Kurs-IDs sofort neu zu suchen.

Ablauf:

```text
book startet
→ kein Cache gefunden
→ prepare wird automatisch ausgeführt
→ danach erneuter Buchungsversuch
```

Das ist robuster, aber langsamer als ein vorheriger Prepare-Lauf.

---

## Logging

Das Script schreibt eigene Logs in:

```text
mywellness.log
```

Beispiel-Log:

```text
[2026-04-27 20:59:58.123] Cross-Power: Versuch 1, Status 400, 184 ms, Antwort: Booking has not opened
[2026-04-27 21:00:00.041] Cross-Power: Versuch 8, Status 200, 201 ms, Antwort: ...
```

Die Logs helfen bei der Analyse:

- wann der erste Versuch gestartet wurde
- wie schnell die API geantwortet hat
- welcher Versuch erfolgreich war
- ob MyWellness noch geschlossen war

---

## Shell-Logging

Wenn das Script selbst loggt, ist ein Shell-Redirect nicht zwingend nötig.

Nicht zwingend erforderlich:

```yaml
>> /config/mywellness.log 2>&1
```

Empfohlen ist eher:

```yaml
shell_command:
  mywellness_prepare: "/config/venv/bin/python /config/RoboterSteve_multi.py prepare"
  mywellness_book: "/config/venv/bin/python /config/RoboterSteve_multi.py book"
```

Wenn du zusätzlich Shell-Logging nutzt, schreibt die Shell unabhängig vom Python-Logging in eine eigene Datei.

---

## Bedeutung von `2>&1`

Falls du Shell-Logging verwendest:

```bash
>> /config/mywellness.log 2>&1
```

Bedeutung:

- `>> /config/mywellness.log` schreibt normale Ausgaben in die Log-Datei
- `2>&1` leitet Fehlerausgaben ebenfalls in dieselbe Datei um

Kurz gesagt:

```text
stdout + stderr → gleiche Log-Datei
```

---

## Sicherheit

Wichtig:

- Tokens niemals öffentlich posten
- Tokens nicht in ein öffentliches Git-Repository committen
- `.gitignore` verwenden
- bei versehentlichem Veröffentlichen Tokens sofort erneuern

Empfohlene `.gitignore`:

```gitignore
mywellness_course_ids_cache.json
mywellness.log
*.log
.env
```

Falls echte Tokens versehentlich veröffentlicht wurden:

1. Home Assistant Long-Lived Access Token löschen
2. neuen Token erstellen
3. MyWellness Token erneuern
4. Git-Historie bereinigen, falls das Repository öffentlich war

---

## Home Assistant Token erneuern

In Home Assistant:

1. Profil öffnen
2. nach unten zu `Long-Lived Access Tokens` scrollen
3. alten Token löschen
4. neuen Token erstellen
5. neuen Token ins Script eintragen

---

## Empfohlene Zeitplanung

```text
20:58:00  → prepare
20:59:58  → book
```

Optional aggressiver:

```text
20:57:00  → prepare
20:59:57  → book
```

Je früher `book` startet, desto mehr frühe Fehlversuche entstehen.  
Mit `MAX_RETRIES = 30` und `RETRY_DELAY = 0.2` ist ein Start um `20:59:58` ein guter Kompromiss.

---

## Testen

### Prepare manuell testen

```bash
/config/venv/bin/python /config/mywellness.py prepare
```

Danach prüfen, ob die Datei erstellt wurde:

```text
mywellness_course_ids_cachejson
```

### Book manuell testen

```bash
/config/venv/bin/python /config/mywellness.py book
```

Achtung: Das kann echte Buchungsversuche auslösen.

---

## Fehlerbehebung

### Keine Cache-Datei gefunden

Mögliche Ursachen:

- `prepare` wurde nicht ausgeführt
- falscher Pfad
- Script hat keine Schreibrechte
- MyWellness API hat keine Kurse geliefert

### Cache-Datum passt nicht

Der Cache gehört zu einem anderen Ziel-Datum.

Lösung:

```bash
/config/venv/bin/python /config/mywellness.py prepare
```

### Keine Kurs-ID gespeichert

Mögliche Ursachen:

- Kursname stimmt nicht exakt
- Kurs findet an dem Tag nicht statt
- Kurs ist im Kalender noch nicht sichtbar

### Home Assistant Notification funktioniert nicht

Prüfen:

```python
HA_NOTIFY_SERVICE = "notify.mobile_app_*"
```

Der Service muss exakt dem Service-Namen in Home Assistant entsprechen.

---

## Kurzfassung

Das System funktioniert so:

```text
20:58:00
→ Kurs-IDs suchen und speichern

20:59:58
→ gespeicherte Kurs-IDs laden
→ Kurse parallel buchen
→ bei "Booking has not opened" mehrfach wiederholen
→ Ergebnis per Home Assistant Notification senden
```

---

## Hinweis

Dieses Script nutzt inoffizielle API-Endpunkte von MyWellness.  
Falls MyWellness API, Authentifizierung oder Datenstruktur ändert, muss das Script angepasst werden.
