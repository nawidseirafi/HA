import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, RefreshCw, Send, Trash2 } from 'lucide-react';
import { request } from '@shared/api/client';
import './home-hub.css';

type Status = { quality: string; monitor_only?: boolean; deliveries?: Record<string, number>; counts: Record<string, number>; error: string | null; registry_errors: Record<string, string> };
type Entity = { entity_id: string; name: string; state: string; device_name?: string; area?: string; last_updated?: string };
type Inventory = { items: Entity[]; total: number; next_offset: number | null };
type Message = { role: string; text: string };
type Event = { id: number; kind: string; subject: string; observed_at: string; payload: unknown };

export function HomeHubPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [tab, setTab] = useState('chat');
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [agents, setAgents] = useState<{ id: string; name: string; runtime: unknown }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const bottom = useRef<HTMLDivElement>(null);
  const loadStatus = useCallback(async () => {
    try { setStatus(await request<Status>('/api/home-hub/status')); }
    catch (err) { setError(String(err)); }
  }, []);

  useEffect(() => {
    void loadStatus();
    request<{ items: Message[] }>('/api/home-hub/conversation').then(data => setMessages(data.items)).catch(err => setError(String(err)));
    const timer = window.setInterval(loadStatus, 15000);
    return () => window.clearInterval(timer);
  }, [loadStatus]);
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'nearest' }); }, [messages]);
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        if (tab === 'entities') {
          const data = await request<Inventory>(`/api/home-hub/entities?query=${encodeURIComponent(query)}&offset=${offset}&limit=30`);
          if (!cancelled) setInventory(data);
        }
        if (tab === 'events') {
          const data = await request<{ items: Event[] }>('/api/home-hub/history');
          if (!cancelled) setEvents(data.items);
        }
        if (tab === 'agents') {
          const data = await request<{ items: typeof agents }>('/api/home-hub/agents');
          if (!cancelled) setAgents(data.items);
        }
      } catch (err) { if (!cancelled) setError(String(err)); }
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [tab, query, offset]);

  async function send(text = question) {
    if (!text.trim() || busy) return;
    setBusy(true); setError(''); setQuestion('');
    setMessages(previous => [...previous, { role: 'user', text }]);
    try {
      const result = await request<{ answer: string }>('/api/home-hub/chat', { method: 'POST', body: JSON.stringify({ message: text }) });
      setMessages(previous => [...previous, { role: 'assistant', text: result.answer }]);
    } catch (err) { setError(String(err)); setQuestion(text); }
    finally { setBusy(false); }
  }

  async function clear() {
    try { await request('/api/home-hub/conversation', { method: 'DELETE' }); setMessages([]); }
    catch (err) { setError(String(err)); }
  }

  return <div className="page-stack home-hub-page">
    <header className="page-header"><div><h1>Hauszentrale</h1><p role="status">{status?.quality === 'live' ? 'Live verbunden' : status?.quality === 'stale' ? 'Daten veraltet' : 'Verbindung nicht bestaetigt'} · {status?.counts.devices ?? 0} Geraete · {status?.counts.entities ?? 0} Entities</p></div>
      <button className="button secondary" title="Status aktualisieren" aria-label="Status aktualisieren" onClick={() => void loadStatus()}><RefreshCw size={18} /></button>
    </header>
    {error && <p role="alert">{error}</p>}
    {status?.monitor_only && <p role="status">Beobachtungsmodus · Schaltaktionen und Hintergrundagenten deaktiviert</p>}
    {Boolean(status?.deliveries?.pending) && <p role="status">{status?.deliveries?.pending} Benachrichtigungen warten auf Versand.</p>}
    {status && Object.keys(status.registry_errors).length > 0 && <p role="alert">Geraeteverzeichnis unvollstaendig: {Object.keys(status.registry_errors).join(', ')}</p>}
    <div className="hub-tabs" role="tablist" aria-label="Hauszentrale">
      {[['chat', 'Chat'], ['entities', 'Entities'], ['agents', 'Agenten'], ['events', 'Ereignisse']].map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>)}
    </div>
    {tab === 'chat' && <section className="hub-chat" aria-label="Haus-Chat">
      <div className="hub-chat-history" role="log" aria-live="polite">
        {messages.length === 0 && <p>Noch keine Nachrichten.</p>}
        {messages.map((message, index) => <article key={index} className={`hub-message ${message.role}`}><strong>{message.role === 'user' ? 'Du' : 'Steve'}</strong><p>{message.text}</p></article>)}
        {busy && <p role="status">Steve fragt die Hauszentrale ab ...</p>}<div ref={bottom} />
      </div>
      <form className="hub-compose" onSubmit={event => { event.preventDefault(); void send(); }}>
        <button type="button" className="button secondary" title="Chatverlauf loeschen" aria-label="Chatverlauf loeschen" disabled={busy || !messages.length} onClick={() => void clear()}><Trash2 size={18} /></button>
        <textarea aria-label="Nachricht" placeholder="Nachricht an Steve" value={question} maxLength={4000} onChange={event => setQuestion(event.target.value)} />
        <button className="button primary" title="Senden" aria-label="Senden" disabled={busy || !question.trim()}><Send size={18} /></button>
      </form>
    </section>}
    {tab === 'entities' && <section aria-label="Entity-Verzeichnis">
      <input className="hub-search" aria-label="Entities suchen" placeholder="Name, Raum oder Entity" value={query} onChange={event => { setQuery(event.target.value); setOffset(0); }} />
      <div className="hub-table-scroll"><table className="hub-table"><thead><tr><th>Name</th><th>Raum</th><th>Zustand</th><th>Aktualisiert</th></tr></thead><tbody>
        {inventory?.items.map(entity => <tr key={entity.entity_id}><td>{entity.name}<small>{entity.entity_id}</small></td><td>{entity.area || '-'}</td><td>{entity.state}</td><td>{entity.last_updated ? new Date(entity.last_updated).toLocaleString('de-DE') : '-'}</td></tr>)}
      </tbody></table></div>
      {inventory?.total === 0 && <p>Keine passenden Entities.</p>}
      <div className="hub-pagination"><button className="button secondary" aria-label="Vorherige Seite" title="Vorherige Seite" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}><ChevronLeft size={18} /></button><span>{inventory?.total ?? 0} Ergebnisse</span><button className="button secondary" aria-label="Naechste Seite" title="Naechste Seite" disabled={inventory?.next_offset == null} onClick={() => setOffset(inventory?.next_offset ?? offset)}><ChevronRight size={18} /></button></div>
    </section>}
    {tab === 'agents' && <section aria-label="Agentenstatus">{agents.map(agent => <details className="hub-detail" key={agent.id}><summary>{agent.name}</summary><pre>{JSON.stringify(agent.runtime, null, 2)}</pre></details>)}</section>}
    {tab === 'events' && <section aria-label="Ereignisverlauf">{events.length === 0 && <p>Noch keine Ereignisse.</p>}{events.map(event => <details className="hub-detail" key={event.id}><summary>{new Date(event.observed_at).toLocaleString('de-DE')} · {event.kind} · {event.subject}</summary><pre>{JSON.stringify(event.payload, null, 2)}</pre></details>)}</section>}
  </div>;
}
