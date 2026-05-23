import { CalendarCheck, CalendarClock, CheckCircle2, Clock, Power, Sparkles } from 'lucide-react';
import type { AgentStatus } from '../../api/client';

function formatDate(value?: string | null) {
  if (!value) return '–';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'short' }).format(date);
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
        <span>Kurs-Scan</span>
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
        <span>Buchung</span>
        <strong>{formatDate(status?.last_booking_run)}</strong>
        <em className="wellness-stat-hint">Jetzt buchen <Clock size={12} /></em>
      </button>

      <article className="wellness-stat-card warning">
        <div className="wellness-stat-icon"><CalendarClock size={20} /></div>
        <span>Nächste Aktion</span>
        <strong>{formatDate(status?.next_scheduled_run)}</strong>
        <em className="wellness-stat-hint">automatisch geplant</em>
      </article>
    </section>
  );
}
