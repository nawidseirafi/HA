# RoboterSteve Dokumentation

Diese Dokumentation ist nach Zweck getrennt. Fuer konkrete Deployments und Updates sind die Betriebsdokumente die Quelle der Wahrheit.

## Betriebsdokumente

- `DEPLOYMENT.md`: Installation, RoboterSteve/systemd, Betrieb und Fehleranalyse.
- `UPDATE_SYSTEM.md`: Update Engine V1, statischer HTTPS-Update-Server, ZIP-Releases, local/systemd und ZIP-Docker Updates.

## Architektur

- `ARCHITECTURE.md`: aktueller Ist-Zustand der Anwendung.
- `ARCHITECTURE_TARGET.md`: Zielbild und Leitlinien fuer weitere Entwicklung.

Aktuell wichtige Fachagenten der Personal Edition:

- Scheduler: zentrale Zeitsteuerung.
- Invoice, Market, MyWellness und Vacation: bestehende Fachagenten.
- Garden: Garten-Agent fuer Mähroboter, Bodenfeuchte, Bewaesserung und Wetter. Der Agent sammelt Snapshots, speichert Entscheidungen und kann Bewaesserung nur nach regelbasierter Safety-Freigabe ueber Home Assistant steuern. Automatik ist standardmaessig aus; KI steuert keine Geraete direkt.

## Konsolidierte Dokumente

- `docker_create.md`: veraltete Proxmox-/Docker-Einzelanleitung. Inhalt wurde auf einen Verweis reduziert; der aktuelle Standard fuer RoboterSteve ist das systemd-Deployment in `DEPLOYMENT.md`.

## Aktuelle Deployment-Regeln

```text
RoboterSteve = build/robotersteve + systemd + UPDATE_EXECUTION_MODE=local_systemd
Update-Server Upload = build/updates/robotersteve/stable/
```

Docker-Updates verwenden `docker compose up -d --build`. `docker restart` ist kein Standard-Updatepfad.
