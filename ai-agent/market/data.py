import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


class MarketDataService:
    def quote(self, symbol: str) -> dict[str, Any]:
        symbol = symbol.strip().upper()
        return self._yahoo_quote(symbol)

    def _yahoo_quote(self, symbol: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(symbol)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=5d&interval=1d"
        request = urllib.request.Request(url, headers={"User-Agent": "RoboterSteve/1.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        closes = [value for value in result["indicators"]["quote"][0].get("close", []) if value is not None]
        price = float(meta.get("regularMarketPrice") or closes[-1])
        previous = float(meta.get("previousClose") or (closes[-2] if len(closes) > 1 else price))
        change_percent = ((price - previous) / previous * 100) if previous else 0
        volume_values = result["indicators"]["quote"][0].get("volume", []) or []
        volume = next((value for value in reversed(volume_values) if value is not None), None)
        return {
            "symbol": symbol,
            "price": round(price, 4),
            "change_percent": round(change_percent, 2),
            "volume": volume,
            "currency": meta.get("currency", "USD"),
            "provider": "yahoo",
            "is_fallback": False,
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
