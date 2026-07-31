import { AlertTriangle, BarChart3, Bell, Bot, BrainCircuit, Home, Layers3, Lightbulb, Loader2, Moon, RefreshCw, ShieldAlert, Thermometer, Users, Warehouse, Zap } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api, type ContextStatus, type MessageCenterItem } from '@shared/api/client';
import '@shared/styles/wall.css';

const WALL_CONTEXT_POLL_MS = 10000;

export function WallStevePage() {
  const [status, setStatus] = useState<ContextStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [now, setNow] = useState(new Date());
  const [messages, setMessages] = useState<MessageCenterItem[]>([]);
  const [unreadMessages, setUnreadMessages] = useState(0);
  const [messageCenterOpen, setMessageCenterOpen] = useState(false);

  const load = useCallback(async () => {
    setError('');
    try {
      const [nextStatus, unreadData] = await Promise.all([
        api.contextStatus(),
        api.unreadMessageCount().catch(() => ({ unread_count: 0 })),
      ]);
      setStatus(nextStatus);
      setUnreadMessages(unreadData.unread_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Steve Context konnte nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), WALL_CONTEXT_POLL_MS);
    const clock = window.setInterval(() => setNow(new Date()), 1000);
    return () => {
      window.clearInterval(timer);
      window.clearInterval(clock);
    };
  }, [load]);

  const summary = status?.summary || status?.reason || status?.message || 'ContextService liefert noch keinen Steve-denkt-Text.';

  const openMessageCenter = async () => {
    setMessageCenterOpen((current) => !current);
    try {
      const [messageData, unreadData] = await Promise.all([
        api.messages(20),
        api.unreadMessageCount(),
      ]);
      setMessages(messageData.messages);
      setUnreadMessages(unreadData.unread_count);
    } catch {
      setMessages([]);
    }
  };

  return (
    <main className="wall-shell" data-testid="wall-steve-page">
      <aside className="wall-nav">
        <button type="button" onClick={() => navigateWall('/wall?section=home')} aria-label="Home"><Home size={24} /></button>
        <button type="button" onClick={() => navigateWall('/wall?section=floor')} aria-label="Etagen"><Layers3 size={24} /></button>
        <button type="button" onClick={() => navigateWall('/wall?section=lights')} aria-label="Lampen"><Lightbulb size={24} /></button>
        <button type="button" onClick={() => navigateWall('/wall?section=climate')} aria-label="Klima"><Thermometer size={24} /></button>
        <button type="button" onClick={() => navigateWall('/wall?section=energy')} aria-label="Energie"><Zap size={24} /></button>
        <button type="button" onClick={() => navigateWall('/wall?section=security')} aria-label="Sicherheit"><ShieldAlert size={24} /></button>
        <button type="button" onClick={() => navigateWall('/wall?section=agents')} aria-label="Agenten"><Bot size={24} /></button>
        <button className="active" type="button" aria-label="Steve"><BrainCircuit size={24} /></button>
      </aside>
      <section className="wall-main wall-steve-main">
        <header className="wall-header">
          <div>
            <span>{formatWallDate(now)}</span>
            <div className="wall-title-row">
              <h1><BrainCircuit size={30} /> Steve</h1>
              <span className="wall-internet-pill ok" aria-label="ContextService verbunden" title="ContextService verbunden" />
            </div>
            <p>{status ? `Context aktualisiert ${formatWallTime(status.updated_at)}` : 'Steve liest den aktuellen Kontext'}</p>
          </div>
          <div className="wall-header-side">
            <strong>{formatClock(now)}</strong>
            <button className={`wall-message-button ${unreadMessages ? 'has-unread' : ''}`} type="button" onClick={openMessageCenter} aria-label="Nachrichten">
              <Bell size={18} />
              {unreadMessages > 0 && <span>{unreadMessages > 99 ? '99+' : unreadMessages}</span>}
            </button>
            <button type="button" onClick={load} aria-label="Aktualisieren">
              <RefreshCw size={18} /> Aktualisieren
            </button>
          </div>
        </header>
        {messageCenterOpen && <WallSteveMessageCenter messages={messages} />}

        <section className="wall-steve-hero">
          <div className="wall-steve-icon"><BrainCircuit size={42} /></div>
          <div>
            <span>Steve denkt ...</span>
            <h2>{summary}</h2>
          </div>
        </section>

        {loading && !status && (
          <section className="wall-steve-state">
            <Loader2 size={22} />
            <strong>Steve liest den Kontext.</strong>
          </section>
        )}
        {error && !status && (
          <section className="wall-steve-state error">
            <AlertTriangle size={22} />
            <strong>{error}</strong>
          </section>
        )}

        {status && (
          <section className="wall-steve-grid">
            <WallSteveCard icon={<Home size={24} />} label="Hausstatus" value={status.house} />
            <WallSteveCard icon={<Users size={24} />} label="Anwesenheit" value={status.presence} />
            <WallSteveCard icon={<Warehouse size={24} />} label="Garage" value={status.garage} />
            <WallSteveCard icon={<Moon size={24} />} label="Schlaf" value={status.sleep || '-'} />
            <WallSteveCard icon={<Users size={24} />} label="Gäste" value={status.guest ? 'JA' : 'NEIN'} />
            <WallSteveCard icon={<BarChart3 size={24} />} label="Confidence" value={`${Math.round(Number(status.confidence || 0) * 100)} %`} />
          </section>
        )}
      </section>
    </main>
  );
}

function navigateWall(path: string) {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function WallSteveMessageCenter({ messages }: { messages: MessageCenterItem[] }) {
  return (
    <section className="wall-message-center wall-steve-message-center">
      <div className="wall-message-center-head">
        <div>
          <span>Nachrichten</span>
          <strong>Message Center</strong>
        </div>
      </div>
      {messages.length === 0 && <div className="wall-message-empty">Keine Nachrichten vorhanden.</div>}
      {messages.slice(0, 6).map((item) => (
        <article key={item.id} className={`wall-message-card ${item.severity} ${item.read ? 'read' : 'unread'}`}>
          <span className="wall-message-icon">{item.severity === 'info' ? 'i' : '!'}</span>
          <div>
            <strong>{item.title}</strong>
            <p>{item.message}</p>
            <small>{formatWallTime(item.created_at)}</small>
          </div>
        </article>
      ))}
    </section>
  );
}

function WallSteveCard({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <article className="wall-steve-card">
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function formatClock(date: Date) {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatWallDate(date: Date) {
  const weekdays = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'];
  const months = ['Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  return `${weekdays[date.getDay()]}, ${pad(date.getDate())}. ${months[date.getMonth()]}`;
}

function formatWallTime(value?: string) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' }).format(date);
}

function pad(value: number) {
  return String(value).padStart(2, '0');
}
