# Sentero Docker Deployment

Diese Datei ist bewusst nur noch ein Verweis.

Die fruehere Proxmox-/Docker-Einzelanleitung war veraltet und enthielt alte Restart-Kommandos wie `docker restart`. Die aktuelle, getestete Anleitung steht zentral in:

- `docs/DEPLOYMENT.md` unter `Sentero ZIP-Docker Deployment V1`
- `docs/UPDATE_SYSTEM.md` fuer ZIP-basierte Updates ohne Docker Registry

Aktueller V1-Standard:

```text
Sentero Docker Update = ZIP herunterladen + Dateien aktualisieren + docker compose up -d --build
```

Kein `docker restart` als Standard.
