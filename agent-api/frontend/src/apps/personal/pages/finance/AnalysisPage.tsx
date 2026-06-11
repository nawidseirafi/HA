import { useEffect, useState } from 'react';
import { Activity, AlertTriangle, BrainCircuit, CalendarClock, Euro, RefreshCw } from 'lucide-react';
import { api } from '@shared/api/client';
import type { ContractAnalysis } from '@shared/types/invoice';
import { currency, shortDate } from '@shared/utils/format';
import type { Route } from '../../App';

export function AnalysisPage({ navigate }: { navigate: (route: Route) => void }) {
  const [analysis, setAnalysis] = useState<ContractAnalysis | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadAnalysis = async () => {
    setBusy(true);
    setError('');
    try {
      setAnalysis(await api.contractAnalysis());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analyse konnte nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { loadAnalysis(); }, []);

  return (
    <div className="page-stack">
      <header className="dashboard-hero finance-hero">
        <div>
          <span className="eyebrow">Finance · Analysen</span>
          <h1>Optimierungshinweise</h1>
          <p>Die Analyse wird aus deinen gespeicherten Verträgen berechnet. Empfehlungen, keine automatischen Entscheidungen.</p>
        </div>
        <div className="invoice-hero-actions">
          <button className="button primary" onClick={loadAnalysis} disabled={busy}>
            {busy ? <Activity size={16} /> : <RefreshCw size={16} />}
            {busy ? 'Analysiere...' : 'Analyse aktualisieren'}
          </button>
        </div>
      </header>
      {error && <section className="panel error-panel"><AlertTriangle size={18} /> {error}</section>}
      <section className="dashboard-grid">
        <div className="panel wide-panel">
          <div className="section-title"><div><span className="eyebrow">Hinweise</span><h2>Prüfpunkte</h2></div></div>
          <div className="analysis-list">
            {(analysis?.hints ?? []).map((hint, index) => (
              <button key={`${hint.contract_id}-${hint.type}-${index}`} className={`analysis-card ${hint.severity}`} onClick={() => navigate({ name: 'contract', id: hint.contract_id })}>
                <BrainCircuit size={18} />
                <div className="analysis-card-body">
                  <div className="analysis-card-title">
                    <strong>{hint.name}</strong>
                    <span>{hint.provider || 'Anbieter offen'}</span>
                  </div>
                  <p>{hint.message}</p>
                </div>
              </button>
            ))}
            {analysis && !analysis.hints.length && <p className="muted-text">Keine kritischen Hinweise gefunden.</p>}
          </div>
        </div>
        <aside className="quick-stack">
          <div className="panel system-panel">
            <div className="section-title"><div><span className="eyebrow">Top-Kosten</span><h2>Monatlich am teuersten</h2></div></div>
            {(analysis?.most_expensive ?? []).map((contract) => <button key={contract.id} className="mini-contract-row" onClick={() => navigate({ name: 'contract', id: contract.id })}><Euro size={16} /><span>{contract.name}</span><strong>{currency(contract.monthly_cost)}</strong></button>)}
          </div>
          <div className="panel system-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">In den nächsten 6 Monaten</span>
                <h2>Ende oder Verlängerung</h2>
                <p className="section-help">Verträge mit Enddatum oder Verlängerungsdatum innerhalb von 6 Monaten.</p>
              </div>
            </div>
            {(analysis?.ending_next_6_months ?? []).map((contract) => (
              <button key={contract.id} className="mini-contract-row due-row" onClick={() => navigate({ name: 'contract', id: contract.id })}>
                <CalendarClock size={16} />
                <span>
                  {contract.name}
                  <small>{contract.end_date ? 'Enddatum' : 'Verlängerung'}</small>
                </span>
                <strong>{shortDate(contract.end_date || contract.renewal_date || '')}</strong>
              </button>
            ))}
            {analysis && !analysis.ending_next_6_months.length && <p className="muted-text">Keine bekannten End- oder Verlängerungsdaten in den nächsten 6 Monaten.</p>}
          </div>
        </aside>
      </section>
    </div>
  );
}
