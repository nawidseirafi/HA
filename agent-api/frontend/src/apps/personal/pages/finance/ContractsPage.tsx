import { useEffect, useRef, useState } from 'react';
import { Activity, AlertTriangle, CalendarClock, FileText, Plus, Upload } from 'lucide-react';
import { api } from '@shared/api/client';
import type { Contract, ContractCategory } from '@shared/types/invoice';
import { currency, shortDate } from '@shared/utils/format';
import type { Route } from '../../App';

const CATEGORY_OPTIONS: Array<{ value: ContractCategory; label: string }> = [
  { value: 'insurance', label: 'Versicherungen' },
  { value: 'energy', label: 'Energie' },
  { value: 'telecommunication', label: 'Telekommunikation' },
  { value: 'subscription', label: 'Abonnements' },
  { value: 'membership', label: 'Mitgliedschaften' },
  { value: 'financial_obligation', label: 'Verpflichtungen' },
  { value: 'other', label: 'Sonstige' },
];

export function ContractsPage({ navigate, category }: { navigate: (route: Route) => void; category?: string }) {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    const params = new URLSearchParams();
    if (category) params.set('category', category);
    const data = await api.contracts(params);
    setContracts(data.contracts);
  };

  useEffect(() => { load().catch((err) => setError(err instanceof Error ? err.message : 'Verträge konnten nicht geladen werden.')); }, [category]);

  const upload = async (file?: File) => {
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.uploadContractDocument(file);
      setError(result.message || 'Dokument hochgeladen und Contract-Entwurf angelegt.');
      await load();
      navigate({ name: 'contract', id: result.contract.id });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-stack">
      <header className="dashboard-hero finance-hero">
        <div>
          <span className="eyebrow">Finance · Contracts</span>
          <h1>{categoryLabel(category) || 'Verträge'}</h1>
          <p>Laufende Verpflichtungen, Versicherungen, Energie, Telekommunikation und Abos als prüfbare Karten.</p>
        </div>
        <div className="invoice-hero-actions">
          <button className="button secondary" onClick={() => fileRef.current?.click()} disabled={busy}><Upload size={16} /> Dokument hochladen</button>
          <button className="button primary" onClick={() => setFormOpen((value) => !value)} disabled={busy}><Plus size={16} /> Vertrag anlegen</button>
          <input ref={fileRef} type="file" hidden onChange={(event) => upload(event.target.files?.[0])} />
        </div>
      </header>

      {error && <section className={`panel ${error.includes('hochgeladen') ? 'status-panel' : 'error-panel'}`}><div className="agent-run-status"><AlertTriangle size={18} /><span>{error}</span></div></section>}

      {formOpen && <ContractForm onCreated={async () => { setFormOpen(false); await load(); }} />}

      <section className="contract-filter-row">
        <button className={!category ? 'active' : ''} onClick={() => navigate({ name: 'contracts' })}>Alle</button>
        {CATEGORY_OPTIONS.map((item) => (
          <button key={item.value} className={category === item.value ? 'active' : ''} onClick={() => navigate({ name: 'contracts', category: item.value })}>{item.label}</button>
        ))}
      </section>

      <section className="contract-card-grid">
        {contracts.map((contract) => (
          <button key={contract.id} className="contract-card" onClick={() => navigate({ name: 'contract', id: contract.id })}>
            <div className="contract-card-top">
              <span className="contract-pill">{contract.category_label || categoryLabel(contract.category)}</span>
              <span className={`review-badge ${contract.status === 'active' ? 'reviewed' : 'needs_review'}`}>{statusLabel(contract.status)}</span>
            </div>
            <h2>{contract.name}</h2>
            <p>{contract.provider || 'Anbieter offen'} · {contract.subcategory || 'Unterkategorie offen'}</p>
            <div className="contract-money">{currency(contract.monthly_cost)} <span>/ Monat</span></div>
            <div className="contract-meta-row"><CalendarClock size={15} /> Frist: {contract.renewal_date || contract.end_date ? shortDate(contract.renewal_date || contract.end_date || '') : 'offen'}</div>
            {contract.document_id && <div className="contract-meta-row"><FileText size={15} /> Dokument verknüpft</div>}
          </button>
        ))}
        {!contracts.length && <div className="panel empty-contract-panel"><Activity size={20} /><span>Noch keine Verträge in dieser Ansicht.</span></div>}
      </section>
    </div>
  );
}

function ContractForm({ onCreated }: { onCreated: () => void }) {
  const [payload, setPayload] = useState<Partial<Contract>>({ category: 'other', status: 'needs_review', auto_renew: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const save = async () => {
    setBusy(true);
    setError('');
    try {
      await api.createContract(payload);
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Vertrag konnte nicht gespeichert werden.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="panel contract-form-panel">
      <div className="section-title"><div><span className="eyebrow">Manuell</span><h2>Neuen Vertrag anlegen</h2></div></div>
      <div className="contract-form-grid">
        <input placeholder="Name" value={payload.name || ''} onChange={(e) => setPayload({ ...payload, name: e.target.value })} />
        <input placeholder="Anbieter" value={payload.provider || ''} onChange={(e) => setPayload({ ...payload, provider: e.target.value })} />
        <select value={payload.category || 'other'} onChange={(e) => setPayload({ ...payload, category: e.target.value as ContractCategory })}>{CATEGORY_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
        <input placeholder="Unterkategorie" value={payload.subcategory || ''} onChange={(e) => setPayload({ ...payload, subcategory: e.target.value })} />
        <input type="number" step="0.01" placeholder="Monatliche Kosten" value={payload.monthly_cost ?? ''} onChange={(e) => setPayload({ ...payload, monthly_cost: Number(e.target.value) || null })} />
        <input placeholder="Kündigungsfrist, z.B. 3 Monate" value={payload.cancellation_period || ''} onChange={(e) => setPayload({ ...payload, cancellation_period: e.target.value })} />
        <input type="date" value={payload.start_date || ''} onChange={(e) => setPayload({ ...payload, start_date: e.target.value })} />
        <input type="date" value={payload.renewal_date || ''} onChange={(e) => setPayload({ ...payload, renewal_date: e.target.value })} />
      </div>
      {error && <p className="form-error">{error}</p>}
      <div className="button-row"><button className="button primary" onClick={save} disabled={busy}>{busy ? 'Speichert...' : 'Vertrag speichern'}</button></div>
    </section>
  );
}

function categoryLabel(value?: string) {
  return CATEGORY_OPTIONS.find((item) => item.value === value)?.label || '';
}

function statusLabel(value: string) {
  if (value === 'active') return 'Aktiv';
  if (value === 'needs_review') return 'Prüfen';
  if (value === 'cancelled') return 'Gekündigt';
  if (value === 'expired') return 'Abgelaufen';
  return value || 'Offen';
}
