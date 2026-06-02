import json
import re
import sys
from typing import Any
from backend.services.llm.factory import create_llm_client
import yaml
from backend.paths import API_CONFIG_PATH

ALLOWED_RECOMMENDATIONS = {"buy", "hold", "sell", "watch"}
ALLOWED_RISK_LEVELS = {"low", "medium", "high"}
ALLOWED_TIME_HORIZONS = {"short", "medium", "long"}


class MarketAnalysisService:
    def analyze(self, watchlist_item: dict[str, Any], quote: dict[str, Any], news: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            raw = self._llm_analysis(watchlist_item, quote, news)
            validated = self._validate(raw, watchlist_item["symbol"])
            validated["analysis_source"] = "llm"
            validated["analysis_error"] = ""
            return validated
        except Exception as exc:
            fallback = self._heuristic_analysis(watchlist_item, quote, news)
            fallback["analysis_source"] = "heuristic"
            fallback["analysis_error"] = str(exc)
            return fallback

    def _llm_analysis(self, watchlist_item: dict[str, Any], quote: dict[str, Any], news: list[dict[str, Any]]) -> dict[str, Any]:
        if not API_CONFIG_PATH.exists():
            raise RuntimeError("config.yaml nicht gefunden")
        if str(API_CONFIG_PATH) not in sys.path:
            sys.path.insert(0, str(API_CONFIG_PATH))

        config = yaml.safe_load(API_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        llm_config = config.get("llm", {})
        if not llm_config:
            raise RuntimeError("keine LLM-Konfiguration vorhanden")
        client = create_llm_client()
        response = client.generate(prompt=self._prompt(watchlist_item, quote, news), system=SYSTEM_PROMPT)
        return self._extract_json(response.text)

    def _validate(self, data: dict[str, Any], symbol: str) -> dict[str, Any]:
        recommendation = str(data.get("recommendation") or data.get("signal") or "watch").lower()
        if recommendation not in ALLOWED_RECOMMENDATIONS:
            raise ValueError(f"Ungueltige Empfehlung: {recommendation}")
        confidence = float(data.get("confidence", 0))
        if confidence <= 1:
            confidence *= 100
        confidence = max(0, min(confidence, 100))
        risk_level = str(data.get("risk_level") or "medium").lower()
        if risk_level not in ALLOWED_RISK_LEVELS:
            risk_level = "medium"
        time_horizon = str(data.get("time_horizon") or "medium").lower()
        if time_horizon not in ALLOWED_TIME_HORIZONS:
            time_horizon = "medium"
        summary = self._compact(str(data.get("summary") or "Marktsignal wird weiter beobachtet."))
        return {
            "symbol": str(data.get("symbol") or symbol).upper(),
            "signal": recommendation,
            "recommendation": recommendation,
            "confidence": confidence,
            "risk_level": risk_level,
            "summary": summary,
            "reasoning": str(data.get("reasoning") or ""),
            "positive_factors": self._list(data.get("positive_factors")),
            "negative_factors": self._list(data.get("negative_factors")),
            "risk_factors": self._list(data.get("risk_factors") or data.get("negative_factors")),
            "news_summary": self._compact(str(data.get("news_summary") or "")),
            "time_horizon": time_horizon,
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

    def _compact(self, value: str, max_length: int = 150) -> str:
        text = re.sub(r"\s+", " ", value).strip()
        if len(text) <= max_length:
            return text
        return text[: max_length - 1].rstrip(" .,;:") + "."

    def _prompt(self, watchlist_item: dict[str, Any], quote: dict[str, Any], news: list[dict[str, Any]]) -> str:
        return json.dumps(
            {
                "task": "Analysiere Markt- und Nachrichtenlage als unverbindliches Marktsignal.",
                "watchlist_item": watchlist_item,
                "quote": quote,
                "news": news,
                "required_json": {
                    "symbol": watchlist_item["symbol"],
                    "recommendation": "buy | hold | sell | watch",
                    "confidence": 0,
                    "risk_level": "low | medium | high",
                    "summary": "maximal 150 Zeichen, 1 bis 2 Saetze",
                    "reasoning": "kurze Begruendung",
                    "positive_factors": ["..."],
                    "negative_factors": ["..."],
                    "time_horizon": "short | medium | long",
                    "not_financial_advice": True,
                },
            },
            ensure_ascii=False,
        )

    def _heuristic_analysis(self, watchlist_item: dict[str, Any], quote: dict[str, Any], news: list[dict[str, Any]]) -> dict[str, Any]:
        performance = quote.get("performance") or {}
        technical = quote.get("technical") or {}
        change_30d = float(performance.get("30d") or quote.get("change_percent") or 0)
        change_1y = float(performance.get("1y") or 0)
        volatility = technical.get("volatility")
        positive_news = len([item for item in news if item.get("sentiment") in {"bullish", "positive"}])
        negative_news = len([item for item in news if item.get("sentiment") in {"bearish", "negative"}])
        score = 50 + min(max(change_30d, -20), 20) + min(max(change_1y / 2, -15), 15) + (positive_news - negative_news) * 4
        recommendation = "hold"
        if score >= 76:
            recommendation = "buy"
        elif score >= 58:
            recommendation = "watch"
        elif score <= 42:
            recommendation = "sell"
        risk_level = "medium"
        if isinstance(volatility, (int, float)):
            if volatility < 18:
                risk_level = "low"
            elif volatility > 35:
                risk_level = "high"
        summary_by_recommendation = {
            "buy": "Positiver Trend mit stabilem Marktsignal.",
            "watch": "Interessantes Signal, aber der Einstieg sollte beobachtet werden.",
            "hold": "Aktuell neutrales Signal ohne klaren Handlungsdruck.",
            "sell": "Schwacher Trend und erhoehtes Risiko sprechen gegen Zukauf.",
        }
        return {
            "symbol": str(watchlist_item.get("symbol") or quote.get("symbol") or "").upper(),
            "signal": recommendation,
            "recommendation": recommendation,
            "confidence": round(max(0, min(score, 100))),
            "risk_level": risk_level,
            "summary": summary_by_recommendation[recommendation],
            "reasoning": f"30D {change_30d:.1f}%, 1Y {change_1y:.1f}%, News-Saldo {positive_news - negative_news}.",
            "positive_factors": self._heuristic_factors(change_30d, change_1y, positive_news, positive=True),
            "negative_factors": self._heuristic_factors(change_30d, change_1y, negative_news, positive=False),
            "risk_factors": [f"Volatilitaet {volatility}%"] if isinstance(volatility, (int, float)) and volatility > 30 else [],
            "news_summary": "",
            "time_horizon": "medium",
            "not_financial_advice": True,
        }

    def _heuristic_factors(self, change_30d: float, change_1y: float, news_count: int, positive: bool) -> list[str]:
        factors: list[str] = []
        if positive:
            if change_30d > 5:
                factors.append("Positiver 30-Tage-Trend")
            if change_1y > 10:
                factors.append("Positive Jahresentwicklung")
            if news_count:
                factors.append("Positive Nachrichtenlage")
        else:
            if change_30d < -5:
                factors.append("Negativer 30-Tage-Trend")
            if change_1y < -10:
                factors.append("Schwache Jahresentwicklung")
            if news_count:
                factors.append("Negative Nachrichtenlage")
        return factors


SYSTEM_PROMPT = """
Du bist MarketAgent in RoboterSteve. Erzeuge ausschliesslich valides JSON.
Keine Finanzberatung, keine absoluten Kauf-/Verkaufsempfehlungen, keine Broker- oder Order-Anweisungen.
Formuliere ausschliesslich Marktbeobachtungen und Signale, nicht als verbindliche Handlung.
Erlaubte Empfehlungen sind nur: buy, hold, sell, watch.
Erlaubte Risiken sind nur: low, medium, high.
Die Summary muss kompakt bleiben: maximal 1 bis 2 Saetze und maximal etwa 150 Zeichen.
""".strip()
