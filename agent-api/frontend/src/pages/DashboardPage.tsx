import { useEffect, useRef, useState } from 'react';
import { Play, Upload } from 'lucide-react';
import { api } from '../api/client';
import type { Route } from '../App';
import type { Summary } from '../types/invoice';
import { currency, shortDate } from '../lib/format';

export function DashboardPage({ navigate }: { navigate: (route: Route) => void }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => api.summary().then(setSummary);
  useEffect(() => { load(); }, []);

  const run = async () => {
    setBusy(true);
    await api.runAgent();
    await load();
    setBusy(false);
  };

  const upload = async (file?: File) => {
    if (!file) return;
    setBusy(true);
    await api.upload(file);
    await load();
    setBusy(false);
  };

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Dashboard</span>
          <h1>Rechnungen und Belege</h1>
        </div>
        <div className="button-row">
          <button className="button secondary" onClick={run} disabled={busy}><Play size={16} /> InvoiceAgent starten</button>
          <button className="button primary" onClick={() => fileRef.current?.click()} disabled={busy}><Upload size={16} /> Beleg hochladen</button>
          <input ref={fileRef} type="file" hidden onChange={(event) => upload(event.target.files?.[0])} />
        </div>
      </header>

      <section className="stats-grid">
        <Metric label="Gesamt" value={summary?.total_invoices ?? 0} />
        <Metric label="Aktueller Monat" value={currency(summary?.current_month_total)} />
        <Metric label="Aktuelles Jahr" value={currency(summary?.current_year_total)} />
        <Metric label="Ungeprüft" value={summary?.needs_review_count ?? 0} tone="warn" />
        <Metric label="KI-Fehler" value={summary?.ai_error_count ?? 0} tone="danger" />
      </section>

      <section className="panel">
        <div className="section-title">
          <h2>Letzte Uploads</h2>
          <button className="button ghost" onClick={() => navigate({ name: 'years' })}>Alle Jahre</button>
        </div>
        <div className="recent-list">
          {(summary?.latest_uploads ?? []).map((invoice) => (
            <button key={invoice.id} onClick={() => navigate({ name: 'invoice', id: invoice.id })}>
              <span>{shortDate(invoice.invoice_date)}</span>
              <strong>{invoice.vendor}</strong>
              <em>{currency(invoice.gross_amount ?? invoice.amount, invoice.currency)}</em>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: 'warn' | 'danger' }) {
  return (
    <div className={`summary-card ${tone ?? ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
