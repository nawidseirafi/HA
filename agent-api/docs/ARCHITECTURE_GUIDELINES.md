# RoboterSteve – Architecture Guidelines

Version: 1.0

Dieses Dokument definiert die grundlegenden Architekturprinzipien von RoboterSteve.

Diese Regeln gelten für alle Editionen (Personal, Sentero und zukünftige Produkte) und dürfen nur nach einer bewussten Architekturentscheidung geändert werden.

Dieses Dokument beschreibt keine Implementierungsdetails, sondern die Leitplanken für jede zukünftige Entwicklung.

---

# 1. Grundprinzipien

RoboterSteve ist eine modulare Agentenplattform.

Alle Funktionen sollen in klar abgegrenzten Komponenten umgesetzt werden.

Grundsatz:

> Eine Funktion hat genau einen Verantwortlichen.

Keine Logik darf mehrfach implementiert werden.

---

# 2. Single Source of Truth

Für jede Information existiert genau eine Quelle.

Beispiele:

- Home Assistant ist Quelle aller Sensorzustände.
- Agent-Manifeste sind Quelle aller Agent-Metadaten.
- Scheduler verwaltet ausschließlich Zeitsteuerungen.
- Messaging Service verwaltet alle Nachrichten.
- Jeder Agent besitzt seine eigene Fachdatenbank.

Andere Komponenten dürfen diese Daten nur lesen oder über definierte APIs verändern.

---

# 3. Agenten

Jeder Agent besitzt:

- eigenes Manifest
- eigene Konfiguration
- eigene Fachlogik
- eigene Datenbank (wenn notwendig)
- eigene API
- optional Scheduler
- optional LLM

Agenten dürfen niemals direkt die Datenbank eines anderen Agenten verändern.

Kommunikation erfolgt ausschließlich über Services oder APIs.

---

# 4. Orchestrator

Der Orchestrator besitzt keine Fachlogik.

Er koordiniert ausschließlich:

- Agent Discovery
- Agent Status
- Agent Control
- Scheduler
- Routing

Der Orchestrator darf niemals Rechnungen analysieren, Gartenlogik enthalten oder Sentero-Regeln implementieren.

---

# 5. Agent Control

Alle Agenten werden ausschließlich über den Agent-Control-Vertrag gesteuert.

Erlaubte Aktionen:

- status
- enable
- disable
- start
- stop
- run

Neue Spezial-APIs dürfen Agent Control niemals umgehen.

---

# 6. Home Assistant

Home Assistant ist ausschließlich Datenquelle und Geräte-Steuerung.

Alle Smart-Home-Geräte laufen über Home Assistant.

RoboterSteve spricht niemals direkt mit:

- Zigbee
- Matter
- WLAN-Geräten
- FritzBox
- MQTT

Falls möglich erfolgt jede Kommunikation über Home Assistant.

---

# 6a. Garden

Garden ist der owning Agent fuer Rasen, Bodenfeuchte, Bewaesserung, Mähroboter und Gartenhistorie.

Home Assistant bleibt die einzige Quelle fuer Sensorzustände und die einzige Schnittstelle zur Gerätesteuerung.

Der Orchestrator enthaelt keine Garden-Fachlogik.

Der Scheduler enthaelt keine Garden-Imports und fuehrt Garden nur ueber den generischen Agent-Control-Vertrag aus.

Die Garden-Decision-Engine bewertet regelbasiert und fuehrt keine Home-Assistant-Service-Calls aus.

KI darf Garden-Empfehlungen begruenden, aber keine Geräte direkt steuern und keine regelbasierte Safety-Freigabe ueberstimmen.

Kalibrierungs-, Sampling- und Diagnose-Entities duerfen nicht fuer fachliche Bewaesserungsentscheidungen verwendet werden.

Mähroboter und Bewaesserung muessen gegenseitig verriegelt bleiben.

---

# 7. Wall Dashboard

Wall ist ein Smart-Home Dashboard.

Wall besitzt keine Geschäftslogik.

Wall

- liest Daten
- zeigt Daten
- startet Geräte

Wall analysiert niemals Daten.

Alle Bewertungen erfolgen durch Agenten.

---

# 8. Sentero

Sentero ist ein Produkt.

Sentero ist keine Entwickleroberfläche.

Regeln:

Keine technischen Begriffe

Keine Entity IDs

Keine Datenbanken

Keine API-Begriffe

Keine Agentenkarte

Keine Infrastrukturansichten

Alles muss in Alltagssprache formuliert werden.

---

# 9. KI

Die KI unterstützt Entscheidungen.

Die KI entscheidet niemals allein.

Regeln:

KI darf

- analysieren
- Empfehlungen geben
- Zusammenfassungen schreiben
- Warnungen erzeugen

KI darf niemals

- Türen öffnen
- Geräte schalten
- Lampen steuern
- Heizungen verändern
- Alarm auslösen

ohne regelbasierte Freigabe.

Beispiel:

Der Household Comfort Service darf einen Schlafzimmer-Ventilator nur dann ueber Home Assistant schalten, wenn die regelbasierte Freigabe erteilt wurde. Die KI darf dazu eine Einschaetzung und Begruendung liefern, aber keinen Service-Call erzeugen und keine Regel ueberstimmen.

---

# 10. Lernen

Agenten dürfen Verhalten lernen.

Dabei gelten folgende Regeln:

Alle Rohdaten bleiben lokal.

Lernen erfolgt pro Installation.

Es gibt kein Cloud-Profil.

Es werden ausschließlich anonymisierte Merkmale ausgewertet.

Neue Modelle dürfen bestehende Regeln ergänzen, aber nicht ersetzen.

---

# 11. Benutzeroberflächen

Jede Oberfläche verfolgt genau einen Zweck.

Personal

→ Administrator

Sentero

→ Angehörige

Wall

→ Smart Home Bedienung

Adminfunktionen dürfen niemals in Sentero erscheinen.

---

# 12. Services

Services sind Querschnittskomponenten.

Beispiele:

Messaging

Authentication

Infrastructure

Home Assistant

LLM

Services besitzen keine Fachlogik.

---

# 13. Datenbanken

Fachdaten bleiben beim jeweiligen Agenten.

Beispiele:

Invoice

→ invoices.db

Garden

→ garden.db

Market

→ market.db

Sentero

→ sentero.db

Household Comfort

→ Household Service / optional spaeter household.db

Keine globale Monolith-Datenbank.

---

# 14. APIs

Jede API besitzt genau einen Verantwortungsbereich.

Keine API ruft direkt andere APIs derselben Anwendung auf.

Gemeinsame Logik gehört in Services.

---

# 15. Frontend

Gemeinsame Komponenten liegen ausschließlich unter

frontend/src/shared/

Produktlogik liegt ausschließlich unter

frontend/src/apps/<edition>

Keine verstreuten if (edition == ...).

---

# 16. Design

Alle Produkte verwenden dieselbe Designphilosophie.

Prinzipien:

weniger ist mehr

wenige Farben

runde Elemente

große Abstände

klare Typografie

Animationen nur dezent.

---

# 17. Sicherheit

Secrets niemals im Code.

Nur

.env

Environment

config.yaml

Benutzerdaten verlassen niemals ohne Zustimmung das System.

---

# 18. Updates

Updates müssen

atomar

rollbackfähig

editionfähig

offlinefähig

sein.

Ein fehlgeschlagenes Update darf niemals das System unbrauchbar machen.

---

# 19. Erweiterbarkeit

Neue Agenten müssen ohne Änderungen bestehender Agenten integrierbar sein.

Neue Produkte müssen ohne Fork des Repositories entstehen.

---

# 20. Code-Regeln

Lieber mehrere kleine Komponenten als große Klassen.

Keine Copy-Paste-Logik.

Klare Verantwortlichkeiten.

Keine zyklischen Abhängigkeiten.

---

# 21. Grundsatz

RoboterSteve soll auch in fünf Jahren noch verständlich sein.

Jede neue Funktion muss:

einfach wirken

lokal nachvollziehbar sein

in die bestehende Architektur passen

keine bestehenden Regeln verletzen

Im Zweifel gilt:

**Einfachheit vor Cleverness.**
