import { useEffect, useMemo, useState } from 'react';
import type { MarketReport, MarketSignal } from '../../api/client';
import { api } from '../../api/client';
import type { Route } from '../../App';
import { MarketReportCard } from '../../components/market/MarketReportCard';

export function MarketReportsPage({ navigate }: { navigate: (route: Route) => void }) {
  const [reports, setReports] = useState<MarketReport[]>([]);
  const [symbol, setSymbol] = useState('');
  const [signal, setSignal] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    const params = new URLSearchParams();
    if (symbol.trim()) params.set('symbol', symbol.trim().toUpperCase());
    if (signal) params.set('signal', signal);
    try {
      const data = await api.marketReports(params);
      setReports(data.reports);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reports konnten nicht geladen werden.');
    }
  };

  useEffect(() => { load(); }, []);

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(reports, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'market-reports.json';
    link.click();
    URL.revokeObjectURL(url);
  };

  const uniqueSymbols = useMemo(() => [...new Set(reports.map((report) => report.symbol))], [reports]);

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">MarketAgent</span>
          <h1>Marktberichte</h1>
          <p className="market-disclaimer">Keine Finanzberatung.</p>
        </div>
        <button className="button secondary" onClick={exportJson}>JSON Export</button>
      </header>
      <section className="panel market-filter-bar">
        <label>Symbol<input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} list="market-symbols" placeholder="AAPL" /></label>
        <datalist id="market-symbols">{uniqueSymbols.map((value) => <option value={value} key={value} />)}</datalist>
        <label>Signal<select value={signal} onChange={(event) => setSignal(event.target.value as MarketSignal | '')}>
          <option value="">Alle</option>
          <option value="buy">Buy</option>
          <option value="hold">Hold</option>
          <option value="sell">Sell</option>
          <option value="watch">Watch</option>
        </select></label>
        <button className="button primary" onClick={load}>Filtern</button>
      </section>
      {error && <section className="panel error-panel">{error}</section>}
      <section className="market-card-grid">
        {reports.map((report) => (
          <MarketReportCard key={report.id} report={report} onOpen={(nextSymbol) => navigate({ name: 'marketSymbol', symbol: nextSymbol })} />
        ))}
        {reports.length === 0 && <section className="panel">Keine Reports gefunden.</section>}
      </section>
    </div>
  );
}
