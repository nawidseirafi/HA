import { useEffect, useState } from 'react';
import type { MarketReport, MarketSummary } from '../../api/client';
import { api } from '../../api/client';
import type { Route } from '../../App';
import { formatPercent, formatPrice, sourceLabel } from '../../components/market/MarketReportCard';
import { MarketRunButton } from '../../components/market/MarketRunButton';
import { MarketPerformanceChart, MarketSentimentDonut, MiniSparkline, type MarketRange } from '../../components/market/MarketCharts';
import { MarketSignalBadge } from '../../components/market/MarketSignalBadge';

export function MarketDashboardPage({ navigate }: { navigate: (route: Route) => void }) {
  const [summary, setSummary] = useState<MarketSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [range, setRange] = useState<MarketRange>('30D');

  const load = async () => {
    setError('');
    try {
      setSummary(await api.marketSummary());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Marktdaten konnten nicht geladen werden.');
    }
  };

  useEffect(() => { load(); }, []);

  const run = async () => {
    setBusy(true);
    setError('');
    try {
      await api.runMarketAgent();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Marktanalyse fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">MarketAgent</span>
          <h1>Marktanalyse</h1>
          <p className="market-disclaimer">Keine Finanzberatung.</p>
        </div>
        <div className="button-row">
          <button className="button secondary" onClick={() => navigate({ name: 'marketWatchlist' })}>Watchlist</button>
          <MarketRunButton busy={busy} onRun={run} />
        </div>
      </header>

      {error && <section className="panel error-panel">{error}</section>}
      <MarketTickerStrip reports={summary?.latest_reports ?? []} onOpen={(symbol) => navigate({ name: 'marketSymbol', symbol })} />

      <section className="market-dashboard-grid">
        <div className="market-primary-stack">
          <MarketPerformanceChart reports={summary?.latest_reports ?? []} range={range} onRangeChange={setRange} />
          <MarketIntelTable
            reports={summary?.latest_reports ?? []}
            onOpen={(symbol) => navigate({ name: 'marketSymbol', symbol })}
            onReports={() => navigate({ name: 'marketReports' })}
          />
        </div>

        <aside className="quick-stack market-side-stack">
          <MarketSentimentDonut summary={summary} />
          <MarketMovePanel title="Stärkste Gewinner" reports={summary?.top_gainers ?? []} onOpen={(symbol) => navigate({ name: 'marketSymbol', symbol })} />
          <MarketMovePanel title="Stärkste Verlierer" reports={summary?.top_losers ?? []} onOpen={(symbol) => navigate({ name: 'marketSymbol', symbol })} />
          <MarketNewsFlow reports={summary?.latest_reports ?? []} />
        </aside>
      </section>
    </div>
  );
}

function MarketTickerStrip({ reports, onOpen }: { reports: MarketReport[]; onOpen: (symbol: string) => void }) {
  return (
    <section className="market-ticker-strip">
      {reports.map((report) => (
        <button key={report.id} onClick={() => onOpen(report.symbol)}>
          <strong>{report.symbol}</strong>
          <span>{formatPrice(report.price)}</span>
          <b className={(report.change_percent ?? 0) >= 0 ? 'market-positive' : 'market-negative'}>{formatPercent(report.change_percent)}</b>
          <em className={`market-quality ${report.data_quality ?? 'unknown'}`}>{qualityLabel(report)}</em>
          <MiniSparkline symbol={report.symbol} changePercent={report.change_percent} />
        </button>
      ))}
      {reports.length === 0 && <div className="market-empty-ticker">Keine Live-Daten. Watchlist anlegen und Marktanalyse starten.</div>}
    </section>
  );
}

function MarketIntelTable({ reports, onOpen, onReports }: { reports: MarketReport[]; onOpen: (symbol: string) => void; onReports: () => void }) {
  return (
    <section className="panel market-intel-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Intelligence Feed</span>
          <h2>Watchlist Dynamik</h2>
        </div>
        <button className="button ghost" onClick={onReports}>Alle Berichte</button>
      </div>
      <div className="market-intel-table">
        <div className="market-intel-head">
          <span>Symbol</span>
          <span>Signal</span>
          <span>Preis</span>
          <span>Move</span>
          <span>Confidence</span>
          <span>Daten</span>
        </div>
        {reports.map((report) => (
          <button className="market-intel-row" key={report.id} onClick={() => onOpen(report.symbol)}>
            <strong>{report.symbol}</strong>
            <MarketSignalBadge signal={report.signal} />
            <span>{formatPrice(report.price)}</span>
            <b className={(report.change_percent ?? 0) >= 0 ? 'market-positive' : 'market-negative'}>{formatPercent(report.change_percent)}</b>
            <span>{Math.round((report.confidence || 0) * 100)}%</span>
            <small>{report.status === 'error' ? 'Keine echten Daten' : `${sourceLabel(report.analysis_source)} · ${report.quote_provider || '?'} · ${report.news_provider || '?'}`}</small>
          </button>
        ))}
        {reports.length === 0 && <p className="muted">Noch keine Reports vorhanden.</p>}
      </div>
    </section>
  );
}

function qualityLabel(report: MarketReport) {
  if (report.data_quality === 'real') return 'LIVE + KI';
  if (report.analysis_source === 'llm') return 'KI';
  if (report.data_quality === 'error') return 'ERROR';
  return 'TEILDATEN';
}

function MarketNewsFlow({ reports }: { reports: MarketReport[] }) {
  const news = reports
    .filter((report) => report.news_summary || report.summary)
    .slice(0, 6)
    .map((report) => ({
      symbol: report.symbol,
      text: report.news_summary || report.summary,
      signal: report.signal,
      time: report.created_at,
    }));
  return (
    <section className="panel market-news-flow">
      <div className="section-title">
        <div>
          <span className="eyebrow">Newsflow</span>
          <h2>Marktlage</h2>
        </div>
      </div>
      <div className="market-flow-list">
        {news.map((item) => (
          <article key={`${item.symbol}-${item.time}`}>
            <div>
              <strong>{item.symbol}</strong>
              <MarketSignalBadge signal={item.signal} />
            </div>
            <p>{item.text}</p>
            <small>{new Date(item.time).toLocaleString('de-DE')}</small>
          </article>
        ))}
        {news.length === 0 && <p className="muted">Noch kein Newsflow vorhanden.</p>}
      </div>
    </section>
  );
}

function MarketMovePanel({ title, reports, onOpen }: { title: string; reports: MarketSummary['latest_reports']; onOpen: (symbol: string) => void }) {
  return (
    <div className="panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Momentum</span>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="market-mini-list">
        {reports.map((report) => (
          <button key={report.id} onClick={() => onOpen(report.symbol)}>
            <strong>{report.symbol}</strong>
            <span className={(report.change_percent ?? 0) >= 0 ? 'market-positive' : 'market-negative'}>
              {(report.change_percent ?? 0).toFixed(2)}%
            </span>
          </button>
        ))}
        {reports.length === 0 && <p className="muted">Noch keine Daten.</p>}
      </div>
    </div>
  );
}
