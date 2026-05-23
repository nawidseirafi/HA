import { Terminal } from 'lucide-react';
import type { MyWellnessLog } from '../../api/client';

interface Props {
  items: MyWellnessLog[];
  fallbackLogs: string[];
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'medium' }).format(date);
}

export function WellnessLogsTable({ items, fallbackLogs }: Props) {
  return (
    <section className="panel logs-panel wellness-logs-table">
      <div className="section-title">
        <div>
          <span className="eyebrow">Diagnose</span>
          <h2>Logs</h2>
        </div>
        <Terminal size={18} />
      </div>
      {items.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Zeit</th>
                <th>Aktion</th>
                <th>Status</th>
                <th>Meldung</th>
                <th>Laufzeit</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td data-label="Zeit">{formatDate(item.created_at)}</td>
                  <td data-label="Aktion">{item.action_type}</td>
                  <td data-label="Status"><span className={`agent-state-pill ${item.status === 'error' ? 'error' : item.status === 'ok' ? 'ok' : 'waiting'}`}>{item.status}</span></td>
                  <td data-label="Meldung">{item.message || '-'}</td>
                  <td data-label="Laufzeit">{item.duration_seconds != null ? `${item.duration_seconds.toFixed(1)}s` : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <pre>{fallbackLogs.length ? fallbackLogs.join('\n') : 'Keine Logs vorhanden.'}</pre>
      )}
    </section>
  );
}
