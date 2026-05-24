import html
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


class MarketNewsService:
    def news_for_symbol(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        symbol = symbol.strip().upper()
        try:
            return self._yahoo_rss_news(symbol, limit=limit)
        except Exception:
            return []

    def _yahoo_rss_news(self, symbol: str, limit: int) -> list[dict[str, Any]]:
        encoded = urllib.parse.quote(symbol)
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={encoded}&region=US&lang=en-US"
        request = urllib.request.Request(url, headers={"User-Agent": "RoboterSteve/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read()
        root = ET.fromstring(payload)
        items: list[dict[str, Any]] = []
        for item in root.findall("./channel/item")[:limit]:
            title = self._text(item, "title")
            summary = self._text(item, "description")
            items.append(
                {
                    "symbol": symbol,
                    "title": title,
                    "source": "Yahoo Finance",
                    "url": self._text(item, "link"),
                    "published_at": self._parse_date(self._text(item, "pubDate")),
                    "sentiment": self._basic_sentiment(f"{title} {summary}"),
                    "summary": summary,
                    "provider": "yahoo_rss",
                    "is_fallback": False,
                }
            )
        return items

    def _text(self, item: ET.Element, tag: str) -> str:
        value = item.findtext(tag, default="")
        return html.unescape(value).strip()

    def _parse_date(self, value: str) -> str | None:
        if not value:
            return None
        try:
            return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat(timespec="seconds")
        except Exception:
            return None

    def _basic_sentiment(self, text: str) -> str:
        lower = text.lower()
        positive = ("beats", "growth", "rises", "surges", "upgrade", "profit", "record", "strong")
        negative = ("falls", "drops", "misses", "lawsuit", "weak", "loss", "downgrade", "risk")
        if any(word in lower for word in positive):
            return "bullish"
        if any(word in lower for word in negative):
            return "bearish"
        return "neutral"
