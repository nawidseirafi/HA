import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from market.analysis import MarketAnalysisService
from market.data import MarketDataService
from market.news import MarketNewsService
from market.report import MarketReportService, utc_now
from market.symbol_resolver import MarketSymbolResolver


class MarketAgent:
    def __init__(self):
        self.store = MarketReportService()
        self.data = MarketDataService()
        self.news = MarketNewsService()
        self.analysis = MarketAnalysisService()
        self.symbol_resolver = MarketSymbolResolver()

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
        yahoo_symbol = symbol
        resolution: dict[str, Any] | None = None
        resolution_candidates: list[dict[str, Any]] = []
        quote_errors: list[str] = []
        try:
            try:
                quote = self.data.quote(yahoo_symbol)
            except Exception as original_quote_error:
                quote_errors.append(f"{yahoo_symbol}: {original_quote_error}")
                resolution_candidates = self.symbol_resolver.resolve_candidates(symbol, item)
                if not resolution_candidates:
                    raise original_quote_error
                last_quote_error = original_quote_error
                for candidate in resolution_candidates:
                    candidate_symbol = candidate["yahoo_symbol"]
                    try:
                        quote = self.data.quote(candidate_symbol)
                        yahoo_symbol = candidate_symbol
                        resolution = candidate
                        break
                    except Exception as candidate_error:
                        last_quote_error = candidate_error
                        quote_errors.append(f"{candidate_symbol}: {candidate_error}")
                if not quote:
                    raise last_quote_error
            quote_provider = quote.get("provider", "none")
            news_items = self.news.news_for_symbol(yahoo_symbol)
            self.store.save_news(symbol, news_items)
            news_provider = next((item.get("provider") for item in news_items if item.get("provider")), "none")
            analysis = self.analysis.analyze(item, quote, news_items)
            analysis_source = analysis.pop("analysis_source", "llm")
            analysis_error = analysis.pop("analysis_error", "")
            data_quality = "real" if quote_provider == "yahoo" and news_provider == "yahoo_rss" and analysis_source == "llm" else "partial"
            report = {
                **analysis,
                "symbol": symbol,
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
                    "symbol_resolution": resolution,
                    "symbol_resolution_candidates": resolution_candidates,
                    "quote_errors": quote_errors,
                    "yahoo_symbol": yahoo_symbol,
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
                "ai_raw_json": {
                    "error": str(exc),
                    "quote": quote,
                    "news": news_items,
                    "symbol_resolution": resolution,
                    "symbol_resolution_candidates": resolution_candidates,
                    "quote_errors": quote_errors,
                    "yahoo_symbol": yahoo_symbol,
                },
                "status": "error",
                "error": str(exc),
            }
        saved = self.store.save_report(report)
        saved["news"] = news_items
        saved["disclaimer"] = "Keine Finanzberatung."
        return saved


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Market Agent CLI")
    parser.add_argument("command", choices=["run", "analyze"], help="run = batch all watchlist symbols; analyze = single symbol")
    parser.add_argument("--symbol", help="symbol for the analyze command")
    args = parser.parse_args()

    agent = MarketAgent()
    if args.command == "run":
        result = agent.run()
    else:
        if not args.symbol:
            parser.error("--symbol is required for analyze")
        result = agent.analyze_symbol(args.symbol)
    print(json.dumps(result, default=str))
