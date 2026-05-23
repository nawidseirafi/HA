import { useEffect, useState } from 'react';
import { BadgeCheck, Save, Wand2 } from 'lucide-react';
import type { Invoice } from '../../types/invoice';

interface Props {
  invoice: Invoice;
  onSave: (payload: Partial<Invoice>) => Promise<void>;
  onReanalyze: () => Promise<void>;
  onMarkReviewed: () => Promise<void>;
}

export function InvoiceDetailPanel({ invoice, onSave, onReanalyze, onMarkReviewed }: Props) {
  const [form, setForm] = useState<Partial<Invoice>>(invoice);
  const [amountInputs, setAmountInputs] = useState({
    net_amount: formatAmountInput(invoice.net_amount),
    gross_amount: formatAmountInput(invoice.gross_amount ?? invoice.amount),
    tax_amount: formatAmountInput(invoice.tax_amount),
  });
  const [showRaw, setShowRaw] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [reviewing, setReviewing] = useState(false);

  useEffect(() => {
    setForm(invoice);
    setAmountInputs({
      net_amount: formatAmountInput(invoice.net_amount),
      gross_amount: formatAmountInput(invoice.gross_amount ?? invoice.amount),
      tax_amount: formatAmountInput(invoice.tax_amount),
    });
  }, [invoice]);

  const update = (key: keyof Invoice, value: string | number | boolean | null) => setForm((current) => ({ ...current, [key]: value }));
  const updateAmount = (key: 'net_amount' | 'gross_amount' | 'tax_amount', value: string) => {
    setAmountInputs((current) => ({ ...current, [key]: value }));
    update(key, parseAmountInput(value));
  };

  const save = async () => {
    setSaving(true);
    try {
      await onSave({
        ...form,
        net_amount: parseAmountInput(amountInputs.net_amount),
        gross_amount: parseAmountInput(amountInputs.gross_amount),
        tax_amount: parseAmountInput(amountInputs.tax_amount),
      });
    } finally {
      setSaving(false);
    }
  };

  const reanalyze = async () => {
    setReanalyzing(true);
    try {
      await onReanalyze();
    } finally {
      setReanalyzing(false);
    }
  };

  const markReviewed = async () => {
    setReviewing(true);
    try {
      await onMarkReviewed();
    } finally {
      setReviewing(false);
    }
  };

  return (
    <section className="detail-panel">
      <div className="panel detail-form-card">
        <div className="section-title">
          <div>
            <span className="eyebrow">Metadaten</span>
            <h2>Beleg bearbeiten</h2>
          </div>
          <span className={`status status-${form.review_status}`}>{statusLabel(form.review_status)}</span>
        </div>
      <div className="form-grid">
        <label>Anbieter<input value={form.vendor ?? ''} onChange={(event) => update('vendor', event.target.value)} /></label>
        <label>Rechnungsdatum<input type="date" value={form.invoice_date ?? ''} onChange={(event) => update('invoice_date', event.target.value)} /></label>
        <label>Rechnungsnummer<input value={form.invoice_number ?? ''} onChange={(event) => update('invoice_number', event.target.value)} /></label>
        <label>Kategorie<input value={form.category ?? ''} onChange={(event) => update('category', event.target.value)} /></label>
        <label>Betrag netto<input inputMode="decimal" value={amountInputs.net_amount} onChange={(event) => updateAmount('net_amount', event.target.value)} /></label>
        <label>MwSt<input inputMode="decimal" value={amountInputs.tax_amount} onChange={(event) => updateAmount('tax_amount', event.target.value)} /></label>
        <label>Betrag brutto<input inputMode="decimal" value={amountInputs.gross_amount} onChange={(event) => updateAmount('gross_amount', event.target.value)} /></label>
        <label>Art<select value={form.transaction_type ?? 'expense'} onChange={(event) => update('transaction_type', event.target.value)}>
          <option value="expense">Ausgabe</option>
          <option value="income">Einnahme</option>
        </select></label>
        <label>Status<select value={form.review_status ?? 'needs_review'} onChange={(event) => update('review_status', event.target.value)}>
          <option value="new">new</option>
          <option value="needs_review">needs_review</option>
          <option value="reviewed">reviewed</option>
          <option value="exported">exported</option>
          <option value="error">error</option>
        </select></label>
        <label>Waehrung<input value={form.currency ?? 'EUR'} onChange={(event) => update('currency', event.target.value)} /></label>
        <label className="check"><input type="checkbox" checked={Boolean(form.is_business)} onChange={(event) => update('is_business', event.target.checked)} /> geschaeftlich</label>
        <label className="check"><input type="checkbox" checked={Boolean(form.is_tax_relevant)} onChange={(event) => update('is_tax_relevant', event.target.checked)} /> steuerrelevant</label>
        <label className="wide">Notizen<textarea value={form.notes ?? ''} onChange={(event) => update('notes', event.target.value)} /></label>
      </div>
      <div className="button-row">
        <button className="button primary" onClick={save} disabled={saving || reanalyzing || reviewing}><Save size={16} /> {saving ? 'Speichere...' : 'Speichern'}</button>
        <button className="button secondary" onClick={reanalyze} disabled={saving || reanalyzing || reviewing}><Wand2 size={16} /> {reanalyzing ? 'Analysiere...' : 'Erneut analysieren'}</button>
        <button className="button secondary" onClick={markReviewed} disabled={saving || reanalyzing || reviewing}><BadgeCheck size={16} /> {reviewing ? 'Markiere...' : 'Als geprüft markieren'}</button>
        <button className="button ghost" onClick={() => setShowRaw((value) => !value)}>KI-Rohdaten</button>
      </div>
      {showRaw && <pre className="raw-json">{invoice.ai_raw_json || invoice.reason || 'Keine Rohdaten gespeichert.'}</pre>}
      </div>
    </section>
  );
}

function statusLabel(status?: Invoice['review_status']) {
  if (!status) return 'Neu';
  return {
    reviewed: 'Verarbeitet',
    exported: 'Verarbeitet',
    needs_review: 'In Prüfung',
    review: 'In Prüfung',
    error: 'Fehler',
    new: 'Neu',
    archived: 'Verarbeitet',
  }[status] ?? status;
}

function formatAmountInput(value?: number | null) {
  return value === null || value === undefined ? '' : String(value).replace('.', ',');
}

function parseAmountInput(value: string) {
  const normalized = value.trim().replace(/\./g, '').replace(',', '.');
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}
