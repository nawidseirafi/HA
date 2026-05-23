import { useEffect, useState } from 'react';
import type { MarketReport, MarketWatchlistItem, MarketWatchlistPayload } from '../../api/client';
import { api } from '../../api/client';
import type { Route } from '../../App';
import { WatchlistForm } from '../../components/market/WatchlistForm';
import { WatchlistTable } from '../../components/market/WatchlistTable';

export function MarketWatchlistPage({ navigate }: { navigate: (route: Route) => void }) {
  const [items, setItems] = useState<MarketWatchlistItem[]>([]);
  const [latestReports, setLatestReports] = useState<MarketReport[]>([]);
  const [editing, setEditing] = useState<MarketWatchlistItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [busySymbol, setBusySymbol] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    try {
      const [watchlist, latest] = await Promise.all([
        api.marketWatchlist(),
        api.marketLatestReports().catch(() => ({ reports: [], disclaimer: 'Keine Finanzberatung.' })),
      ]);
      setItems(watchlist);
      setLatestReports(latest.reports);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Watchlist konnte nicht geladen werden.');
    }
  };

  useEffect(() => { load(); }, []);

  const save = async (payload: MarketWatchlistPayload) => {
    setBusy(true);
    setError('');
    try {
      if (editing) await api.updateMarketWatchlistItem(editing.id, payload);
      else await api.createMarketWatchlistItem(payload);
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Speichern fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (item: MarketWatchlistItem) => {
    if (!confirm(`${item.symbol} aus der Watchlist löschen?`)) return;
    await api.deleteMarketWatchlistItem(item.id);
    await load();
  };

  const analyze = async (item: MarketWatchlistItem) => {
    setBusySymbol(item.symbol);
    setError('');
    try {
      await api.analyzeMarketSymbol(item.symbol);
      navigate({ name: 'marketSymbol', symbol: item.symbol });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analyse fehlgeschlagen.');
    } finally {
      setBusySymbol('');
    }
  };

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">MarketAgent</span>
          <h1>Watchlist</h1>
          <p className="market-disclaimer">Keine Finanzberatung.</p>
        </div>
        <button className="button secondary" onClick={() => navigate({ name: 'marketDashboard' })}>Dashboard</button>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      <section className="market-watchlist-layout">
        <WatchlistTable
          items={items}
          latestReports={latestReports}
          busySymbol={busySymbol}
          onEdit={setEditing}
          onDelete={remove}
          onAnalyze={analyze}
          onOpen={(symbol) => navigate({ name: 'marketSymbol', symbol })}
        />
        <WatchlistForm editing={editing} busy={busy} onSubmit={save} onCancel={() => setEditing(null)} />
      </section>
    </div>
  );
}
