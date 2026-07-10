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

The Garden Agent is currently an advisory agent. It reads compatible Home Assistant entities such as `lawn_mower.*`, soil moisture sensors, irrigation switches/valves and weather entities, stores snapshots in its own database and produces rule-based recommendations. It is prepared for later AI analysis, but it does not automatically control irrigation or mower devices yet.
