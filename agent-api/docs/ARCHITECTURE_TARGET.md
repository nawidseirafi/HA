# Zielarchitektur und offene Architekturpunkte

Stand: 2026-06-09

Dieses Dokument beschreibt nicht den Ist-Zustand im Detail. Der aktuelle Aufbau ist in `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md` und `docs/UPDATE_SYSTEM.md` dokumentiert. Hier stehen die Zielregeln und die noch offenen Architekturpunkte, damit neue Arbeiten nicht wieder gegen die gewachsene Struktur laufen.

# Leitlinien

- Dieses Repository bleibt die Quelle fuer RoboterSteve.
- Ausgelagerte Produkte werden nicht mehr in diesem Repo dokumentiert oder gebaut.
- Bestehende Agenten, APIs und Datenbanken werden nicht ohne Migrationspfad gebrochen.
- Manifeste bleiben Quelle fuer Agent-Metadaten und Scheduler-Defaults.
- Fachliche Daten bleiben bei den owning Agents oder Services.
- Querschnittsdaten bekommen eigene Services und eigene Persistenz.
- Der ContextService ist die zentrale Quelle fuer berechneten Lebens- und Hauskontext.
- Der Orchestrator koordiniert, besitzt aber keine Agent-Fachlogik.
- Agenten werden nur ueber den Agent-Control-Vertrag zentral gesteuert.
- Hinweise, Warnungen und Aufgaben laufen ueber den Messaging Service.
- Technische Details bleiben Personal/Admin/Dev vorbehalten.

# Bereits umgesetzt

## Produktkonfiguration

Umgesetzt:

- RoboterSteve nutzt `editions/personal.yaml` als Personal-Konfiguration.
- Registry, Agent-Router, Agent-Liste und Orchestrator Map respektieren die erlaubten Agenten und Core-Services.
- `deployment_build.py` erzeugt RoboterSteve-Deployment-Artefakte.
- Build-Artefakte werden unter `build/robotersteve/` und `build/updates/robotersteve/stable/` erzeugt.
- RoboterSteve bleibt ein lokales/systemd Deployment.

Zielregel:

- Neue RoboterSteve-Agenten muessen explizit in Konfiguration, Manifest und Navigation eingetragen werden.
- Ausgelagerte Produkte gehoeren nicht in dieses Repository.

## Frontend Multi-App

Umgesetzt:

- Gemeinsamer Entry Point: `frontend/src/main.tsx`.
- Personal App: `frontend/src/apps/personal/`.
- Shared-Bereich: `frontend/src/shared/`.
- `npm run build` baut die Personal App.

Zielregel:

- Keine produkt- oder app-spezifische Fachlogik in shared Komponenten.
- Shared enthaelt nur wirklich gemeinsame API-, Auth-, UI- und Utility-Bausteine.
- RoboterSteve-Navigation und Seiten gehoeren in `apps/personal/`.

## Agent Registry und Orchestrator

Umgesetzt:

- `discover_agent_manifests()` filtert standardmaessig nach erlaubten RoboterSteve-Agenten.
- `include_agent_routers(app)` bindet nur erlaubte Agent-Router ein.
- `/api/agents` zeigt nur erlaubte Agenten.
- `/api/orchestrator/map` baut seine Agent-Knoten aus der gefilterten Registry.
- `/api/orchestrator/map` liefert standardmaessig eine schnelle Manifest-/Registry-Map; teure Live-Checks laufen optional ueber `?live=true`.
- `backend/services/orchestrator_control_service.py` nutzt den Agent-Control-Vertrag.

Zielregel:

- Orchestrator Map bleibt die zentrale UI-Quelle fuer Agent-Status.
- Agent-Metadaten kommen aus Manifesten.
- Runtime-Status kommt aus Agent-Control, nicht aus hardcodierter UI-Logik. Fuer den ersten Render duerfen leichte Statuswerte genutzt werden; Live-Status darf nicht die Map blockieren.

## Agent Control Contract

Umgesetzt als gemeinsamer Vertrag in `backend/agents/control.py` und ueber die Registry nutzbar.

Jeder steuerbare Agent soll mindestens sauber auf folgende Aktionen abbildbar sein:

- `status()`
- `enable()`
- `disable()`
- `start_scheduler()`
- `stop_scheduler()`
- optional `run(...)`

Statuswerte bleiben normalisierbar auf:

- `active`
- `running`
- `disabled`
- `error`
- optional `paused`

Zielregel:

- Deaktivierte Agenten duerfen keine Scheduler-Laeufe ausfuehren.
- Der Scheduler darf nicht agent-spezifisch importieren, sondern muss ueber den Control-Vertrag arbeiten.
- Agenten ohne Control-Vertrag werden nicht als harte Fehler-Spamquelle behandelt; geplante Laeufe werden kontrolliert uebersprungen.

## Scheduler

Umgesetzt:

- Scheduler Agent mit Service, Store, API und SQLite-Persistenz.
- Manifest-Defaults werden als Initialwerte verwendet.
- Veraltete Manifest-Defaults werden bereinigt, ohne manuelle Tasks zu loeschen.
- Scheduler UI gruppiert Tasks nach Agent statt jede Aufgabe als grosse Einzelkarte zu zeigen.
- Task-Zeittexte werden dynamisch aus `schedule` erzeugt.
- Platform-Routine-Erfolge erzeugen keine Message-Center-Flut mehr.
- Infrastructure Health Check laeuft als Default taeglich um 07:00 Uhr.
- Market hat als Default nur noch eine Analyse um 18:00 Uhr.
- Garden hat als Default eine Statuspruefung um 07:00 Uhr.

Aktuelle Zielregel:

- Scheduler-Defaults duerfen bestehende lokale Anpassungen nicht ueberschreiben.
- Erfolgsmeldungen fuer Routinechecks bleiben still; Fehler und handlungsrelevante Warnungen duerfen Messages erzeugen.
- Tasks ausserhalb aktivierter Agenten duerfen nicht laufen.

Offen fuer spaetere Versionen:

- Task-Abhaengigkeiten.
- Task-Ketten.
- Kalender-Integration.
- Vollstaendige Migration aller agent-internen Scheduler in den zentralen Scheduler.

## Messaging Service

Umgesetzt:

```text
backend/services/messaging/
data/messaging/messages.db
```

Regeln:

- Agenten erzeugen fachliche Hinweise ueber den Messaging Service.
- Nutzerrelevante Hinweise erscheinen im Message Center.
- Routine-Erfolgsmeldungen sollen nicht ins Message Center.
- `notification_targets` bleibt die Vorbereitung fuer spaetere Zustellung per Mail, Push oder andere Kanaele.

Offen:

- Echte externe Zustellung an `notification_targets`.
- Eskalationsregeln pro Severity.
- Dedizierte Zustellhistorie fuer Push/Mail.

## Household und Waste

Umgesetzt:

- `backend/services/household_service.py` existiert als Fassade.
- `WasteService` bleibt als eigene Datenquelle erhalten.
- Household-Routen existieren.
- Wall-/HomeAssistant-Kontext kann ueber Household zusammengefuehrt werden.
- Vacation Waste-Hinweise werden auf den Urlaubszeitraum begrenzt und nicht als Termin-Historie in Messages gespammt.
- Offene Tuer-/Fensterkontakte werden ueber Home Assistant erkannt und koennen als Household-Reminder, Message und optional mobile Push-Nachricht gemeldet werden.
- Schlafzimmer-Komfortsteuerung kann regelbasiert und mit optionaler KI-Einschaetzung ueber Home Assistant einen Ventilator schalten; KI steuert nicht direkt.

Zielregel:

- `WasteService` liefert weiterhin alle Waste-Daten.
- Vacation und Household entscheiden, welche Waste-Termine wirklich handlungsrelevant sind.
- Haushaltszustand darf nicht direkt aus UI-Komponenten zusammengesucht werden.
- Comfort-Regeln wie Schlafzimmer-Ventilator gehoeren in Household, bleiben aber regelbasiert und duerfen KI nur beratend verwenden.
- Smart-Home-Schaltungen laufen ausschliesslich ueber Home Assistant und nur nach expliziter regelbasierter Freigabe.

Offen:

- Dedizierte `household.db` nur einfuehren, wenn echte Haushaltsereignisse historisiert werden muessen.
- Wall-Dashboard langfristig weiter auf `HouseholdService.summary()` konsolidieren.
- Comfort-Historie in `household.db` aufnehmen, wenn mehrere Komfortregeln produktiv laufen.
- Zentrale Push-Zustellung ueber `notification_targets`; aktuelle Household-Pushes nutzen noch den konfigurierten Home-Assistant-Notify-Service.

## Context Service

Umgesetzt:

- ContextService als Querschnittsservice unter `backend/services/context/`.
- Eigene SQLite-Persistenz unter `data/context/context.db`.
- API unter `/api/context/status`, `/api/context/history` und `/api/context/debug`.
- Berechnete Zustaende fuer Presence, Garage, House, Vacation und Transition.
- Regelbasierter `DepartureContext` fuer Abfahrt, Kurzabwesenheit und Rueckkehr.
- Regelbasierter Haus-/Schlafkontext, der Uhrzeit nur als ein Signal verwendet.
- Gaeste- und Terrassenkontext blockieren den Nachtkontext.
- Confidence-Wert aus verfuegbaren Signalen und Regelstaerke.
- Debug-Ausgabe mit aktiven Regeln und verwendeten Signalen.

Zielregel:

- Home Assistant bleibt Datenquelle fuer Live-Signale und Geraeteschnittstelle.
- ContextService fuehrt keine Home-Assistant-Service-Calls aus und loest keine Automationen aus.
- Agenten und Scheduler sollen Garagen-, Schlaf- und Hausentscheidungen kuenftig ueber den ContextService treffen, nicht durch eigene Direktinterpretation einzelner HA-Entities.
- Garage-, Jalousien-, Nuki-, Licht- und andere Smart-Home-Aktionen bleiben in den dafuer verantwortlichen Regeln/Automationen und duerfen den ContextService nur lesen.
- KI darf spaeter Kontextmuster erklaeren oder Gewichte vorschlagen, aber die regelbasierte Kontextberechnung nicht ersetzen.

Offen:

- Produktive Entity-Zuordnung pro Installation verfeinern.
- Historische Merkmale fuer Abfahrt, Rueckkehr, Schlafenszeit, Gaestedauer und Aussenaufenthalt aggregieren.
- Spaetere Energy- und Sentero-Kontexte an den ContextService anbinden.

## Garden Agent

Umgesetzt:

- Garden Agent als eigener manifestbasierter Fachagent.
- Eigene Konfiguration unter `backend/agents/garden/config.yaml`.
- Eigene Persistenz unter `data/garden/garden.db`.
- Automatische Home-Assistant-Erkennung fuer `lawn_mower`, Bodenfeuchte-, Bewaesserungs- und Wetter-Entitaeten.
- Regelbasierte Bewertung und Snapshot-Historie.
- Zonenmodell mit `lawn` / `Rasen`.
- Decision Engine mit strukturierten Gruenden und Safety-Blocks.
- Migrationssichere Tabellen fuer Zonen, Entscheidungen, Aktionen und Bewaesserungslaeufe.
- Eve-Aqua-/Bewaesserungsadapter fuer `switch`, `valve` und `input_boolean` ueber Home Assistant.
- Gegenseitige Verriegelung von Mähroboter und Bewaesserung.
- Einmaliges Scheduler-Ausschalten gestarteter Bewaesserungslaeufe ueber generisches Agent-Control `garden/run`.
- Personal Garden Dashboard unter `/garden`.
- Einbindung in Agent-Control mit `status`, `enable`, `disable`, `toggle` und `run`.
- Einbindung in die Agent Map mit Scheduler-, Home-Assistant-, Datenbank- und OpenAI-Bezug.
- Standard-Scheduler-Lauf taeglich um 07:00 Uhr.

Zielregel:

- Garden bleibt der owning Agent fuer Gartenautomatisierung, Mähroboter, Bodenfeuchte, Bewaesserung und Gartenhistorie.
- Household darf Garden-Zusammenfassungen spaeter anzeigen, besitzt aber keine Garten-Fachlogik und keine Gartenhistorie.
- KI darf im Garden-Kontext Empfehlungen, Plaene, Warnungen und Zusammenfassungen erzeugen.
- KI darf keine Geraete direkt steuern und keine Safety-Entscheidung ueberstimmen.
- Automatische Bewaesserung bleibt standardmaessig deaktiviert und wird nur bei `control_enabled: true`, `automatic_enabled: true` und vollstaendiger Safety-Freigabe ausgefuehrt.
- Home Assistant bleibt die einzige Geraeteschnittstelle.
- Kalibrierungs-, Sampling- und Diagnose-Entities duerfen nicht in die fachliche Bewaesserungsentscheidung einfliessen.

Offen:

- Erweiterte Wetterprognose mit echten Forecast-APIs statt nur gebundener Regen-/Wahrscheinlichkeitssensoren.
- Optionale Mähroboter-Start-/Dock-Aktionen ueber offiziell unterstuetzte Home-Assistant-Services.
- Mehrere Gartenzonen produktiv konfigurieren.
- KI-Analyse erst nach stabiler Datensammlung aktivieren.
- Optional Garden-Zusammenfassung im Household-/Wall-Kontext anzeigen.

## Wall und Energie

Umgesetzt:

- Wall Dashboard nutzt fuer den Initial-Render eine schnelle Home-Assistant-Zusammenfassung.
- Sekundaerdaten wie Messages, Garden-Status und schwere Charts werden nachgeladen.
- Wall-Energie-Seite nutzt `/api/homeassistant/energy`.
- EcoTracker, Tageswerte und Phasen werden ausschliesslich ueber Home Assistant gelesen.
- Recharts wird als eigene Lazy-Komponente geladen.
- Die Live-Linie speichert lokal die letzten 60 Minuten, damit ein Seiten-Reload die Kurve nicht sofort leert.

Zielregel:

- Wall enthaelt Darstellung und Bedienung, aber keine Fachlogik.
- Energie V1 bleibt reine Visualisierung; ein Energy Agent ist spaeter moeglich, aber nicht Bestandteil der Wall-Seite.
- Keine direkte Kommunikation mit EcoTracker, Wechselrichtern, Wallboxen oder anderen Energiegeraeten ausserhalb von Home Assistant.
- Performance-relevante Detaildaten duerfen den ersten Wall-Render nicht blockieren.

## Infrastructure Monitoring

Umgesetzt:

```text
backend/services/infrastructure_service.py
backend/services/infrastructure_store.py
backend/api/infrastructure_routes.py
data/infrastructure/infrastructure.db
```

Regeln:

- Home Assistant bleibt Datenquelle.
- Keine direkte FritzBox API in V1.
- Infrastructure ist Service, kein Agent.
- Relevante warning/critical Ereignisse duerfen Messages erzeugen.
- Routine-Health-Check laeuft nicht mehr alle 5 Minuten als Message-Quelle.

Offen:

- Mehr stabile HA-Signale und bessere Aggregationen.
- Optional direkter FritzBox-Zugriff nur als separater Adapter, wenn Home Assistant nicht ausreicht.
- Saubere Push-/Mail-Eskalation fuer kritische Infrastrukturereignisse.

## Update-System

Umgesetzt:

- `/api/system/version`.
- `/api/system/update/check`.
- `/api/system/update/install`.
- `/api/system/update/status`.
- `/api/system/update/rollback`.
- Nutzerfreundliches Update-UI ohne technische Details.
- Admin-/Dev-Details ueber separaten Status.
- ZIP-basierte lokale Updates mit systemd restart fuer RoboterSteve/local_systemd.
- Lokale Update-Manifeste und `latest.json` fuer statischen HTTPS-Update-Server.
- SHA256-Pruefung fuer Release-ZIPs.
- Backups vor Update.
- Audit-Log fuer Update-Aktionen.

Zielregel:

- V1 nutzt keinen Docker-Registry-Updatepfad fuer die Applikation.
- Local/systemd Deployments aktualisieren per ZIP und zeitverzoegertem `systemctl restart`.
- `.env`, `config.yaml`, `data/`, `logs/` und `backups/` werden beim Update nicht ueberschrieben.

Offen fuer Produktreife:

- Kryptographische Signatur der Update-Manifeste oder ZIPs.
- Harter Rollback-Test auf Zielsystemen.
- Update-Server-Konvention fuer RoboterSteve-Releases finalisieren.
- Optionaler Support-Bundle-Export bei fehlgeschlagenen Updates.

# Zielmodelle fuer optionale Persistenz

## household.db

Noch nicht zwingend notwendig. Erst einfuehren, wenn Household mehr als Live-Zusammenfassung/Fassade wird.

Moegliche Tabellen:

- `household_events`
- `household_state`
- `household_reminders`

Zweck:

- Haushaltsereignisse historisieren.
- Livewerte von Home Assistant entkoppeln.
- Erinnerungen nachvollziehbar machen.

## orchestrator.db

Noch nicht umgesetzt und weiterhin optional.

Moegliche Tabellen:

- `agent_registry_snapshot`
- `agent_status_events`
- `agent_runs`
- `orchestrator_events`
- `agent_dependencies`

Zweck:

- Agentenuebergreifende Statushistorie.
- Debugging und Audit fuer Orchestrator-Entscheidungen.
- Grundlage fuer spaetere Abhaengigkeiten und Task-Ketten.

Wichtig:

- `orchestrator.db` darf keine Fachhistorien besitzen.
- Rechnungen, Wellness-Daten, Marktberichte, Vacation-Perioden und Garden-Snapshots bleiben in ihren owning Domains.

# Offene Architekturarbeit

## P1

- Update-Rollback auf echtem lokalem systemd-Zielsystem testen und dokumentieren.
- Messaging-Zustellung an E-Mail/Push als echte Delivery-Schicht implementieren.
- Secrets aus Service-Dateien konsequent entfernen und nur ueber `.env`/Environment laden.

## P2

- Household-Fassade weiter stabilisieren und Wall-Dashboard schrittweise darauf konsolidieren.
- Orchestrator-Statusereignisse entwerfen, bevor `orchestrator.db` eingefuehrt wird.
- Scheduler-Abhaengigkeiten und Task-Ketten fachlich definieren.
- LLM-Factory und Provider-Konfiguration bereinigen.
- Garden um mehrere produktive Zonen, erweiterte Wetterprognosen und optionale Mähroboter-Aktionen erweitern.
- Zentrale Home-Assistant-Service-Schnittstelle weiter pruefen; der alte `HomeAssistantClient` ist nur noch ein Kompatibilitaets-Wrapper.

## P3

- `household.db` einfuehren, falls echte Haushaltsereignisse historisiert werden muessen.
- `orchestrator.db` einfuehren, wenn Statusmodell und Map stabil genug sind.
- Vacation Presence Simulation als separate regelbasierte Engine entwerfen.
- Direkten FritzBox-Adapter nur bei nachgewiesenem Bedarf ergaenzen.
- Update-Signaturen und Update-Server-Hardening fuer kommerzielle Auslieferung umsetzen.

# Nicht-Ziele

- Keine ausgelagerten Produkte wieder in dieses Repo zurueckziehen.
- Keine privaten Daten, Logs oder Secrets in Builds oder Update-ZIPs.
- Kein `docker restart` als Standard-Updatepfad.
- Keine KI- oder Agent-Komponente steuert direkt Smart-Home-Geraete ohne regelbasierte Freigabe.
