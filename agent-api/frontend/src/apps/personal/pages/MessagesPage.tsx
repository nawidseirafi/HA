import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AlertTriangle, Bell, Check, CircleAlert, Clock3, Info, MailOpen, RefreshCw, Search, Trash2 } from 'lucide-react';
import { api, type MessageCenterItem, type MessageSeverity } from '@shared/api/client';

type SeverityFilter = 'all' | 'unread' | 'read' | MessageSeverity;

const severityFilters: Array<{ key: SeverityFilter; label: string }> = [
  { key: 'all', label: 'Alle' },
  { key: 'unread', label: 'Ungelesen' },
  { key: 'read', label: 'Gelesen' },
  { key: 'critical', label: 'Critical' },
  { key: 'warning', label: 'Warning' },
  { key: 'info', label: 'Info' },
];

const sources = [
  'all',
  'vacation',
  'mywellness',
  'market',
  'invoice',
  'household',
  'infrastructure',
  'orchestrator',
  'system',
];

export function MessagesPage() {
  const [messages, setMessages] = useState<MessageCenterItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    setBusy('load');
    try {
      const [messagesResponse, unreadResponse] = await Promise.all([
        api.messages(500),
        api.unreadMessageCount(),
      ]);
      setMessages(sortMessages(messagesResponse.messages));
      setUnreadCount(unreadResponse.unread_count);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nachrichten konnten nicht geladen werden.');
    } finally {
      setBusy('');
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const summary = useMemo(() => {
    const todayKey = localDateKey(new Date());
    return {
      unread: unreadCount || messages.filter((item) => !item.read).length,
      critical: messages.filter((item) => item.severity === 'critical').length,
      warning: messages.filter((item) => item.severity === 'warning').length,
      today: messages.filter((item) => localDateKey(parseDate(item.created_at)) === todayKey).length,
    };
  }, [messages, unreadCount]);

  const filteredMessages = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return messages.filter((item) => {
      if (severityFilter === 'unread' && item.read) return false;
      if (severityFilter === 'read' && !item.read) return false;
      if (severityFilter !== 'all' && severityFilter !== 'unread' && severityFilter !== 'read' && item.severity !== severityFilter) return false;
      if (sourceFilter !== 'all' && normalizeSource(item.source) !== sourceFilter) return false;
      if (!needle) return true;
      return [
        item.title,
        item.message,
        item.source,
        item.category,
      ].some((value) => String(value || '').toLowerCase().includes(needle));
    });
  }, [messages, query, severityFilter, sourceFilter]);

  const markRead = async (id: number) => {
    setBusy(`read:${id}`);
    try {
      await api.markMessageRead(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nachricht konnte nicht markiert werden.');
    } finally {
      setBusy('');
    }
  };

  const markAllRead = async () => {
    setBusy('read-all');
    try {
      await api.markAllMessagesRead();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nachrichten konnten nicht markiert werden.');
    } finally {
      setBusy('');
    }
  };

  const deleteMessage = async (id: number) => {
    setBusy(`delete:${id}`);
    try {
      await api.deleteMessage(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nachricht konnte nicht gelöscht werden.');
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="page-stack messages-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Agent Console</span>
          <h1>Nachrichten</h1>
          <p>Zentrale Verwaltungsansicht für Hinweise, Warnungen und Systemmeldungen aus allen Agenten.</p>
        </div>
        <div className="messages-actions">
          <button className="button secondary" type="button" onClick={load} disabled={busy === 'load'}>
            <RefreshCw size={18} /> Aktualisieren
          </button>
          <button className="button primary" type="button" onClick={markAllRead} disabled={busy === 'read-all' || summary.unread === 0}>
            <MailOpen size={18} /> Alle gelesen
          </button>
        </div>
      </header>

      {error && <section className="panel error-panel">{error}</section>}

      <section className="messages-summary-grid">
        <SummaryCard icon={<Bell size={20} />} label="Ungelesen" value={summary.unread} tone="info" />
        <SummaryCard icon={<CircleAlert size={20} />} label="Critical" value={summary.critical} tone="critical" />
        <SummaryCard icon={<AlertTriangle size={20} />} label="Warning" value={summary.warning} tone="warning" />
        <SummaryCard icon={<Clock3 size={20} />} label="Heute" value={summary.today} tone="neutral" />
      </section>

      <section className="messages-toolbar panel">
        <div className="messages-filter-row" role="group" aria-label="Nachrichtenfilter">
          {severityFilters.map((filter) => (
            <button
              key={filter.key}
              type="button"
              className={severityFilter === filter.key ? 'active' : ''}
              onClick={() => setSeverityFilter(filter.key)}
            >
              {filter.label}
            </button>
          ))}
        </div>
        <label className="messages-source-filter">
          <span>Quelle</span>
          <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
            {sources.map((source) => (
              <option key={source} value={source}>{source === 'all' ? 'Alle Quellen' : sourceLabel(source)}</option>
            ))}
          </select>
        </label>
        <label className="messages-search">
          <Search size={18} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Titel, Nachricht oder Quelle suchen"
          />
        </label>
      </section>

      <section className="messages-list" aria-live="polite">
        {filteredMessages.length === 0 ? (
          <div className="panel messages-empty">
            <Bell size={22} />
            <strong>Keine Nachrichten gefunden</strong>
            <p>Ändere Filter oder Suche, um weitere Nachrichten anzuzeigen.</p>
          </div>
        ) : filteredMessages.map((message) => (
          <article className={`message-card ${message.severity} ${message.read ? 'read' : 'unread'}`} key={message.id}>
            <div className="message-card-icon">{severityIcon(message.severity)}</div>
            <div className="message-card-body">
              <div className="message-card-head">
                <div>
                  <span className={`message-severity ${message.severity}`}>{severityLabel(message.severity)}</span>
                  <h2>{message.title}</h2>
                </div>
                <span className={`message-read-state ${message.read ? 'read' : 'unread'}`}>{message.read ? 'gelesen' : 'ungelesen'}</span>
              </div>
              <p>{message.message}</p>
              <div className="message-meta">
                <span>{sourceLabel(message.source)}</span>
                <span>{formatDateTime(message.created_at)}</span>
              </div>
            </div>
            <div className="message-card-actions">
              {!message.read && (
                <button
                  className="icon-button"
                  type="button"
                  title="Als gelesen markieren"
                  aria-label="Als gelesen markieren"
                  disabled={busy === `read:${message.id}`}
                  onClick={() => markRead(message.id)}
                >
                  <Check size={18} />
                </button>
              )}
              <button
                className="icon-button danger"
                type="button"
                title="Nachricht löschen"
                aria-label="Nachricht löschen"
                disabled={busy === `delete:${message.id}`}
                onClick={() => deleteMessage(message.id)}
              >
                <Trash2 size={18} />
              </button>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

function SummaryCard({ icon, label, value, tone }: { icon: ReactNode; label: string; value: number; tone: 'info' | 'warning' | 'critical' | 'neutral' }) {
  return (
    <article className={`messages-summary-card ${tone}`}>
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function sortMessages(items: MessageCenterItem[]) {
  return [...items].sort((left, right) => parseDate(right.created_at).getTime() - parseDate(left.created_at).getTime());
}

function normalizeSource(value: string) {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'invoices') return 'invoice';
  return normalized;
}

function sourceLabel(value: string) {
  const normalized = normalizeSource(value);
  const labels: Record<string, string> = {
    vacation: 'Vacation Agent',
    mywellness: 'MyWellness Agent',
    market: 'Market Agent',
    invoice: 'Invoice Agent',
    household: 'Household',
    infrastructure: 'Infrastructure',
    orchestrator: 'Orchestrator',
    system: 'System',
    all: 'Alle Quellen',
  };
  return labels[normalized] ?? value;
}

function severityLabel(value: MessageSeverity) {
  if (value === 'critical') return 'Critical';
  if (value === 'warning') return 'Warning';
  return 'Info';
}

function severityIcon(value: MessageSeverity) {
  if (value === 'critical') return <CircleAlert size={20} />;
  if (value === 'warning') return <AlertTriangle size={20} />;
  return <Info size={20} />;
}

function parseDate(value?: string | null) {
  if (!value) return new Date(0);
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date : new Date(0);
}

function localDateKey(date: Date) {
  if (!Number.isFinite(date.getTime())) return '';
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function formatDateTime(value?: string | null) {
  const date = parseDate(value);
  if (!Number.isFinite(date.getTime()) || date.getTime() === 0) return '-';
  return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function pad(value: number) {
  return String(value).padStart(2, '0');
}
