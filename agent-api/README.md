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

## Telegram Chat

Roboter Steve can run a private Telegram chat agent. The agent polls Telegram with `getUpdates`, accepts only configured chat IDs, stores processed update offsets in `data/telegram/telegram.db`, and answers read-only status questions through the configured LLM provider. It does not execute device actions from Telegram.

Setup:

- Create a bot with BotFather and either enter the token on `/telegram` or set `TELEGRAM_BOT_TOKEN` in `agent-api/.env`.
- Open the Telegram Agent card or `/telegram` to see whether the token is configured and to get the bot link/QR code.
- Send a message to the bot, then call `GET /api/telegram/discover-chats` to see the numeric chat ID. Set it as `TELEGRAM_CHAT_ID` in `agent-api/.env` or add it to `backend/agents/telegram/config.yaml` under `allowed_chat_ids`.
- On `/telegram`, discover chats and save the chat ID, or set `backend/agents/telegram/config.yaml` `allowed_chat_ids` manually.
- Enable or disable the chat agent on `/telegram`.
- Restart the backend. Use `POST /api/telegram/test` to send a test message.
