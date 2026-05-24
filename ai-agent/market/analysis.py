import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


AI_AGENT_DIR = Path(__file__).resolve().parents[1]
AGENT_CONFIG_PATH = AI_AGENT_DIR / "config.yaml"
ALLOWED_SIGNALS = {"bullish", "neutral", "bearish", "watch"}


class MarketAnalysisService:
    def analyze(self, watchlist_item: dict[str, Any], quote: dict[str, Any], news: list[dict[str, Any]]) -> dict[str, Any]:
        raw = self._llm_analysis(watchlist_item, quote, news)
        validated = self._validate(raw, watchlist_item["symbol"])
        validated["analysis_source"] = "llm"
        validated["analysis_error"] = ""
        return validated

    def _llm_analysis(self, watchlist_item: dict[str, Any], quote: dict[str, Any], news: list[dict[str, Any]]) -> dict[str, Any]:
        if not AGENT_CONFIG_PATH.exists():
            raise RuntimeError("ai-agent/config.yaml nicht gefunden")
        if str(AI_AGENT_DIR) not in sys.path:
            sys.path.insert(0, str(AI_AGENT_DIR))
        from llm import create_llm_client  # type: ignore

        config = yaml.safe_load(AGENT_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        llm_config = config.get("llm", {})
        if not llm_config:
            raise RuntimeError("keine LLM-Konfiguration vorhanden")
        client = create_llm_client({"llm": llm_config})
        response = client.generate(prompt=self._prompt(watchlist_item, quote, news), system=SYSTEM_PROMPT)
        return self._extract_json(response.text)

    def _validate(self, data: dict[str, Any], symbol: str) -> dict[str, Any]:
        signal = str(data.get("signal", "watch")).lower()
        if signal not in ALLOWED_SIGNALS:
            raise ValueError(f"Ungueltiges Signal: {signal}")
        confidence = float(data.get("confidence", 0))
        if confidence < 0 or confidence > 1:
            raise ValueError("Confidence muss zwischen 0 und 1 liegen.")
        return {
            "symbol": str(data.get("symbol") or symbol).upper(),
            "signal": signal,
            "confidence": confidence,
            "summary": str(data.get("summary") or ""),
            "positive_factors": self._list(data.get("positive_factors")),
            "negative_factors": self._list(data.get("negative_factors")),
            "risk_factors": self._list(data.get("risk_factors")),
            "news_summary": str(data.get("news_summary") or ""),
            "not_financial_advice": bool(data.get("not_financial_advice", True)),
        }

    def _extract_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)
        return json.loads(cleaned)

    def _list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if value:
            return [str(value)]
        return []

    def _prompt(self, watchlist_item: dict[str, Any], quote: dict[str, Any], news: list[dict[str, Any]]) -> str:
        return json.dumps(
            {
                "task": "Analysiere Markt- und Nachrichtenlage. Keine Kauf-/Verkaufsempfehlung.",
                "watchlist_item": watchlist_item,
                "quote": quote,
                "news": news,
                "required_json": {
                    "symbol": watchlist_item["symbol"],
                    "signal": "bullish | neutral | bearish | watch",
                    "confidence": 0.0,
                    "summary": "...",
                    "positive_factors": ["..."],
                    "negative_factors": ["..."],
                    "risk_factors": ["..."],
                    "news_summary": "...",
                    "not_financial_advice": True,
                },
            },
            ensure_ascii=False,
        )


SYSTEM_PROMPT = """
Du bist MarketAgent in RoboterSteve. Erzeuge ausschliesslich valides JSON.
Keine Finanzberatung, keine absoluten Kauf-/Verkaufsempfehlungen, keine Broker- oder Order-Anweisungen.
Erlaubte Signale sind nur: bullish, neutral, bearish, watch.
""".strip()
