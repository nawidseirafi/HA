import { Power } from 'lucide-react';
import type { AgentStatus } from '../../api/client';

interface Props {
  status: AgentStatus | null;
  loading: boolean;
  onToggle: () => void;
}

export function WellnessToggle({ status, loading, onToggle }: Props) {
  const active = status?.enabled !== false;
  return (
    <section className="panel wellness-toggle-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Toggle</span>
          <h2>Agent {active ? 'aktiv' : 'inaktiv'}</h2>
        </div>
      </div>
      <button className={`wellness-switch ${active ? 'on' : 'off'}`} type="button" onClick={onToggle} disabled={loading}>
        <span><Power size={16} /></span>
        {active ? 'Deaktivieren' : 'Aktivieren'}
      </button>
      <p>Home Assistant läuft aktuell noch parallel.</p>
    </section>
  );
}
