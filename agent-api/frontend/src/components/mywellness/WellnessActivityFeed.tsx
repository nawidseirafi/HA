import { AlertTriangle, CheckCircle2, Info, Search, Zap } from 'lucide-react';
import type { MyWellnessLog } from '../../api/client';

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' }).format(date);
}

function tone(status: string) {
  if (status === 'error') return 'error';
  if (status === 'skipped') return 'warning';
  if (status === 'ok') return 'success';
  return 'info';
}

function iconFor(item: MyWellnessLog) {
  if (item.status === 'error') return AlertTriangle;
  if (item.action_type === 'prepare') return Search;
  if (item.action_type === 'book') return Zap;
  if (item.status === 'ok') return CheckCircle2;
  return Info;
}

function friendlyMessage(item: MyWellnessLog) {
  if (item.action_type === 'prepare' && item.status === 'ok') return 'Kursliste vorbereitet';
  if (item.action_type === 'book' && item.status === 'ok') return 'Buchungsaktion abgeschlossen';
  if (item.action_type === 'prepare' && item.status === 'running') return 'Kurs-Suche gestartet';
  if (item.action_type === 'book' && item.status === 'running') return 'Buchung gestartet';
  return item.message || item.action_type;
}

export function WellnessActivityFeed({ items, compact = false }: { items: MyWellnessLog[]; compact?: boolean }) {
  const visible = items.slice(0, compact ? 6 : 80);
  return (
    <section className="wellness-feed panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Activity</span>
          <h2>Verlauf</h2>
        </div>
      </div>
      <div className="wellness-feed-list">
        {visible.length === 0 && <p className="muted">Noch keine Aktivität vorhanden.</p>}
        {visible.map((item) => {
          const Icon = iconFor(item);
          return (
            <article className={`wellness-feed-item ${tone(item.status)}`} key={item.id}>
              <span><Icon size={15} /></span>
              <div>
                <strong>{friendlyMessage(item)}</strong>
                <small>{formatTime(item.created_at)} · {item.action_type}</small>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
