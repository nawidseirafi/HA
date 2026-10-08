# Anmeldung mit Face ID auf dem iPad

RoboterSteve unterstützt zusätzlich zum Passwort Passkeys (WebAuthn). Auf einem
geeigneten iPad bestätigt Face ID die Anmeldung, auf anderen Geräten Touch ID
oder der Gerätecode. Welche Bestätigung angeboten wird, entscheidet das Gerät.
RoboterSteve erhält keine Gesichtsbilder oder biometrischen Daten.

## Einrichten und verwenden

1. RoboterSteve in einem aktuellen Safari über seine feste **HTTPS-Adresse** öffnen.
2. Wie bisher mit Benutzername und Passwort anmelden.
3. **Settings → Face ID & Passkeys** öffnen, eine Bezeichnung vergeben
   (zum Beispiel „Mein iPad“) und das aktuelle Passwort eingeben.
4. **Face ID / Passkey einrichten** antippen und den Apple-Dialog bestätigen.
5. Nach dem Abmelden **Mit Face ID / Passkey anmelden** wählen.

Das Passwort bleibt als weitere Anmeldemöglichkeit erhalten. Passkeys lassen
sich in Settings einzeln entfernen. Ein dort entfernter Passkey wird vom Server
nicht mehr akzeptiert; der Eintrag im Apple-Passwortmanager kann zusätzlich dort
entfernt werden. Bereits angemeldete Sitzungen bleiben bestehen.

## Server und HTTPS

Die Python-Abhängigkeiten aus `requirements.txt` installieren und das Frontend
mit `npm ci` und `npm run build` im Ordner `frontend` bauen. Danach das Backend
neu starten bzw. die übliche Aktualisierung installieren.

Standardmäßig verwendet RoboterSteve die vom Backend erkannte Website-Adresse
als erwartete Origin und deren Hostnamen als WebAuthn-Relying-Party-ID. Bei einem
Reverse Proxy muss das Backend die externe HTTPS-Adresse korrekt erkennen.
Alternativ die externe Adresse ausdrücklich in `agent-api/.env` setzen:

```dotenv
ROBOTERSTEVE_PASSKEY_ORIGIN=https://steve.example.org
```

Hier die tatsächlich verwendete Adresse eintragen, ohne Pfad. Nicht die
Update-Download-Adresse verwenden. Frontend und API sollten unter derselben
Adresse erreichbar sein. Änderungen an dieser Einstellung erfordern bei einem
systemd-/Container-Environment einen Neustart des Backends. Die Website-Origin
wird exakt geprüft; die Einstellung ist keine beliebige CORS-Freigabe.

Safari auf dem iPad benötigt HTTPS mit einem vertrauenswürdigen Zertifikat.
`http://192.168.…:8080` genügt nicht. Eine vorhandene HTTPS-Anbindung kann genutzt
werden; eine öffentliche Freigabe ins Internet ist dafür nicht erforderlich.
Passkeys sind an den Hostnamen gebunden. Deshalb vor dem Einrichten die dauerhaft
gewünschte Adresse festlegen und später dieselbe Adresse öffnen.

Für lokale Entwicklung **auf dem Entwicklungsrechner** ist beispielsweise
`ROBOTERSTEVE_PASSKEY_ORIGIN=http://localhost:5173` mit dem Vite-Proxy möglich.
Die localhost-Ausnahme gilt nicht für den Zugriff vom iPad auf die LAN-IP.

## Debian: HTTPS für `ai-agent.local` einrichten

Ausgangslage: RoboterSteve ist bereits unter `http://ai-agent.local:8080`
erreichbar. Caddy läuft auf demselben Debian-Rechner und leitet HTTPS an die
bestehende Anwendung weiter. Danach auf dem iPad `https://ai-agent.local`
**ohne `:8080`** verwenden. Die folgenden Befehle sind auf dem Debian-Zielrechner
auszuführen, außer dem ausdrücklich gekennzeichneten Mac-Schritt.

### 1. Caddy installieren

```bash
sudo apt update
sudo apt install -y caddy
```

Das Paket ist in Debian 12 und 13 verfügbar. Ports 80 und 443 müssen für Caddy
verfügbar sein. Falls dort bereits ein Webserver läuft, dessen HTTPS-Konfiguration
verwenden oder die Dienste aufeinander abstimmen. Bei aktiver Firewall TCP 443
für das eigene Heimnetz erlauben; TCP 80 wird für die HTTP-Weiterleitung genutzt.
Eine Router-Portfreigabe ins Internet ist nicht erforderlich.

### 2. HTTPS und Weiterleitung konfigurieren

```bash
sudo nano /etc/caddy/Caddyfile
```

Bei einer frischen Caddy-Installation den Beispielinhalt durch Folgendes ersetzen.
Wenn Caddy bereits andere Websites bedient, diesen Block ergänzen und die
vorhandenen Einträge erhalten:

```caddyfile
ai-agent.local {
    tls internal
    reverse_proxy 127.0.0.1:8080
}
```

Konfiguration prüfen und nur bei erfolgreicher Prüfung aktivieren:

```bash
sudo -u caddy -H caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
```

`tls internal` erstellt Zertifikate mit Caddys eigener lokaler Zertifizierungsstelle.
Das iPad muss deren Stammzertifikat einmal erhalten und ihm vertrauen.

### 3. RoboterSteve-Adresse festlegen

Die mitgelieferte Dienstvorlage verwendet `agent-api.service`. Dafür:

```bash
sudo systemctl edit agent-api
```

Im bearbeitbaren Bereich eintragen:

```ini
[Service]
Environment="ROBOTERSTEVE_PASSKEY_ORIGIN=https://ai-agent.local"
```

Speichern, dann:

```bash
sudo systemctl daemon-reload
sudo systemctl restart agent-api
```

Falls dein Dienst anders heißt, dessen Namen verwenden. Alternativ lässt sich
dieselbe Variable in der `.env` neben RoboterSteves `config.yaml` setzen; eine
bereits gesetzte Prozess-/systemd-Variable hat dabei Vorrang.

### 4. Stammzertifikat auf das iPad übertragen

Auf Debian nur das öffentliche Stammzertifikat zum Kopieren bereitstellen:

```bash
sudo install -m 0644 /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt /tmp/ai-agent-root.crt
```

Auf deinem **Mac** im Terminal herunterladen. `DEIN_DEBIAN_BENUTZER` durch den
Benutzernamen deiner SSH-Anmeldung ersetzen:

```bash
scp DEIN_DEBIAN_BENUTZER@ai-agent.local:/tmp/ai-agent-root.crt ~/Downloads/ai-agent-root.crt
```

Die Datei anschließend per AirDrop vom Mac auf das iPad übertragen. Nur die
Datei `root.crt` weitergeben, keine privaten Schlüssel (`.key`).

Auf dem iPad:

1. Das empfangene Zertifikat öffnen und das angebotene Profil unter
   **Einstellungen → Allgemein → VPN und Geräteverwaltung** installieren
   (gegebenenfalls zunächst **Profil geladen** auswählen).
2. Unter **Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen**
   das vollständige Vertrauen für die eigene **Caddy Local Authority** aktivieren.
3. Safari öffnen und `https://ai-agent.local` aufrufen. Die Verbindung muss ohne
   Zertifikatswarnung funktionieren; eine Warnung lediglich zu übergehen genügt nicht.

### 5. Verbindung prüfen und Face ID einrichten

Optional auf Debian prüfen, ohne dort global ein Stammzertifikat zu installieren:

```bash
sudo curl --cacert /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt --resolve ai-agent.local:443:127.0.0.1 https://ai-agent.local/health
```

Erwartete Antwort: `{"status":"ok"}`.

Auf dem iPad unter `https://ai-agent.local` mit Passwort anmelden und in
**Settings → Face ID & Passkeys** den Passkey einrichten. Die neue Adresse als
Lesezeichen speichern. Die alte HTTP-Adresse auf Port 8080 bietet weiterhin
keine Passkey-Anmeldung.

Bei Problemen:

- **502 Bad Gateway:** Prüfen, ob RoboterSteve auf `127.0.0.1:8080` läuft.
- **Seite nicht erreichbar:** Caddy-Status, Firewall und Erreichbarkeit von
  `ai-agent.local` im selben Heimnetz prüfen.
- **Zertifikatswarnung:** Profilinstallation und vollständiges Vertrauen auf
  dem iPad prüfen. Caddys Datenverzeichnis dauerhaft erhalten; eine neu erzeugte
  Zertifizierungsstelle benötigt erneut Vertrauen auf dem iPad.
- **Passkey-Adresse stimmt nicht:** Die Origin-Einstellung muss genau
  `https://ai-agent.local` sein. Das iPad darf dabei weder die IP-Adresse noch
  `http://ai-agent.local:8080` verwenden.
- **Caddy startet nicht:** `sudo journalctl -u caddy -n 50 --no-pager` zeigt den Fehler.

Quellen: [Debian-Paket Caddy](https://packages.debian.org/trixie/caddy),
[Caddy: lokales HTTPS mit systemd](https://caddyserver.com/docs/running#local-https-with-systemd),
[Apple: Zertifikaten auf dem iPad vertrauen](https://support.apple.com/de-de/102390).

## Speicherung und Prüfung

Öffentliche Schlüssel, zufällige Benutzerkennungen, Signaturzähler und temporäre
Anfragen liegen in `agent-api/data/auth/passkeys.sqlite3`. Diese Datei muss bei
Backups und Deployments erhalten bleiben. Private Schlüssel verbleiben im
Authenticator bzw. Passwortmanager. Die Datenbank wird automatisch angelegt;
ein verlorener Datenbestand erfordert eine erneute Passkey-Einrichtung.

Die Einrichtung verlangt eine angemeldete Sitzung und das aktuelle Passwort.
Anfragen verfallen nach fünf Minuten, sind nur einmal verwendbar und bei der
Einrichtung zusätzlich an die Sitzung gebunden. Registrierung und Anmeldung
verlangen eine Benutzerverifikation. Signatur, Challenge, Origin, RP-ID und
Benutzerzuordnung werden serverseitig überprüft. Die bestehende Abwesenheitsregel
und „Auf diesem Gerät angemeldet bleiben“ gelten auch für Passkey-Anmeldungen.

Im Beobachtungsmodus funktionieren bestehende Passkeys zur Anmeldung; das
Einrichten und Entfernen bleibt wie andere Änderungen gesperrt.

Technische Grundlagen: [Apple Passkeys](https://developer.apple.com/passkeys/),
[py_webauthn](https://duo-labs.github.io/py_webauthn/),
[SimpleWebAuthn Browser](https://simplewebauthn.dev/docs/packages/browser).
