import json
import math
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
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=1y&interval=1d"
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
        performance = self._performance(closes)
        technical = self._technical(closes)
        return {
            "symbol": symbol,
            "price": round(price, 4),
            "change_percent": round(change_percent, 2),
            "volume": volume,
            "currency": meta.get("currency", "USD"),
            "exchange": meta.get("exchangeName") or meta.get("fullExchangeName") or "",
            "name": meta.get("longName") or meta.get("shortName") or symbol,
            "performance": performance,
            "technical": technical,
            "provider": "yahoo",
            "is_fallback": False,
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def _performance(self, closes: list[float]) -> dict[str, float | None]:
        return {
            "1d": self._change(closes, 1),
            "7d": self._change(closes, 7),
            "30d": self._change(closes, 30),
            "6m": self._change(closes, 126),
            "1y": self._change(closes, 252),
        }

    def _technical(self, closes: list[float]) -> dict[str, Any]:
        returns = []
        for index in range(1, len(closes)):
            previous = closes[index - 1]
            if previous:
                returns.append((closes[index] - previous) / previous)
        recent = closes[-30:] if len(closes) >= 30 else closes
        trend = "stable"
        if len(recent) >= 2:
            change = self._change(recent, len(recent) - 1) or 0
            if change > 5:
                trend = "up"
            elif change < -5:
                trend = "down"
        volatility = None
        if returns:
            mean = sum(returns) / len(returns)
            variance = sum((value - mean) ** 2 for value in returns) / len(returns)
            volatility = round(math.sqrt(variance) * math.sqrt(252) * 100, 2)
        return {
            "trend": trend,
            "volatility": volatility,
            "sma_30": round(sum(recent) / len(recent), 4) if recent else None,
        }

    def _change(self, values: list[float], lookback: int) -> float | None:
        if len(values) <= lookback:
            return None
        start = float(values[-lookback - 1])
        end = float(values[-1])
        if not start:
            return None
        return round((end - start) / start * 100, 2)
