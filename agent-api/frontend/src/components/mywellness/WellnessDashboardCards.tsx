import { CalendarCheck, CalendarClock, CheckCircle2, Clock, Power, Sparkles } from 'lucide-react';
import type { AgentStatus } from '../../api/client';

function formatDate(value?: string | null) {
  if (!value) return '–';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}

function formatTime(value?: string | null) {
  if (!value) return '–';
  return value.slice(0, 5);
}

function nextScheduledTime(status: AgentStatus | null) {
  const action = nextScheduledAction(status);
  if (action === 'book') return formatTime(status?.booking_time);
  if (action === 'prepare') return formatTime(status?.prepare_time);
  if (action === 'health_sync') return formatTime(status?.health_sync_time);
  return formatDate(status?.next_scheduled_run);
}

function nextScheduledAction(status: AgentStatus | null) {
  if (status?.next_scheduled_action) return status.next_scheduled_action;
  if (!status?.next_scheduled_run) return null;
  if (status.health_sync_enabled !== false && status.prepare_enabled === false && status.booking_enabled === false) return 'health_sync';
  if (status.prepare_enabled !== false && status.booking_enabled === false) return 'prepare';
  if (status.booking_enabled !== false && status.prepare_enabled === false) return 'book';
  const planned = new Date(status.next_scheduled_run);
  if (!Number.isNaN(planned.getTime())) {
    const plannedTime = `${String(planned.getHours()).padStart(2, '0')}:${String(planned.getMinutes()).padStart(2, '0')}`;
    if (status.prepare_time?.slice(0, 5) === plannedTime) return 'prepare';
    if (status.booking_time?.slice(0, 5) === plannedTime) return 'book';
    if (status.health_sync_time?.slice(0, 5) === plannedTime) return 'health_sync';
  }
  return null;
}

interface Props {
  status: AgentStatus | null;
  loading?: boolean;
  onToggleAgent: () => void;
  onScan: () => void;
  onBook: () => void;
}

export function WellnessDashboardCards({ status, loading, onToggleAgent, onScan, onBook }: Props) {
  const active = status?.enabled !== false;
  const action = nextScheduledAction(status);
  const nextLabel = action === 'book' ? 'Nächste Buchung' : action === 'prepare' ? 'Nächster Kurs-Scan' : action === 'health_sync' ? 'Nächster Health-Sync' : 'Nächste Aktion';

  return (
    <section className="wellness-card-grid">
      <button
        type="button"
        className={`wellness-stat-card interactive ${active ? 'success' : 'muted'}`}
        onClick={onToggleAgent}
        disabled={loading}
        aria-pressed={active}
      >
        <div className="wellness-stat-icon"><Power size={20} /></div>
        <span>Agent Status</span>
        <strong>{active ? 'Aktiv' : 'Pausiert'}</strong>
        <em className="wellness-stat-hint">{active ? 'Tippen zum Pausieren' : 'Tippen zum Aktivieren'}</em>
        <span className={`wellness-stat-dot ${active ? 'on' : 'off'}`} aria-hidden />
      </button>

      <button
        type="button"
        className="wellness-stat-card interactive info"
        onClick={onScan}
        disabled={loading}
      >
        <div className="wellness-stat-icon"><Sparkles size={20} /></div>
        <span>Letzter Kurs-Scan</span>
        <strong>{formatDate(status?.last_prepare_run)}</strong>
        <em className="wellness-stat-hint">Jetzt scannen <CheckCircle2 size={12} /></em>
      </button>

      <button
        type="button"
        className="wellness-stat-card interactive success"
        onClick={onBook}
        disabled={loading}
      >
        <div className="wellness-stat-icon"><CalendarCheck size={20} /></div>
        <span>Letzte Buchung</span>
        <strong>{formatDate(status?.last_booking_run)}</strong>
        <em className="wellness-stat-hint">Jetzt buchen <Clock size={12} /></em>
      </button>

      <article className="wellness-stat-card warning">
        <div className="wellness-stat-icon"><CalendarClock size={20} /></div>
        <span>{nextLabel}</span>
        <strong>{nextScheduledTime(status)}</strong>
        <em className="wellness-stat-hint">automatisch geplant</em>
      </article>
    </section>
  );
}
