# Abfall Widget für Home Assistant

Dieses Widget zeigt die nächsten Abfalltermine in Home Assistant an.

## Dateien

- `abfall_widget.py` - Python-Script zum Auslesen der Termine aus der PLIST-Datei
- `abfall_dashboard.yaml` - Dashboard-Konfiguration für HA
- `abfall_automation.yaml` - Automationen und Template-Sensoren

## Installation

### 1. Python-Script in HA installieren

Kopiere `abfall_widget.py` in das HA python_scripts Verzeichnis:
```
/config/python_scripts/abfall_widget.py
```

Stelle sicher, dass Python-Scripts in der HA `configuration.yaml` aktiviert sind:
```yaml
python_script:
```

### 2. Automationen integrieren

Kopiere den Inhalt von `abfall_automation.yaml` in deine `automations.yaml`:
```yaml
# Automationen Abfall
automation: !include abfall_automation.yaml
```

Oder füge die Automationen direkt in deine bestehende `automations.yaml` ein.

### 3. Dashboard erstellen

In Home Assistant:
1. Gehe zu Einstellungen → Dashboards
2. Erstelle ein neues Dashboard
3. Wechsle in den Code-Editor (3 Punkte Menü → Raw Configuration bearbeiten)
4. Kopiere den Inhalt von `abfall_dashboard.yaml`

Oder importiere als YAML-Datei:
```yaml
- url: /local/dashboards/abfall.yaml
  filename: abfall.yaml
  title: Abfalltermine
  icon: mdi:trash-can
  show_in_sidebar: true
  require_admin: false
```

## Features

- ✅ Zeigt nächsten Abfalltermin an
- ✅ Übersicht aller Termine für 14 Tage
- ✅ Automatische Benachrichtigungen 24h vor Termin
- ✅ Einfache, übersichtliche Darstellung
- ✅ Farbcodierung nach Abfalltyp

## Terminte (anonymisiert)

- Freitag, 8. Mai: Gelber Sack + Bioabfall
- Dienstag, 12. Mai: Sperrabfall
- Samstag, 16. Mai: Restabfall + Bioabfall + Metall
- Freitag, 22. Mai: Papier + Bioabfall
- Samstag, 30. Mai: Restabfall + Bioabfall + Metall
- ... und weitere

## Customization

### Benachrichtigungstext ändern

Bearbeite in `abfall_automation.yaml` die Benachrichtigungen:
```yaml
- service: notify.notify
  data:
    title: "Dein Text hier"
    message: "Deine Nachricht"
```

### Farben anpassen

Im Dashboard YAML kannst du die Emojis/Farben ändern:
- 🟨 Gelb = Gelber Sack
- ⬛ Schwarz = Sperrabfall
- 🟫 Braun = Bioabfall
- Etc.

## Troubleshooting

**Widget zeigt "Keine Termine"?**
- Prüfe, ob die PLIST-Datei vorhanden ist
- Verifiziere den Dateipfad in den Scripts

**Benachrichtigungen funktionieren nicht?**
- Prüfe HA Logs auf Fehler
- Stelle sicher, dass Notifications konfiguriert sind

**Script funktioniert nicht?**
- Prüfe die HA python_scripts Dokumentation
- Verifiziere die Python-Version (3.7+)
