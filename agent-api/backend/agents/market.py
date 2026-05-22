from typing import Any

from backend.services.market_analysis_service import MarketAnalysisService
from backend.services.market_data_service import MarketDataService
from backend.services.market_news_service import MarketNewsService
from backend.services.market_report_service import MarketReportService, utc_now


class MarketAgent:
    def __init__(self):
        self.store = MarketReportService()
        self.data = MarketDataService()
        self.news = MarketNewsService()
        self.analysis = MarketAnalysisService()

    def run(self) -> dict[str, Any]:
        entries = self.store.watchlist(enabled_only=True)
        reports = [self.analyze_symbol(entry["symbol"]) for entry in entries]
        return {"status": "completed", "reports": reports, "disclaimer": "Keine Finanzberatung."}

    def analyze_symbol(self, symbol: str) -> dict[str, Any]:
        symbol = symbol.strip().upper()
        entries = [item for item in self.store.watchlist() if item["symbol"].upper() == symbol]
        item = entries[0] if entries else {
            "symbol": symbol,
            "name": symbol,
            "asset_type": "stock",
            "exchange": "",
            "currency": "USD",
            "notes": "",
            "enabled": True,
        }
        quote: dict[str, Any] = {}
        news_items: list[dict[str, Any]] = []
        quote_provider = "none"
        news_provider = "none"
        try:
            quote = self.data.quote(symbol)
            quote_provider = quote.get("provider", "none")
            news_items = self.news.news_for_symbol(symbol)
            self.store.save_news(symbol, news_items)
            news_provider = next((item.get("provider") for item in news_items if item.get("provider")), "none")
            analysis = self.analysis.analyze(item, quote, news_items)
            analysis_source = analysis.pop("analysis_source", "llm")
            analysis_error = analysis.pop("analysis_error", "")
            data_quality = "real" if quote_provider == "yahoo" and news_provider == "yahoo_rss" and analysis_source == "llm" else "partial"
            report = {
                **analysis,
                "report_date": utc_now()[:10],
                "price": quote.get("price"),
                "change_percent": quote.get("change_percent"),
                "volume": quote.get("volume"),
                "quote_provider": quote_provider,
                "news_provider": news_provider,
                "analysis_source": analysis_source,
                "data_quality": data_quality,
                "ai_raw_json": {
                    "analysis": analysis,
                    "quote": quote,
                    "news": news_items,
                    "analysis_source": analysis_source,
                    "analysis_error": analysis_error,
                },
                "status": "ok" if data_quality == "real" else "degraded",
                "error": analysis_error,
            }
        except Exception as exc:
            report = {
                "symbol": symbol,
                "report_date": utc_now()[:10],
                "signal": "watch",
                "confidence": 0,
                "price": quote.get("price") if quote else None,
                "change_percent": quote.get("change_percent") if quote else None,
                "volume": quote.get("volume") if quote else None,
                "quote_provider": quote_provider,
                "news_provider": news_provider,
                "analysis_source": "error",
                "data_quality": "error",
                "summary": "",
                "positive_factors": [],
                "negative_factors": [],
                "risk_factors": [],
                "news_summary": "",
                "ai_raw_json": {"error": str(exc), "quote": quote, "news": news_items},
                "status": "error",
                "error": str(exc),
            }
        saved = self.store.save_report(report)
        saved["news"] = news_items
        saved["disclaimer"] = "Keine Finanzberatung."
        return saved
