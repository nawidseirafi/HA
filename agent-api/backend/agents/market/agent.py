from typing import Any

import yaml

from backend.config import load_agent_section
from backend.paths import AGENTS_DIR
from backend.services.messaging import MessagingService

from .analysis_service import MarketAnalysisService
from .data_service import MarketDataService
from .news_service import MarketNewsService
from .report_service import MarketReportService, utc_now
from .symbol_resolver import MarketSymbolResolver


class MarketAgent:
    def __init__(self):
        self.store = MarketReportService()
        self.data = MarketDataService()
        self.news = MarketNewsService()
        self.analysis = MarketAnalysisService()
        self.symbol_resolver = MarketSymbolResolver()

    def config(self) -> dict[str, Any]:
        config = load_agent_section("market")
        return {
            "enabled": bool(config.get("enabled", True)),
            "database_path": config.get("database_path", "data/market/market.db"),
            "log_path": config.get("log_path", "logs/market.log"),
            "price_provider": config.get("price_provider", "yahoo"),
            "news_provider": config.get("news_provider", "fallback"),
        }

    def status(self) -> dict[str, Any]:
        config = self.config()
        return {
            "enabled": config["enabled"],
            "current_status": "active" if config["enabled"] else "disabled",
            "status": "active" if config["enabled"] else "disabled",
            "last_error": None,
            "settings": config,
        }

    def enable(self) -> dict[str, Any]:
        self._write_config(enabled=True)
        return self.status()

    def disable(self) -> dict[str, Any]:
        self._write_config(enabled=False)
        return self.status()

    def toggle(self) -> dict[str, Any]:
        return self.disable() if self.config()["enabled"] else self.enable()

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if "enabled" in payload:
            updates["enabled"] = bool(payload["enabled"])
        if updates:
            self._write_config(**updates)
        return self.status()

    def run(self) -> dict[str, Any]:
        if not self.config()["enabled"]:
            return {"status": "disabled", "reports": [], "disclaimer": "Keine Finanzberatung."}
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
        self._create_market_message(saved)
        return saved

    def _create_market_message(self, report: dict[str, Any]) -> None:
        signal = str(report.get("signal") or "watch")
        if signal not in {"bullish", "bearish"}:
            return
        title = "Kaufchance erkannt" if signal == "bullish" else "Starke Marktbewegung"
        severity = "info" if signal == "bullish" else "warning"
        try:
            MessagingService().create_message(
                source="market",
                category="market",
                severity=severity,
                title=title,
                message=f"{report.get('symbol')} wurde mit Signal {signal} bewertet.",
                payload={"symbol": report.get("symbol"), "report_id": report.get("id"), "signal": signal},
            )
        except Exception:
            pass

    def _write_config(self, **updates: Any) -> None:
        path = AGENTS_DIR / "market" / "config.yaml"
        data: dict[str, Any] = {}
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
                data = loaded if isinstance(loaded, dict) else {}
        section = data.get("market")
        if not isinstance(section, dict):
            section = {}
        section.update(updates)
        data["market"] = section
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)
