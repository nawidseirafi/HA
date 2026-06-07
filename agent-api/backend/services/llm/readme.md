# LLM Service

Der LLM-Service ist ein Core-Baustein und kann von mehreren RoboterSteve Editionen genutzt werden.

## Entwicklung

```bash
cd agent-api
../venv/bin/python -m pip install -r requirements.txt
```

## Editionen

- `personal` kann OpenAI, Gemini oder lokale Llama/Ollama-Modelle verwenden.
- `seniorcare` ist fuer lokale/produktnahe Deployments vorbereitet und nutzt im Beispiel `llm.provider: llama` mit Ollama.

Secrets gehoeren in `.env` oder die Zielumgebung, nicht in README-Dateien oder Edition-Builds.
