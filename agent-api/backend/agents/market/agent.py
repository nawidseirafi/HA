import threading
from datetime import datetime
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
        self._running = False
        self._last_error: str | None = None
        self._last_run: str | None = None
        self.scheduler_stop = threading.Event()
        self.scheduler_thread: threading.Thread | None = None
        self._last_scheduled_run: str | None = None
        self.discovery_universe = [
            "Microsoft",
            "Apple",
            "MSCI World",
            "Nvidia",
            "S&P 500 ETF",
        ]

    def config(self) -> dict[str, Any]:
        config = load_agent_section("market")
        return {
            "enabled": self._bool_config(config.get("enabled", True)),
            "database_path": config.get("database_path", "data/market/market.db"),
            "log_path": config.get("log_path", "logs/market.log"),
            "price_provider": config.get("price_provider", "yahoo"),
            "news_provider": config.get("news_provider", "fallback"),
            "schedule": self._schedule_times(config.get("schedule")),
        }

    def status(self) -> dict[str, Any]:
        config = self.config()
        if self._last_error:
            current_status = "error"
        elif not config["enabled"]:
            current_status = "disabled"
        elif self._running:
            current_status = "running"
        else:
            current_status = "active"
        return {
            "enabled": config["enabled"],
            "is_running": self._running,
            "current_status": current_status,
            "status": current_status,
            "last_error": self._last_error,
            "last_successful_run": self._last_run,
            "scheduler_running": bool(self.scheduler_thread and self.scheduler_thread.is_alive()),
            "last_scheduled_run": self._last_scheduled_run,
            "settings": config,
        }

    def start_scheduler(self) -> dict[str, Any]:
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return self.status()
        self.scheduler_stop.clear()
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        return self.status()

    def stop_scheduler(self) -> dict[str, Any]:
        self.scheduler_stop.set()
        return self.status()

    def _scheduler_loop(self) -> None:
        last_run: set[str] = set()
        while not self.scheduler_stop.is_set():
            now = datetime.now().astimezone()
            today = now.date().isoformat()
            if len(last_run) > 20:
                last_run = {item for item in last_run if item.startswith(today)}
            if self.config()["enabled"]:
                for schedule_time in self.config()["schedule"]:
                    run_key = f"{today}:{schedule_time}"
                    if run_key in last_run:
                        continue
                    if self._time_due(now, schedule_time):
                        last_run.add(run_key)
                        self._last_scheduled_run = utc_now()
                        threading.Thread(target=self.run, daemon=True).start()
            self.scheduler_stop.wait(30)

    def enable(self) -> dict[str, Any]:
        self._write_config(enabled=True)
        self._last_error = None
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
        if "schedule" in payload and isinstance(payload["schedule"], list):
            updates["schedule"] = self._schedule_times(payload["schedule"])
        if updates:
            self._write_config(**updates)
        return self.status()

    def run(self) -> dict[str, Any]:
        if not self.config()["enabled"]:
            return {"status": "disabled", "current_status": "disabled", "reports": [], "disclaimer": "Keine Finanzberatung."}
        if self._running:
            return {"status": "running", "current_status": "running", "reports": [], "disclaimer": "Keine Finanzberatung."}
        self._running = True
        self._last_error = None
        try:
            entries = self.store.watchlist(enabled_only=True)
            reports = [self.analyze_symbol(entry["symbol"], report_type="watchlist") for entry in entries]
            discovery_reports = self.update_discovery()
            self._last_run = utc_now()
            return {
                "status": "active",
                "current_status": "active",
                "run_status": "completed",
                "reports": reports,
                "discovery_reports": discovery_reports,
                "disclaimer": "Keine Finanzberatung.",
            }
        except Exception as exc:
            self._last_error = str(exc)
            return {
                "status": "error",
                "current_status": "error",
                "message": str(exc),
                "reports": [],
                "disclaimer": "Keine Finanzberatung.",
            }
        finally:
            self._running = False

    def resolve_asset(self, raw_input: str) -> dict[str, Any]:
        return self.symbol_resolver.resolve_asset(raw_input)

    def create_watchlist_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_input = str(payload.get("input_name") or payload.get("symbol") or payload.get("name") or "").strip()
        resolved = self.resolve_asset(raw_input)
        merged = {
            **payload,
            **resolved,
            "notes": payload.get("notes", ""),
            "enabled": payload.get("enabled", True),
        }
        return self.store.create_watchlist_item(merged)

    def update_watchlist_item(self, item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        raw_input = str(payload.get("input_name") or payload.get("symbol") or payload.get("name") or "").strip()
        if raw_input:
            resolved = self.resolve_asset(raw_input)
            payload = {**payload, **resolved}
        return self.store.update_watchlist_item(item_id, payload)

    def update_discovery(self) -> list[dict[str, Any]]:
        reports: list[dict[str, Any]] = []
        watchlist_symbols = {item["symbol"].upper() for item in self.store.watchlist()}
        for raw in self.discovery_universe:
            try:
                asset = self.resolve_asset(raw)
                if asset["symbol"].upper() in watchlist_symbols:
                    continue
                reports.append(self._analyze_asset(asset, report_type="discovery"))
            except Exception:
                continue
        return reports[:5]

    def analyze_symbol(self, symbol: str, report_type: str = "watchlist") -> dict[str, Any]:
        symbol = symbol.strip().upper()
        entries = [item for item in self.store.watchlist() if item["symbol"].upper() == symbol]
        item = entries[0] if entries else {
            "symbol": symbol,
            "name": symbol,
            "resolved_name": symbol,
            "asset_type": "stock",
            "exchange": "",
            "currency": "USD",
            "notes": "",
            "enabled": True,
        }
        return self._analyze_asset(item, report_type=report_type)

    def _analyze_asset(self, item: dict[str, Any], report_type: str = "watchlist") -> dict[str, Any]:
        symbol = str(item.get("symbol") or "").strip().upper()
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
                "asset_type": self._safe_asset_type(item.get("asset_type"), symbol),
                "report_date": utc_now()[:10],
                "price": quote.get("price"),
                "change_percent": quote.get("change_percent"),
                "volume": quote.get("volume"),
                "performance": quote.get("performance") or {},
                "technical": quote.get("technical") or {},
                "quote_provider": quote_provider,
                "news_provider": news_provider,
                "analysis_source": analysis_source,
                "data_quality": data_quality,
                "report_type": report_type,
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
                "asset_type": self._safe_asset_type(item.get("asset_type"), symbol),
                "report_date": utc_now()[:10],
                "signal": "watch",
                "recommendation": "watch",
                "confidence": 0,
                "risk_level": "medium",
                "price": quote.get("price") if quote else None,
                "change_percent": quote.get("change_percent") if quote else None,
                "volume": quote.get("volume") if quote else None,
                "quote_provider": quote_provider,
                "news_provider": news_provider,
                "analysis_source": "error",
                "data_quality": "error",
                "summary": "",
                "reasoning": "",
                "positive_factors": [],
                "negative_factors": [],
                "risk_factors": [],
                "news_summary": "",
                "time_horizon": "medium",
                "report_type": report_type,
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
        previous_report = self.store.latest_for_symbol(symbol)
        saved = self.store.save_report(report)
        saved["news"] = news_items
        saved["disclaimer"] = "Keine Finanzberatung."
        self._create_market_message(saved, previous_report)
        return saved

    def _create_market_message(self, report: dict[str, Any], previous_report: dict[str, Any] | None = None) -> None:
        recommendation = str(report.get("recommendation") or report.get("signal") or "watch")
        confidence = float(report.get("confidence") or 0)
        previous = str((previous_report or {}).get("recommendation") or (previous_report or {}).get("signal") or "")
        relevant_transition = (previous, recommendation) in {
            ("hold", "buy"),
            ("buy", "sell"),
            ("watch", "buy"),
            ("sell", "buy"),
        }
        if not relevant_transition:
            return
        title = "Market Signalwechsel"
        severity = "warning" if recommendation == "sell" else "info"
        message = self._market_message_text(report, recommendation, confidence, previous)
        try:
            MessagingService().create_message(
                source="market",
                category="market",
                severity=severity,
                title=title,
                message=message,
                payload={"symbol": report.get("symbol"), "report_id": report.get("id"), "previous": previous, "recommendation": recommendation},
            )
        except Exception:
            pass

    def _market_message_text(self, report: dict[str, Any], recommendation: str, confidence: float, previous: str = "") -> str:
        name = report.get("resolved_name") or report.get("symbol")
        summary = str(report.get("summary") or "").strip()
        risk = str(report.get("risk_level") or "medium").capitalize()
        if previous:
            return f"{name} wechselte von {previous.upper()} zu {recommendation.upper()}. Confidence {confidence:.0f} %. {summary} Risiko {risk}.".strip()
        return f"{name} zeigt ein {recommendation.upper()} Signal. Confidence {confidence:.0f} %. {summary} Risiko {risk}.".strip()

    def _infer_asset_type(self, symbol: str) -> str:
        if symbol.startswith("^"):
            return "index"
        if "-USD" in symbol:
            return "crypto"
        return "stock"

    def _safe_asset_type(self, value: Any, symbol: str) -> str:
        text = str(value or "").strip().lower()
        if text in {"stock", "etf", "fund", "etc", "crypto", "index"}:
            return text
        return self._infer_asset_type(symbol)

    def _schedule_times(self, value: Any) -> list[str]:
        raw = value if isinstance(value, list) else ["06:00", "12:00", "18:00"]
        normalized: list[str] = []
        for item in raw:
            text = str(item).strip()
            if not text:
                continue
            parts = text.split(":")
            try:
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            except (ValueError, IndexError):
                continue
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                normalized.append(f"{hour:02d}:{minute:02d}")
        return normalized or ["06:00", "12:00", "18:00"]

    def _time_due(self, now: datetime, schedule_time: str) -> bool:
        hour, minute = [int(part) for part in schedule_time.split(":", 1)]
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return 0 <= (now - scheduled).total_seconds() < 60

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

    def _bool_config(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return True
        return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}
