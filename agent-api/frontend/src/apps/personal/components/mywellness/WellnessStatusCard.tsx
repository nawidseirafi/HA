import { AlertTriangle, CalendarClock, CheckCircle2, Clock } from 'lucide-react';
import type { AgentStatus } from '@shared/api/client';

interface Props {
  status: AgentStatus | null;
}

function formatDate(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}

function tone(status?: string) {
  if (status === 'running' || status === 'ok' || status === 'enabled') return 'ok';
  if (status === 'error') return 'error';
  return 'waiting';
}

export function WellnessStatusCard({ status }: Props) {
  const state = status?.current_status ?? status?.last_status ?? 'loading';
  const statusTone = tone(state);
  return (
    <section className={`panel mywellness-status status-${statusTone}`}>
      <div className="section-title">
        <div>
          <span className="eyebrow">MyWellness Agent</span>
          <h2>Status</h2>
        </div>
        <span className={`agent-state-pill ${statusTone}`}>
          {statusTone === 'error' ? <AlertTriangle size={16} /> : statusTone === 'ok' ? <CheckCircle2 size={16} /> : <Clock size={16} />}
          {status?.enabled ? 'Aktiv' : 'Inaktiv'}
        </span>
      </div>
      <div className="agent-status-grid">
        <div>
          <Clock size={18} />
          <span>Aktueller Status</span>
          <strong>{state}</strong>
        </div>
        <div>
          <CalendarClock size={18} />
          <span>Letzter Prepare Lauf</span>
          <strong>{formatDate(status?.last_prepare_run)}</strong>
        </div>
        <div>
          <CalendarClock size={18} />
          <span>Letzter Booking Lauf</span>
          <strong>{formatDate(status?.last_booking_run)}</strong>
        </div>
      </div>
      {status?.last_error && <p className="agent-error">{status.last_error}</p>}
    </section>
  );
}
