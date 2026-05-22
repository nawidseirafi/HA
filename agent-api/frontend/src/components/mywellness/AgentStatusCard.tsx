import { Activity, AlertTriangle, CalendarClock, CheckCircle2, Clock } from 'lucide-react';
import type { AgentStatus } from '../../api/client';

interface Props {
  status: AgentStatus | null;
}

function formatDate(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}

function statusClass(status?: string) {
  if (status === 'running' || status === 'ok') return 'ok';
  if (status === 'error') return 'error';
  return 'waiting';
}

export function AgentStatusCard({ status }: Props) {
  const current = status?.current_status ?? 'loading';
  const tone = statusClass(current);

  return (
    <section className={`panel mywellness-status status-${tone}`}>
      <div className="section-title">
        <div>
          <span className="eyebrow">MyWellness Agent</span>
          <h2>Status</h2>
        </div>
        <span className={`agent-state-pill ${tone}`}>
          {tone === 'error' ? <AlertTriangle size={16} /> : tone === 'ok' ? <CheckCircle2 size={16} /> : <Clock size={16} />}
          {current}
        </span>
      </div>

      <div className="agent-status-grid">
        <div>
          <Activity size={18} />
          <span>Läuft gerade</span>
          <strong>{status?.is_running ? 'Ja' : 'Nein'}</strong>
        </div>
        <div>
          <CheckCircle2 size={18} />
          <span>Letzter erfolgreicher Lauf</span>
          <strong>{formatDate(status?.last_successful_run)}</strong>
        </div>
        <div>
          <CalendarClock size={18} />
          <span>Nächster geplanter Lauf</span>
          <strong>{formatDate(status?.next_scheduled_run)}</strong>
        </div>
      </div>

      {status?.last_error && <p className="agent-error">{status.last_error}</p>}
    </section>
  );
}
