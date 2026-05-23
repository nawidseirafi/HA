import { CalendarClock, CheckCircle2, Clock, Power } from 'lucide-react';
import type { AgentStatus } from '../../api/client';

function formatDate(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}

export function WellnessDashboardCards({ status }: { status: AgentStatus | null }) {
  const cards = [
    { label: 'Agent Status', value: status?.enabled ? 'Aktiv' : 'Pausiert', icon: Power, tone: status?.enabled ? 'success' : 'muted' },
    { label: 'Letzter Kurs-Scan', value: formatDate(status?.last_prepare_run), icon: CheckCircle2, tone: 'info' },
    { label: 'Letzte Buchung', value: formatDate(status?.last_booking_run), icon: Clock, tone: 'success' },
    { label: 'Nächste Aktion', value: formatDate(status?.next_scheduled_run), icon: CalendarClock, tone: 'warning' },
  ];
  return (
    <section className="wellness-card-grid">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <article className={`wellness-stat-card ${card.tone}`} key={card.label}>
            <div><Icon size={19} /></div>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
          </article>
        );
      })}
    </section>
  );
}
