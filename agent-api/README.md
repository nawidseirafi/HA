# RoboterSteve

Standalone deployment package for RoboterSteve.

This package is built as a single RoboterSteve product.

## Contents

- `backend/`: FastAPI backend
- `frontend/dist/`: built frontend
- `requirements.txt`: Python dependencies
- `config.example.yaml`: configuration template
- `.env.example`: environment template
- `README_INSTALL.md`: installation notes

## Personal Edition Agents

The Personal edition includes manifest-based agents for invoices, market monitoring, MyWellness, vacation handling, scheduling and garden automation.

The Garden Agent owns lawn, soil moisture, irrigation, mower and garden-history logic. It reads compatible Home Assistant entities such as `lawn_mower.*`, soil moisture sensors, irrigation switches/valves and weather entities, stores snapshots and decisions in `garden.db`, and evaluates each garden zone with rule-based safety checks. Irrigation can be started manually through the Garden API and can run automatically only when the global control flag, the zone automation flag and every safety rule allow it. Automation is disabled by default. AI may explain or summarize Garden recommendations later, but it never controls devices directly.

Wall includes a Home-Assistant-backed Energy page for EcoTracker-style power sensors and utility-meter daily values. Wall does not talk to meters or devices directly; all data comes through the backend Home Assistant service.
