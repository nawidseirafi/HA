import { useEffect, useState } from 'react';
import { AlertTriangle, BrainCircuit, CalendarClock, CheckCircle2, ExternalLink, Save, Trash2 } from 'lucide-react';
import { api } from '@shared/api/client';
import type { Contract } from '@shared/types/invoice';
import { currency, shortDate } from '@shared/utils/format';
import type { Route } from '../../App';

export function ContractDetailPage({ id, navigate }: { id: number; navigate: (route: Route) => void }) {
  const [contract, setContract] = useState<Contract | null>(null);
  const [draft, setDraft] = useState<Partial<Contract>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = async () => {
    const data = await api.contract(id);
    setContract(data);
    setDraft(data);
  };
  useEffect(() => { load().catch((err) => setError(err instanceof Error ? err.message : 'Vertrag konnte nicht geladen werden.')); }, [id]);

  const save = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const updated = await api.updateContract(id, editableContractPayload(draft));
      setContract(updated);
      setDraft(updated);
      setNotice('Vertrag gespeichert.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Speichern fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!contract || !confirm(`Vertrag ${contract.name} löschen?`)) return;
    await api.deleteContract(contract.id);
    navigate({ name: 'contracts' });
  };

  const updateCancellationPeriod = (value: string) => {
    setDraft((current) => ({ ...current, cancellation_period: value }));
  };

  if (!contract) return <div className="page-stack"><section className="panel">Vertrag wird geladen...</section></div>;
  const nextCancellation = contract.next_cancellation;
  const nextCancellationLabel = nextCancellation?.deadline ? shortDate(nextCancellation.deadline) : 'offen';
  const nextCancellationNote = cancellationNote(nextCancellation, contract.cancellation_period);

  return (
    <div className="page-stack">
      <header className="dashboard-hero finance-hero">
        <div>
          <span className="eyebrow">Finance · Vertragsdetail</span>
          <h1>{contract.name}</h1>
          <p>{contract.provider || 'Anbieter offen'} · {contract.category_label}</p>
        </div>
        <div className="invoice-hero-actions">
          <button className="button ghost" onClick={() => navigate({ name: 'contracts' })}>Zurück</button>
          <button className="button primary" onClick={save} disabled={busy}><Save size={16} /> Speichern</button>
          <button className="button ghost" onClick={remove} disabled={busy}><Trash2 size={16} /> Löschen</button>
        </div>
      </header>

      {error && <section className="panel error-panel"><div className="agent-run-status"><AlertTriangle size={18} /><span>{error}</span></div></section>}
      {notice && <section className="panel success-panel"><span>{notice}</span></section>}

      <section className="kpi-grid contract-detail-kpis">
        <Kpi label="Monatlich" value={currency(contract.monthly_cost)} />
        <Kpi label="Jährlich" value={currency(contract.annual_cost)} />
        <Kpi label="Laufzeit bis" value={contract.end_date ? shortDate(contract.end_date) : 'offen'} />
        <Kpi label="Verlängerung" value={contract.renewal_date ? shortDate(contract.renewal_date) : 'offen'} />
        <Kpi label="Nächste Beendigung" value={nextCancellationLabel} note={nextCancellationNote} />
      </section>

      <section className="dashboard-grid">
        <div className="panel wide-panel contract-form-panel">
          <div className="section-title"><div><span className="eyebrow">Stammdaten</span><h2>Vertrag prüfen</h2></div></div>
          <div className="contract-form-grid">
            <label className="contract-field">
              <span>Vertragsname</span>
              <input value={draft.name || ''} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="z.B. Stromtarif Zuhause" />
            </label>
            <label className="contract-field">
              <span>Anbieter</span>
              <input value={draft.provider || ''} onChange={(e) => setDraft({ ...draft, provider: e.target.value })} placeholder="z.B. MAINGAU Energie GmbH" />
            </label>
            <label className="contract-field">
              <span>Unterkategorie</span>
              <input value={draft.subcategory || ''} onChange={(e) => setDraft({ ...draft, subcategory: e.target.value })} placeholder="z.B. Strom, Kfz, Internet" />
            </label>
            <label className="contract-field">
              <span>Status</span>
              <select value={draft.status || 'needs_review'} onChange={(e) => setDraft({ ...draft, status: e.target.value })}>
                <option value="needs_review">Prüfen</option><option value="active">Aktiv</option><option value="paused">Pausiert</option><option value="cancelled">Gekündigt</option><option value="expired">Abgelaufen</option>
              </select>
            </label>
            <label className="contract-field">
              <span>Monatliche Kosten</span>
              <input type="number" step="0.01" value={draft.monthly_cost ?? ''} onChange={(e) => setDraft({ ...draft, monthly_cost: Number(e.target.value) || null })} placeholder="0,00" />
            </label>
            <label className="contract-field">
              <span>Kündigungsfrist</span>
              <input value={draft.cancellation_period || ''} onChange={(e) => updateCancellationPeriod(e.target.value)} placeholder="z.B. 1 Monat, 30 Tage" />
            </label>
            <label className="contract-field">
              <span>Startdatum</span>
              <div className="contract-date-input">
                <input type="date" value={dateInputValue(draft.start_date)} onChange={(e) => setDraft({ ...draft, start_date: e.target.value || null })} />
                <button type="button" onClick={() => setDraft({ ...draft, start_date: null })}>Leeren</button>
              </div>
            </label>
            <label className="contract-field">
              <span>Enddatum</span>
              <div className="contract-date-input">
                <input type="date" value={dateInputValue(draft.end_date)} onChange={(e) => setDraft({ ...draft, end_date: e.target.value || null })} />
                <button type="button" onClick={() => setDraft({ ...draft, end_date: null })}>Leeren</button>
              </div>
            </label>
            <label className="contract-field">
              <span>Verlängerungsdatum</span>
              <div className="contract-date-input">
                <input type="date" value={dateInputValue(draft.renewal_date)} onChange={(e) => setDraft({ ...draft, renewal_date: e.target.value || null })} />
              <button type="button" onClick={() => setDraft({ ...draft, renewal_date: null })}>Leeren</button>
              </div>
            </label>
          </div>
          <p className="contract-form-help">Bei monatlich oder jederzeit kündbaren Verträgen wird die nächste mögliche Beendigung dynamisch aus dem heutigen Datum plus Kündigungsfrist berechnet.</p>
          <label className="contract-field contract-notes-field">
            <span>Notizen / KI-Bewertung</span>
            <textarea className="contract-notes" placeholder="Zusammenfassung, offene Punkte oder KI-Hinweise" value={draft.notes || ''} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
          </label>
        </div>

        <aside className="quick-stack">
          <div className="panel system-panel">
            <div className="section-title"><div><span className="eyebrow">Bewertung</span><h2>KI-Hinweise</h2></div></div>
            <StatusRow icon={BrainCircuit} label="Status" value={contract.status === 'needs_review' ? 'Manuell prüfen' : 'Bestätigt'} />
            <StatusRow icon={CalendarClock} label="Kündigungsfrist" value={contract.cancellation_period || 'offen'} />
            <StatusRow icon={CheckCircle2} label="Auto-Renew" value={contract.auto_renew ? 'Ja' : 'Nein'} />
            {contract.document_id && <button className="button secondary" onClick={() => navigate({ name: 'invoice', id: contract.document_id! })}><ExternalLink size={16} /> Vertragsdokument öffnen</button>}
          </div>
        </aside>
      </section>
    </div>
  );
}

function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="kpi-card blue"><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</div>;
}

function StatusRow({ icon: Icon, label, value }: { icon: typeof BrainCircuit; label: string; value: string }) {
  return <div className="status-row"><Icon size={17} /><span>{label}</span><strong>{value}</strong></div>;
}

function dateInputValue(value: unknown) {
  return typeof value === 'string' ? value.slice(0, 10) : '';
}

function editableContractPayload(draft: Partial<Contract>): Partial<Contract> {
  return {
    name: draft.name,
    provider: draft.provider,
    category: draft.category,
    subcategory: draft.subcategory,
    monthly_cost: draft.monthly_cost,
    start_date: dateInputValue(draft.start_date) || null,
    end_date: dateInputValue(draft.end_date) || null,
    renewal_date: dateInputValue(draft.renewal_date) || null,
    cancellation_period: draft.cancellation_period,
    auto_renew: draft.auto_renew,
    status: draft.status,
    notes: draft.notes,
    document_id: draft.document_id,
  };
}

function cancellationNote(nextCancellation: Contract['next_cancellation'], period?: string | null) {
  if (!nextCancellation) return period || 'Keine Kündigungsfrist hinterlegt';
  if (nextCancellation.rolling) return `${period || 'Kündigungsfrist'} · dynamisch berechnet`;
  if (nextCancellation.days_left < 0) {
    const days = Math.abs(nextCancellation.days_left);
    return `überfällig seit ${days === 1 ? '1 Tag' : `${days} Tagen`}`;
  }
  if (nextCancellation.days_left === 0) return 'heute fällig';
  return `in ${nextCancellation.days_left === 1 ? '1 Tag' : `${nextCancellation.days_left} Tagen`}`;
}
