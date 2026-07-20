Suchen nach	Was es ist
Mushroom	Mushroom-Karten
Mushroom Themes	passendes dunkles Theme
mini-graph-card	Strom-Graph
auto-entities	Listen automatisch befüllen
button-card	individuelle Buttons
layout-card	Spaltenlayout
card-mod	CSS-Styling (wichtig fürs Mockup-Look)
kiosk-mode	Sidebar/Header verstecken am iPad

RoboterSteve Wall Dashboard
- Wall Dashboard bleibt minimal: Hausstatus, Vacation Mode, Message-Glocke.
- Vollständige Nachrichtenverwaltung liegt in der Agent Console unter /agents/messages.
- FritzBox/Internet-Kachel soll Daten aus dem Infrastructure Service nutzen, nicht direkt aus FritzBox-APIs.
- Vacation-Kachel steuert nur input_boolean.vacation_mode.
- Keine Geräteautomatisierung durch Vacation oder Infrastructure Service.

RoboterSteve-Hinweis
- Das bestehende Wall Dashboard gehoert zur Personal App unter frontend/src/apps/personal.
- Gemeinsame API/Auth/Styles liegen unter frontend/src/shared.
- Smart-Home-Logik bleibt im Backend und wird nicht in Home-Assistant-Dashboard-Karten dupliziert.
