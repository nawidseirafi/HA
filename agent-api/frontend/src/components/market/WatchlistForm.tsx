import { useEffect, useState } from 'react';
import type { MarketWatchlistItem, MarketWatchlistPayload } from '../../api/client';

const emptyForm: MarketWatchlistPayload = {
  symbol: '',
  name: '',
  asset_type: 'stock',
  exchange: '',
  currency: 'USD',
  notes: '',
  enabled: true,
};

export function WatchlistForm({
  editing,
  busy,
  onSubmit,
  onCancel,
}: {
  editing: MarketWatchlistItem | null;
  busy: boolean;
  onSubmit: (payload: MarketWatchlistPayload) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<MarketWatchlistPayload>(emptyForm);

  useEffect(() => {
    setForm(editing ? {
      symbol: editing.symbol,
      name: editing.name,
      asset_type: editing.asset_type,
      exchange: editing.exchange,
      currency: editing.currency,
      notes: editing.notes,
      enabled: editing.enabled,
    } : emptyForm);
  }, [editing]);

  return (
    <form className="panel market-form" onSubmit={(event) => { event.preventDefault(); onSubmit(form); }}>
      <div className="section-title">
        <div>
          <span className="eyebrow">Watchlist</span>
          <h2>{editing ? 'Eintrag bearbeiten' : 'Eintrag hinzufügen'}</h2>
        </div>
      </div>
      <div className="form-grid">
        <label>Symbol<input value={form.symbol} onChange={(event) => setForm({ ...form, symbol: event.target.value.toUpperCase() })} required placeholder="AAPL" /></label>
        <label>Name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Apple Inc." /></label>
        <label>Asset Type<select value={form.asset_type} onChange={(event) => setForm({ ...form, asset_type: event.target.value as MarketWatchlistPayload['asset_type'] })}>
          <option value="stock">Stock</option>
          <option value="etf">ETF</option>
          <option value="crypto">Crypto</option>
          <option value="index">Index</option>
        </select></label>
        <label>Exchange<input value={form.exchange} onChange={(event) => setForm({ ...form, exchange: event.target.value })} placeholder="NASDAQ" /></label>
        <label>Currency<input value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value.toUpperCase() })} placeholder="USD" /></label>
        <label className="check"><input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} /> Aktiv</label>
        <label className="wide">Notizen<textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Warum beobachte ich diesen Wert?" /></label>
      </div>
      <div className="button-row">
        <button className="button primary" disabled={busy}>{busy ? 'Speichere...' : 'Speichern'}</button>
        {editing && <button className="button ghost" type="button" onClick={onCancel}>Abbrechen</button>}
      </div>
    </form>
  );
}
