import { useEffect, useState } from 'react';
import type { MarketWatchlistItem, MarketWatchlistPayload } from '@shared/api/client';
import { api } from '@shared/api/client';

const emptyForm: MarketWatchlistPayload = {
  input_name: '',
  symbol: '',
  name: '',
  resolved_name: '',
  isin: '',
  wkn: '',
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
  const [resolveBusy, setResolveBusy] = useState(false);
  const [resolveError, setResolveError] = useState('');

  useEffect(() => {
    setForm(editing ? {
      input_name: editing.input_name || editing.name || editing.symbol,
      symbol: editing.symbol,
      name: editing.name,
      resolved_name: editing.resolved_name || editing.name,
      isin: editing.isin || '',
      wkn: editing.wkn || '',
      asset_type: editing.asset_type,
      exchange: editing.exchange,
      currency: editing.currency,
      notes: editing.notes,
      enabled: editing.enabled,
    } : emptyForm);
  }, [editing]);

  const resolveInput = async () => {
    const query = String(form.input_name || form.symbol || form.name || '').trim();
    if (!query) {
      setResolveError('Bitte Name, Symbol, ISIN oder WKN eingeben.');
      return;
    }
    setResolveBusy(true);
    setResolveError('');
    try {
      const response = await api.resolveMarketWatchlistInput(query);
      setForm((current) => ({
        ...current,
        ...response.asset,
        input_name: query,
        notes: current.notes,
        enabled: current.enabled,
      }));
    } catch (err) {
      setResolveError(err instanceof Error ? err.message : 'Asset konnte nicht aufgeloest werden.');
    } finally {
      setResolveBusy(false);
    }
  };

  return (
    <form className="panel market-form" onSubmit={(event) => { event.preventDefault(); onSubmit(form); }}>
      <div className="section-title">
        <div>
          <span className="eyebrow">Watchlist</span>
          <h2>{editing ? 'Eintrag bearbeiten' : 'Eintrag hinzufügen'}</h2>
        </div>
      </div>
      <div className="form-grid">
        <label className="wide">Asset suchen<input value={form.input_name || ''} onChange={(event) => setForm({ ...form, input_name: event.target.value })} required placeholder="Apple, AAPL, US0378331005, 865985, MSCI World" /></label>
        <label>Symbol<input value={form.symbol} onChange={(event) => setForm({ ...form, symbol: event.target.value.toUpperCase() })} placeholder="AAPL" /></label>
        <label>Name<input value={form.resolved_name || form.name} onChange={(event) => setForm({ ...form, name: event.target.value, resolved_name: event.target.value })} placeholder="Apple Inc." /></label>
        <label>ISIN<input value={form.isin || ''} onChange={(event) => setForm({ ...form, isin: event.target.value.toUpperCase() })} placeholder="US0378331005" /></label>
        <label>WKN<input value={form.wkn || ''} onChange={(event) => setForm({ ...form, wkn: event.target.value.toUpperCase() })} placeholder="865985" /></label>
        <label>Asset Type<input value={form.asset_type} readOnly /></label>
        <label>Exchange<input value={form.exchange} onChange={(event) => setForm({ ...form, exchange: event.target.value })} placeholder="NASDAQ" /></label>
        <label>Currency<input value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value.toUpperCase() })} placeholder="USD" /></label>
        <label className="check"><input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} /> Aktiv</label>
        <label className="wide">Notizen<textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Warum beobachte ich diesen Wert?" /></label>
      </div>
      {resolveError && <p className="form-error">{resolveError}</p>}
      {form.symbol && (
        <div className="market-resolve-preview">
          <strong>{form.resolved_name || form.name || form.symbol}</strong>
          <span>{form.symbol}</span>
          <span>{form.asset_type}</span>
          <span>{form.currency}</span>
        </div>
      )}
      <div className="button-row">
        <button className="button secondary" type="button" onClick={resolveInput} disabled={resolveBusy || busy}>
          {resolveBusy ? 'Löse auf...' : 'Auflösen'}
        </button>
        <button className="button primary" disabled={busy}>{busy ? 'Speichere...' : 'Speichern'}</button>
        {editing && <button className="button ghost" type="button" onClick={onCancel}>Abbrechen</button>}
      </div>
    </form>
  );
}
