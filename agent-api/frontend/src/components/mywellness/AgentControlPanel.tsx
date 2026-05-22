import { PauseCircle, PlayCircle, RefreshCw } from 'lucide-react';
import type { AgentStatus } from '../../api/client';

interface Props {
  status: AgentStatus | null;
  loading: boolean;
  onStart: () => void;
  onStop: () => void;
  onRefresh: () => void;
}

export function AgentControlPanel({ status, loading, onStart, onStop, onRefresh }: Props) {
  return (
    <section className="panel control-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Steuerung</span>
          <h2>Agent Control</h2>
        </div>
      </div>
      <div className="button-row">
        <button className="button primary" type="button" onClick={onStart} disabled={loading || status?.is_running}>
          <PlayCircle size={18} />
          Starten
        </button>
        <button className="button secondary" type="button" onClick={onStop} disabled={loading || !status?.enabled}>
          <PauseCircle size={18} />
          Stoppen
        </button>
        <button className="button" type="button" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={18} />
          Aktualisieren
        </button>
      </div>
      <p>{status?.enabled === false ? 'Agent ist deaktiviert.' : 'Manueller Start aktualisiert Kursdaten im Prepare-Modus.'}</p>
    </section>
  );
}
