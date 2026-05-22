import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BASE_DIR.parent
DB_PATH = PROJECT_DIR / "ai-agent" / "data" / "market" / "market.db"

REPORT_EXTRA_COLUMNS: dict[str, str] = {
    "quote_provider": "text not null default ''",
    "news_provider": "text not null default ''",
    "analysis_source": "text not null default ''",
    "data_quality": "text not null default 'unknown'",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MarketReportService:
    def __init__(self, database_path: Path = DB_PATH):
        self.database_path = database_path
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                create table if not exists market_watchlist (
                    id integer primary key autoincrement,
                    symbol text not null unique,
                    name text not null default '',
                    asset_type text not null default 'stock',
                    exchange text not null default '',
                    currency text not null default 'USD',
                    notes text not null default '',
                    enabled integer not null default 1,
                    created_at text not null,
                    updated_at text not null
                )
                """
            )
            connection.execute(
                """
                create table if not exists market_reports (
                    id integer primary key autoincrement,
                    symbol text not null,
                    report_date text not null,
                    signal text not null,
                    confidence real not null default 0,
                    price real,
                    change_percent real,
                    volume real,
                    summary text not null default '',
                    positive_factors text not null default '[]',
                    negative_factors text not null default '[]',
                    risk_factors text not null default '[]',
                    news_summary text not null default '',
                    ai_raw_json text not null default '{}',
                    status text not null default 'ok',
                    error text not null default '',
                    created_at text not null
                )
                """
            )
            existing_report_columns = {row["name"] for row in connection.execute("pragma table_info(market_reports)").fetchall()}
            for column, definition in REPORT_EXTRA_COLUMNS.items():
                if column not in existing_report_columns:
                    connection.execute(f"alter table market_reports add column {column} {definition}")
            connection.execute(
                """
                create table if not exists market_news (
                    id integer primary key autoincrement,
                    symbol text not null,
                    title text not null,
                    source text not null default '',
                    url text not null default '',
                    published_at text,
                    sentiment text not null default 'neutral',
                    summary text not null default '',
                    created_at text not null
                )
                """
            )
            connection.commit()

    def watchlist(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        query = "select * from market_watchlist"
        params: tuple[Any, ...] = ()
        if enabled_only:
            query += " where enabled = 1"
        query += " order by symbol"
        with self.connect() as connection:
            return [self._watchlist_row(row) for row in connection.execute(query, params).fetchall()]

    def create_watchlist_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        symbol = str(payload.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("Symbol ist erforderlich.")
        existing = self.find_watchlist_item(symbol)
        if existing:
            return self.update_watchlist_item(existing["id"], payload)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                insert into market_watchlist
                (symbol, name, asset_type, exchange, currency, notes, enabled, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    str(payload.get("name") or symbol).strip(),
                    str(payload.get("asset_type") or "stock").strip(),
                    str(payload.get("exchange") or "").strip(),
                    str(payload.get("currency") or "USD").strip().upper(),
                    str(payload.get("notes") or "").strip(),
                    1 if payload.get("enabled", True) else 0,
                    now,
                    now,
                ),
            )
            connection.commit()
            return self.get_watchlist_item(int(cursor.lastrowid))

    def find_watchlist_item(self, symbol: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("select * from market_watchlist where upper(symbol) = ?", (symbol.upper(),)).fetchone()
        return self._watchlist_row(row) if row else None

    def update_watchlist_item(self, item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_watchlist_item(item_id)
        data = {**current, **payload}
        symbol = str(data.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("Symbol ist erforderlich.")
        with self.connect() as connection:
            connection.execute(
                """
                update market_watchlist
                set symbol = ?, name = ?, asset_type = ?, exchange = ?, currency = ?, notes = ?, enabled = ?, updated_at = ?
                where id = ?
                """,
                (
                    symbol,
                    str(data.get("name") or symbol).strip(),
                    str(data.get("asset_type") or "stock").strip(),
                    str(data.get("exchange") or "").strip(),
                    str(data.get("currency") or "USD").strip().upper(),
                    str(data.get("notes") or "").strip(),
                    1 if data.get("enabled", True) else 0,
                    utc_now(),
                    item_id,
                ),
            )
            connection.commit()
        return self.get_watchlist_item(item_id)

    def delete_watchlist_item(self, item_id: int) -> None:
        with self.connect() as connection:
            connection.execute("delete from market_watchlist where id = ?", (item_id,))
            connection.commit()

    def get_watchlist_item(self, item_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("select * from market_watchlist where id = ?", (item_id,)).fetchone()
        if row is None:
            raise KeyError("Watchlist-Eintrag nicht gefunden.")
        return self._watchlist_row(row)

    def save_news(self, symbol: str, news_items: list[dict[str, Any]]) -> None:
        if not news_items:
            return
        now = utc_now()
        with self.connect() as connection:
            connection.executemany(
                """
                insert into market_news (symbol, title, source, url, published_at, sentiment, summary, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        symbol.upper(),
                        item.get("title", ""),
                        item.get("source", ""),
                        item.get("url", ""),
                        item.get("published_at"),
                        item.get("sentiment", "neutral"),
                        item.get("summary", ""),
                        now,
                    )
                    for item in news_items
                ],
            )
            connection.commit()

    def save_report(self, report: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                insert into market_reports
                (symbol, report_date, signal, confidence, price, change_percent, volume, summary,
                 positive_factors, negative_factors, risk_factors, news_summary, ai_raw_json, status, error,
                 quote_provider, news_provider, analysis_source, data_quality, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.get("symbol", "").upper(),
                    report.get("report_date") or now[:10],
                    report.get("signal", "watch"),
                    float(report.get("confidence") or 0),
                    report.get("price"),
                    report.get("change_percent"),
                    report.get("volume"),
                    report.get("summary", ""),
                    json.dumps(report.get("positive_factors", []), ensure_ascii=False),
                    json.dumps(report.get("negative_factors", []), ensure_ascii=False),
                    json.dumps(report.get("risk_factors", []), ensure_ascii=False),
                    report.get("news_summary", ""),
                    json.dumps(report.get("ai_raw_json", report), ensure_ascii=False),
                    report.get("status", "ok"),
                    report.get("error", ""),
                    report.get("quote_provider", ""),
                    report.get("news_provider", ""),
                    report.get("analysis_source", ""),
                    report.get("data_quality", "unknown"),
                    now,
                ),
            )
            connection.commit()
            return self.get_report(int(cursor.lastrowid))

    def reports(self, symbol: str | None = None, signal: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if symbol:
            clauses.append("upper(symbol) = ?")
            params.append(symbol.upper())
        if signal:
            clauses.append("signal = ?")
            params.append(signal)
        query = "select * from market_reports"
        if clauses:
            query += " where " + " and ".join(clauses)
        query += " order by created_at desc limit ?"
        params.append(limit)
        with self.connect() as connection:
            return [self._report_row(row) for row in connection.execute(query, tuple(params)).fetchall()]

    def latest_reports(self, watchlist_only: bool = False, enabled_only: bool = False) -> list[dict[str, Any]]:
        watchlist_join = ""
        watchlist_where = ""
        if watchlist_only or enabled_only:
            watchlist_join = "join market_watchlist w on upper(w.symbol) = upper(r.symbol)"
            if enabled_only:
                watchlist_where = "where w.enabled = 1"
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                select r.*
                from market_reports r
                {watchlist_join}
                join (
                    select symbol, max(created_at) as created_at
                    from market_reports
                    group by symbol
                ) latest on latest.symbol = r.symbol and latest.created_at = r.created_at
                {watchlist_where}
                order by r.symbol
                """
            ).fetchall()
            return [self._report_row(row) for row in rows]

    def latest_for_symbol(self, symbol: str) -> dict[str, Any] | None:
        reports = self.reports(symbol=symbol, limit=1)
        return reports[0] if reports else None

    def get_report(self, report_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("select * from market_reports where id = ?", (report_id,)).fetchone()
        if row is None:
            raise KeyError("Report nicht gefunden.")
        return self._report_row(row)

    def news(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "select * from market_news where upper(symbol) = ? order by coalesce(published_at, created_at) desc limit ?",
                (symbol.upper(), limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        watchlist = self.watchlist()
        latest = self.latest_reports(enabled_only=True)
        counts = {signal: 0 for signal in ("bullish", "neutral", "bearish", "watch")}
        for report in latest:
            counts[report["signal"]] = counts.get(report["signal"], 0) + 1
        sorted_by_change = sorted(latest, key=lambda item: item.get("change_percent") or 0, reverse=True)
        return {
            "watchlist_count": len(watchlist),
            "enabled_count": len([item for item in watchlist if item["enabled"]]),
            "signals": counts,
            "top_gainers": sorted_by_change[:5],
            "top_losers": list(reversed(sorted_by_change[-5:])),
            "latest_reports": latest[:10],
            "disclaimer": "Keine Finanzberatung.",
        }

    def _watchlist_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        return item

    def _report_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for field in ("positive_factors", "negative_factors", "risk_factors"):
            try:
                item[field] = json.loads(item.get(field) or "[]")
            except json.JSONDecodeError:
                item[field] = []
        try:
            item["ai_raw_json"] = json.loads(item.get("ai_raw_json") or "{}")
        except json.JSONDecodeError:
            item["ai_raw_json"] = {"raw": item.get("ai_raw_json")}
        return item
