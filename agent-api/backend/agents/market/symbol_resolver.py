import json
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

from backend.config import load_global_config
from backend.paths import API_DIR


class MarketSymbolResolver:
    def resolve_asset(self, raw_input: str) -> dict[str, Any]:
        query = raw_input.strip()
        if not query:
            raise ValueError("Bitte Name, Symbol, ISIN oder WKN eingeben.")
        known = self._known_asset(query)
        if known:
            return known
        yahoo = self._yahoo_search_asset(query)
        if yahoo:
            return yahoo
        llm_candidate = self._llm_asset(query)
        if llm_candidate:
            return llm_candidate
        normalized = query.upper()
        if re.fullmatch(r"[A-Z0-9.-]{1,20}", normalized):
            return {
                "input_name": query,
                "resolved_name": normalized,
                "name": normalized,
                "symbol": normalized,
                "isin": query.upper() if self._looks_like_isin(query) else "",
                "wkn": query.upper() if self._looks_like_wkn(query) else "",
                "asset_type": self._infer_asset_type(query, normalized),
                "exchange": "",
                "currency": "USD",
            }
        raise ValueError("Asset konnte nicht aufgeloest werden.")

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

    def _known_asset(self, query: str) -> dict[str, Any] | None:
        key = re.sub(r"\s+", " ", query.strip()).upper()
        known: dict[str, dict[str, Any]] = {
            "APPLE": {"name": "Apple Inc.", "symbol": "AAPL", "isin": "US0378331005", "wkn": "865985", "asset_type": "stock", "exchange": "NASDAQ", "currency": "USD"},
            "AAPL": {"name": "Apple Inc.", "symbol": "AAPL", "isin": "US0378331005", "wkn": "865985", "asset_type": "stock", "exchange": "NASDAQ", "currency": "USD"},
            "US0378331005": {"name": "Apple Inc.", "symbol": "AAPL", "isin": "US0378331005", "wkn": "865985", "asset_type": "stock", "exchange": "NASDAQ", "currency": "USD"},
            "865985": {"name": "Apple Inc.", "symbol": "AAPL", "isin": "US0378331005", "wkn": "865985", "asset_type": "stock", "exchange": "NASDAQ", "currency": "USD"},
            "MICROSOFT": {"name": "Microsoft Corporation", "symbol": "MSFT", "isin": "US5949181045", "asset_type": "stock", "exchange": "NASDAQ", "currency": "USD"},
            "MSFT": {"name": "Microsoft Corporation", "symbol": "MSFT", "isin": "US5949181045", "asset_type": "stock", "exchange": "NASDAQ", "currency": "USD"},
            "TESLA": {"name": "Tesla, Inc.", "symbol": "TSLA", "isin": "US88160R1014", "asset_type": "stock", "exchange": "NASDAQ", "currency": "USD"},
            "TSLA": {"name": "Tesla, Inc.", "symbol": "TSLA", "isin": "US88160R1014", "asset_type": "stock", "exchange": "NASDAQ", "currency": "USD"},
            "NVIDIA": {"name": "NVIDIA Corporation", "symbol": "NVDA", "isin": "US67066G1040", "asset_type": "stock", "exchange": "NASDAQ", "currency": "USD"},
            "NVDA": {"name": "NVIDIA Corporation", "symbol": "NVDA", "isin": "US67066G1040", "asset_type": "stock", "exchange": "NASDAQ", "currency": "USD"},
            "MSCI WORLD": {"name": "iShares Core MSCI World UCITS ETF", "symbol": "EUNL.DE", "isin": "IE00B4L5Y983", "wkn": "A0RPWH", "asset_type": "etf", "exchange": "XETRA", "currency": "EUR"},
            "S&P 500 ETF": {"name": "Vanguard S&P 500 UCITS ETF", "symbol": "VUAA.DE", "isin": "IE00BFMXXD54", "asset_type": "etf", "exchange": "XETRA", "currency": "EUR"},
            "NASDAQ ETF": {"name": "Invesco EQQQ Nasdaq-100 UCITS ETF", "symbol": "EQQQ.DE", "isin": "IE0032077012", "asset_type": "etf", "exchange": "XETRA", "currency": "EUR"},
            "VANGUARD FTSE ALL WORLD": {"name": "Vanguard FTSE All-World UCITS ETF", "symbol": "VWCE.DE", "isin": "IE00BK5BQT80", "wkn": "A2PKXG", "asset_type": "etf", "exchange": "XETRA", "currency": "EUR"},
            "BITCOIN": {"name": "Bitcoin", "symbol": "BTC-USD", "isin": "", "asset_type": "crypto", "exchange": "Crypto", "currency": "USD"},
            "BTC": {"name": "Bitcoin", "symbol": "BTC-USD", "isin": "", "asset_type": "crypto", "exchange": "Crypto", "currency": "USD"},
        }
        asset = known.get(key)
        if not asset:
            return None
        return {
            "input_name": query,
            "resolved_name": asset["name"],
            **asset,
        }

    def _yahoo_search_asset(self, query: str) -> dict[str, Any] | None:
        encoded = urllib.parse.quote(query)
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={encoded}&quotesCount=8&newsCount=0"
        request = urllib.request.Request(url, headers={"User-Agent": "RoboterSteve/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None
        quotes = payload.get("quotes") or []
        for quote in quotes:
            symbol = str(quote.get("symbol") or "").strip().upper()
            quote_type = str(quote.get("quoteType") or "").lower()
            if not symbol or quote_type in {"option", "future"}:
                continue
            asset_type = self._asset_type_from_quote_type(quote_type, symbol)
            return {
                "input_name": query,
                "resolved_name": str(quote.get("longname") or quote.get("shortname") or symbol),
                "name": str(quote.get("longname") or quote.get("shortname") or symbol),
                "symbol": symbol,
                "isin": query.upper() if self._looks_like_isin(query) else "",
                "wkn": query.upper() if self._looks_like_wkn(query) else "",
                "asset_type": asset_type,
                "exchange": str(quote.get("exchDisp") or quote.get("exchange") or ""),
                "currency": str(quote.get("currency") or "USD").upper(),
            }
        return None

    def _llm_asset(self, query: str) -> dict[str, Any] | None:
        try:
            candidate = self._llm_candidate(query, {"symbol": query, "name": query, "asset_type": "stock"})
        except Exception:
            return None
        if not candidate:
            return None
        symbol = candidate["yahoo_symbol"]
        return {
            "input_name": query,
            "resolved_name": symbol,
            "name": symbol,
            "symbol": symbol,
            "isin": query.upper() if self._looks_like_isin(query) else "",
            "wkn": query.upper() if self._looks_like_wkn(query) else "",
            "asset_type": self._infer_asset_type(query, symbol),
            "exchange": "",
            "currency": "USD",
        }

    def _asset_type_from_quote_type(self, quote_type: str, symbol: str) -> str:
        if quote_type in {"equity"}:
            return "stock"
        if quote_type == "etf":
            return "etf"
        if quote_type in {"mutualfund", "fund"}:
            return "fund"
        if quote_type == "etc":
            return "etc"
        if quote_type in {"index"} or symbol.startswith("^"):
            return "index"
        if quote_type in {"cryptocurrency"} or "-USD" in symbol:
            return "crypto"
        return "stock"

    def _infer_asset_type(self, query: str, symbol: str) -> str:
        lower = query.lower()
        if "etf" in lower:
            return "etf"
        if "fonds" in lower or "fund" in lower:
            return "fund"
        if "etc" in lower:
            return "etc"
        if symbol.startswith("^"):
            return "index"
        if "-USD" in symbol:
            return "crypto"
        return "stock"

    def _looks_like_isin(self, value: str) -> bool:
        return bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value.strip().upper()))

    def _looks_like_wkn(self, value: str) -> bool:
        return bool(re.fullmatch(r"[A-Z0-9]{6}", value.strip().upper()))

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
