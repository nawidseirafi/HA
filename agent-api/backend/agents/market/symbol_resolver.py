import json
import re
import sys
from typing import Any

from backend.config import load_global_config
from backend.paths import API_DIR


class MarketSymbolResolver:
    def resolve(self, requested_symbol: str, watchlist_item: dict[str, Any]) -> dict[str, Any] | None:
        candidates = self.resolve_candidates(requested_symbol, watchlist_item)
        return candidates[0] if candidates else None

    def resolve_candidates(self, requested_symbol: str, watchlist_item: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = self._known_candidates(requested_symbol)
        try:
            llm_candidate = self._llm_candidate(requested_symbol, watchlist_item)
        except Exception:
            llm_candidate = None
        if llm_candidate:
            candidates.append(llm_candidate)
        return self._dedupe(candidates)

    def _known_candidates(self, requested_symbol: str) -> list[dict[str, Any]]:
        aliases = {
            "A3DP9J": [
                ("JEDI.L", 0.95, "WKN A3DP9J: VanEck Space Innovators UCITS ETF, Yahoo London"),
                ("JEDI.MI", 0.8, "WKN A3DP9J: VanEck Space Innovators UCITS ETF, Yahoo Mailand"),
                ("JEDI.SW", 0.8, "WKN A3DP9J: VanEck Space Innovators UCITS ETF, Yahoo Schweiz"),
            ],
        }
        return [
            {"yahoo_symbol": symbol, "confidence": confidence, "reason": reason}
            for symbol, confidence, reason in aliases.get(requested_symbol.strip().upper(), [])
        ]

    def _llm_candidate(self, requested_symbol: str, watchlist_item: dict[str, Any]) -> dict[str, Any] | None:
        if not API_DIR.exists():
            return None
        if str(API_DIR) not in sys.path:
            sys.path.insert(0, str(API_DIR))

        from backend.services.llm.factory import create_llm_client

        config = load_global_config()
        llm_config = config.get("llm", {})
        if not llm_config:
            return None

        client = create_llm_client()
        response = client.generate(
            prompt=self._prompt(requested_symbol, watchlist_item),
            system=SYSTEM_PROMPT,
        )
        return self._validate(self._extract_json(response.text))

    def _dedupe(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for candidate in sorted(candidates, key=lambda item: item.get("confidence", 0), reverse=True):
            symbol = str(candidate.get("yahoo_symbol") or "").upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            unique.append(candidate)
        return unique

    def _prompt(self, requested_symbol: str, watchlist_item: dict[str, Any]) -> str:
        return json.dumps(
            {
                "task": "Finde den wahrscheinlich passenden Yahoo-Finance-Ticker fuer das Wertpapier.",
                "requested_symbol": requested_symbol,
                "watchlist_item": watchlist_item,
                "hints": [
                    "Deutsche WKNs wie A3DP9J sind keine Yahoo-Finance-Ticker.",
                    "Nutze Yahoo-Suffixe wie .DE, .F, .L, .PA, .MI, .SW, wenn noetig.",
                    "Wenn du unsicher bist, gib null als yahoo_symbol zurueck.",
                ],
                "required_json": {
                    "yahoo_symbol": "AAPL | JEDI.L | null",
                    "confidence": 0.0,
                    "reason": "kurze Begruendung",
                },
            },
            ensure_ascii=False,
        )

    def _extract_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)
        return json.loads(cleaned)

    def _validate(self, data: dict[str, Any]) -> dict[str, Any] | None:
        symbol = data.get("yahoo_symbol")
        if symbol is None:
            return None
        symbol = str(symbol).strip().upper()
        if not symbol or symbol == "NULL":
            return None
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,20}", symbol):
            return None
        confidence = float(data.get("confidence") or 0)
        if confidence < 0.5:
            return None
        return {
            "yahoo_symbol": symbol,
            "confidence": min(confidence, 1.0),
            "reason": str(data.get("reason") or ""),
        }


SYSTEM_PROMPT = """
Du bist ein Symbol-Resolver fuer MarketAgent. Antworte ausschliesslich mit validem JSON.
Gesucht ist ein Yahoo-Finance-Ticker, keine Anlageberatung und keine Marktanalyse.
Wenn das Symbol nicht verlaesslich bestimmbar ist, gib yahoo_symbol null zurueck.
""".strip()
