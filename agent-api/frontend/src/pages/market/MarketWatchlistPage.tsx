import { useEffect, useState } from 'react';
import type { MarketWatchlistItem, MarketWatchlistPayload } from '../../api/client';
import { api } from '../../api/client';
import type { Route } from '../../App';
import { WatchlistForm } from '../../components/market/WatchlistForm';
import { WatchlistTable } from '../../components/market/WatchlistTable';

export function MarketWatchlistPage({ navigate }: { navigate: (route: Route) => void }) {
  const [items, setItems] = useState<MarketWatchlistItem[]>([]);
  const [editing, setEditing] = useState<MarketWatchlistItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    try {
      const watchlist = await api.marketWatchlist();
      setItems(watchlist);
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
          onEdit={setEditing}
          onDelete={remove}
          onOpen={(symbol) => navigate({ name: 'marketSymbol', symbol })}
        />
        <WatchlistForm editing={editing} busy={busy} onSubmit={save} onCancel={() => setEditing(null)} />
      </section>
    </div>
  );
}
