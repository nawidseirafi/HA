import { useEffect, useState } from 'react';
import type { MarketReport, MarketSignalHistoryItem } from '../../api/client';
import { api } from '../../api/client';
import { MarketReportCard, formatPercent, formatPrice } from '../../components/market/MarketReportCard';
import { MarketSignalBadge } from '../../components/market/MarketSignalBadge';
import { MarketTrendChart } from '../../components/market/MarketTrendChart';

export function MarketSymbolPage({ symbol }: { symbol: string }) {
  const [reports, setReports] = useState<MarketReport[]>([]);
  const [signalHistory, setSignalHistory] = useState<MarketSignalHistoryItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    try {
      const data = await api.marketSymbolReports(symbol);
      setReports(data.reports);
      setSignalHistory(data.signal_history ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Symbol-Daten konnten nicht geladen werden.');
    }
  };

  useEffect(() => { load(); }, [symbol]);

  const run = async () => {
    setBusy(true);
    setError('');
    try {
      await api.analyzeMarketSymbol(symbol);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analyse fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  };

  const latest = reports[0];

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">MarketAgent</span>
          <h1>{symbol.toUpperCase()}</h1>
          <p className="market-disclaimer">Keine Finanzberatung.</p>
        </div>
        <button className="button primary" onClick={run} disabled={busy}>{busy ? 'Analysiere...' : 'Einzelanalyse starten'}</button>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      {latest && (
        <section className="market-symbol-grid">
          <article className="panel market-symbol-main">
            <div className="section-title">
              <div>
                <span className="eyebrow">Letztes Signal</span>
                <h2>{formatPrice(latest.price)} · <span className={(latest.change_percent ?? 0) >= 0 ? 'market-positive' : 'market-negative'}>{formatPercent(latest.change_percent)}</span></h2>
              </div>
              <MarketSignalBadge signal={latest.signal} />
            </div>
            <p>{latest.summary || latest.error || 'Keine echten KI-/Marktdaten gefunden.'}</p>
            <div className="market-source-line">
              <span>Analyse: {latest.analysis_source === 'llm' ? 'KI' : latest.analysis_source === 'heuristic' ? 'Heuristik' : latest.analysis_source || 'unbekannt'}</span>
              <span>Kurse: {latest.quote_provider || 'unbekannt'}</span>
              <span>News: {latest.news_provider || 'unbekannt'}</span>
              <span>Status: {latest.data_quality || latest.status}</span>
            </div>
            {latest.error && <p className="error-panel">{latest.error}</p>}
            <div className="market-factor-grid">
              <FactorList title="Positive Faktoren" items={latest.positive_factors} />
              <FactorList title="Negative Faktoren" items={latest.negative_factors} />
              <FactorList title="Risiken" items={latest.risk_factors} />
            </div>
          </article>
          <article className="panel">
            <div className="section-title"><div><span className="eyebrow">Historie</span><h2>Trend</h2></div></div>
            <MarketTrendChart reports={reports} />
          </article>
        </section>
      )}
      {!latest && <section className="panel">Noch kein Report für {symbol.toUpperCase()} vorhanden.</section>}

      <section className="market-dashboard-grid">
        <div className="panel">
          <div className="section-title"><div><span className="eyebrow">Signal-Historie</span><h2>Verlauf</h2></div></div>
          <div className="market-mini-list">
            {signalHistory.map((item) => (
              <div key={item.id} className="market-history-row">
                <strong>{new Date(item.created_at).toLocaleDateString('de-DE')}</strong>
                <MarketSignalBadge signal={item.signal} />
                <span>{Math.round(item.confidence || 0)}%</span>
              </div>
            ))}
            {signalHistory.length === 0 && <p className="muted">Noch keine Signal-Historie vorhanden.</p>}
          </div>
        </div>
        <div className="panel">
          <div className="section-title"><div><span className="eyebrow">Reports</span><h2>Historische Reports</h2></div></div>
          <div className="market-card-list">{reports.map((report) => <MarketReportCard key={report.id} report={report} />)}</div>
        </div>
      </section>
    </div>
  );
}

function FactorList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <strong>{title}</strong>
      <ul>
        {items.map((item) => <li key={item}>{item}</li>)}
        {items.length === 0 && <li>-</li>}
      </ul>
    </div>
  );
}
