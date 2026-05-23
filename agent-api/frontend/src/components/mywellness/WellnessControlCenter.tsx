import { CalendarCheck, Pause, Play, Sparkles } from 'lucide-react';
import type { AgentStatus } from '../../api/client';

interface Props {
  status: AgentStatus | null;
  loading: boolean;
  onEnable: () => void;
  onDisable: () => void;
  onPrepare: () => void;
  onBook: () => void;
}

export function WellnessControlCenter({ status, loading, onEnable, onDisable, onPrepare, onBook }: Props) {
  const active = status?.enabled !== false;
  return (
    <section className="wellness-control-card">
      <div className="wellness-control-copy">
        <span className="eyebrow">Control Center</span>
        <h2>{active ? 'Bereit für deine nächsten Kurse' : 'Agent pausiert'}</h2>
        <p>{active ? 'Der Agent beobachtet deinen Zeitplan und führt die geplanten Aktionen automatisch aus.' : 'Automatische Aktionen sind pausiert. Manuelle Aktionen bleiben verfügbar.'}</p>
      </div>
      <div className="wellness-control-actions">
        {active ? (
          <button className="button secondary" type="button" onClick={onDisable} disabled={loading}><Pause size={17} /> Agent pausieren</button>
        ) : (
          <button className="button primary" type="button" onClick={onEnable} disabled={loading}><Play size={17} /> Agent aktivieren</button>
        )}
        <button className="button" type="button" onClick={onPrepare} disabled={loading}><Sparkles size={17} /> Kurse vorbereiten</button>
        <button className="button primary" type="button" onClick={onBook} disabled={loading}><CalendarCheck size={17} /> Jetzt buchen</button>
      </div>
    </section>
  );
}
