# RoboterSteve Dokumentation

Diese Dokumentation ist nach Zweck getrennt. Fuer konkrete Deployments und Updates sind die Betriebsdokumente die Quelle der Wahrheit.

## Betriebsdokumente

- `DEPLOYMENT.md`: Installation, Edition-Builds, Personal/systemd, Sentero/Docker, Betrieb und Fehleranalyse.
- `UPDATE_SYSTEM.md`: Update Engine V1, statischer HTTPS-Update-Server, ZIP-Releases, local/systemd und ZIP-Docker Updates.

## Architektur

- `ARCHITECTURE.md`: aktueller Ist-Zustand der Anwendung.
- `ARCHITECTURE_TARGET.md`: Zielbild und Leitlinien fuer weitere Entwicklung.

## Konsolidierte Dokumente

- `docker_create.md`: veraltete Proxmox-/Docker-Einzelanleitung. Inhalt wurde auf einen Verweis reduziert; aktuelle Sentero-Docker-Schritte stehen in `DEPLOYMENT.md`.

## Aktuelle Deployment-Regeln

```text
Personal = build/personal + systemd + UPDATE_EXECUTION_MODE=local_systemd
Sentero = build/sentero + Docker Compose + UPDATE_EXECUTION_MODE=zip_docker
Update-Server Upload = build/updates/<edition>/stable/
```

Docker-Updates verwenden `docker compose up -d --build`. `docker restart` ist kein Standard-Updatepfad.
