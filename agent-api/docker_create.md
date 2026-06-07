# SeniorCare Deployment auf Proxmox (Docker + LXC)

## Ziel

Diese Anleitung beschreibt die vollständige Einrichtung einer SeniorCare-Testumgebung auf Proxmox.

Ergebnis:

- Debian 12 LXC Container
- Docker
- Docker Compose
- Ollama
- RoboterSteve API
- Zugriff über Browser

---

# 1. LXC Container erstellen

## Proxmox

Create CT

### General

text Hostname: seniorcare Unprivileged Container: aktiviert Nesting: aktiviert 

### Template

text debian-12-standard 

### Disk

text 40 GB 

### CPU

text 2 Cores 

### Memory

text 4096 MB RAM 1024 MB Swap 

### Network

text Bridge: vmbr0 IPv4: DHCP IPv6: DHCP 

### DNS

text Use host settings 

Container erstellen und starten.

---

# 2. Container öffnen

Auf dem Proxmox Host:

bash pct enter 102 

oder über die Container-Konsole.

---

# 3. Debian aktualisieren

bash apt update apt upgrade -y 

Hilfspakete:

bash apt install -y curl git rsync sudo openssh-server 

SSH prüfen:

bash systemctl status ssh 

---

# 4. Docker installieren

bash curl -fsSL https://get.docker.com | sh 

Prüfen:

bash docker --version docker compose version 

Beispiel:

text Docker version 29.x Docker Compose version v5.x 

---

# 5. Container-IP ermitteln

bash hostname -I 

Beispiel:

text 192.168.178.64 

Diese IP wird später im Browser verwendet.

---

# 6. Deployment-Verzeichnis anlegen

bash mkdir -p /opt/seniorcare cd /opt/seniorcare 

---

# 7. SeniorCare Build übertragen

Vom Entwicklungsrechner:

bash rsync -av build/seniorcare/ root@192.168.178.64:/opt/seniorcare/ 

Alternativ:

bash scp -r build/seniorcare/* root@192.168.178.64:/opt/seniorcare/ 

---

# 8. Deployment prüfen

Im Container:

bash cd /opt/seniorcare ls -la 

Wichtige Dateien:

text docker-compose.yml requirements.txt backend/ frontend/ config/ 

---

# 9. Docker Container starten

bash cd /opt/seniorcare  docker compose up -d 

Container prüfen:

bash docker ps 

Beispiel:

text seniorcare-robotersteve-api-1 seniorcare-ollama-1 

---

# 10. Logs prüfen

API:

bash docker logs seniorcare-robotersteve-api-1 

Live:

bash docker logs -f seniorcare-robotersteve-api-1 

Compose:

bash docker compose logs 

---

# 11. Browser-Test

Health:

text http://192.168.178.64:8080/health 

Swagger:

text http://192.168.178.64:8080/docs 

Frontend:

text http://192.168.178.64:8080 

---

# 12. Container neu starten

Gesamtes Deployment:

bash docker compose down docker compose up -d 

Nur API:

bash docker restart seniorcare-robotersteve-api-1 

Nur Ollama:

bash docker restart seniorcare-ollama-1 

---

# 13. Fehleranalyse

Container läuft nicht:

bash docker ps -a 

Logs:

bash docker logs seniorcare-robotersteve-api-1 

Compose Logs:

bash docker compose logs 

Offene Ports:

bash ss -tulpn 

---

# 14. Updates

Deployment aktualisieren:

bash docker compose down 

Neue Build-Dateien übertragen:

bash rsync -av build/seniorcare/ root@SERVER:/opt/seniorcare/ 

Neustart:

bash docker compose up -d 

---

# Aktuelle Architektur

text Proxmox └── LXC Container (Debian 12)     ├── Docker     ├── Ollama     ├── RoboterSteve API     └── SeniorCare Frontend 

Zugriff:

text Browser ↓ http://<IP>:8080 ↓ RoboterSteve API ↓ SeniorCare Edition ↓ Ollama 