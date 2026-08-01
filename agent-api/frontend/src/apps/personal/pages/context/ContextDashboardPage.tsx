import { AlertTriangle, BarChart3, BrainCircuit, Check, ChevronDown, Clock3, Home, Loader2, Moon, RefreshCw, ShieldCheck, Users, Warehouse } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api, type ContextDebug, type ContextHistoryItem, type ContextSignal, type ContextStatus } from '@shared/api/client';

type ContextBundle = {
  status: ContextStatus;
  debug: ContextDebug;
  history: ContextHistoryItem[];
};

const POLL_INTERVAL_MS = 10000;

export function ContextDashboardPage() {
  const [bundle, setBundle] = useState<ContextBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [debugOpen, setDebugOpen] = useState(false);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    setError('');
    try {
      const [status, history, debug] = await Promise.all([
        api.contextStatus(),
        api.contextHistory(100),
        api.contextDebug(),
      ]);
      setBundle({ status, debug, history: history.items });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ContextService konnte nicht geladen werden.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(true), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  if (loading && !bundle) {
    return (
      <main className="context-page" data-testid="context-loading">
        <section className="context-empty-state">
          <Loader2 size={24} />
          <strong>ContextService wird geladen</strong>
          <span>Steve liest den aktuellen Kontext.</span>
        </section>
      </main>
    );
  }

  if (error && !bundle) {
    return (
      <main className="context-page" data-testid="context-error">
        <section className="context-empty-state error">
          <AlertTriangle size={24} />
          <strong>ContextService nicht erreichbar</strong>
          <span>{error}</span>
          <button className="button secondary" type="button" onClick={() => load()}>
            <RefreshCw size={16} /> Erneut laden
          </button>
        </section>
      </main>
    );
  }

  if (!bundle) return null;

  const { status, debug, history } = bundle;
  const summary = contextSummary(status, debug);
  const cards = currentContextCards(status);
  const liveSignals = liveSignalCards(debug);
  const explanations = explanationGroups(status, debug);
  const timeline = timelineItems(history);
  const confidence = confidenceItems(status, debug);
  const groupedHistory = historyGroups(history);

  return (
    <main className="context-page" data-testid="context-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Steve Context</span>
          <h1>Kontext & Entscheidungen</h1>
          <p>Live aus dem ContextService. Keine Home-Assistant-Aktionen, keine Automationen.</p>
        </div>
        <button className="button secondary" type="button" onClick={() => load(true)} disabled={refreshing}>
          <RefreshCw size={16} /> {refreshing ? 'Aktualisiert...' : 'Aktualisieren'}
        </button>
      </header>

      {error && <section className="context-inline-error">{error}</section>}

      <section className={`context-steve-card tone-${toneFor(status.house || status.presence)}`} data-testid="steve-thinking">
        <div className="context-steve-icon"><BrainCircuit size={34} /></div>
        <div>
          <span>Steve denkt ...</span>
          <strong>{summary}</strong>
          <small>Aktualisiert {formatDateTime(status.updated_at)}</small>
        </div>
      </section>

      <section className="context-section" data-testid="context-status-cards">
        <SectionTitle icon={<Home size={18} />} title="Aktueller Kontext" detail="Berechnete Zustände" />
        <div className="context-card-grid">
          {cards.map((card) => (
            <article className={`context-status-card tone-${card.tone}`} key={card.label}>
              <div className="context-card-icon">{card.icon}</div>
              <span>{card.label}</span>
              <strong>{card.value}</strong>
              <small>{card.detail}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="context-section" data-testid="context-live-state">
        <SectionTitle icon={<ShieldCheck size={18} />} title="Live-Zustände" detail="Vom ContextService gelieferte Signale" />
        <div className="context-live-grid">
          {liveSignals.map((item) => (
            <article className="context-live-card" key={item.label}>
              <span>{item.label}</span>
              <strong>{item.state}</strong>
              <small>{item.source}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="context-two-column">
        <article className="context-panel" data-testid="context-explanations">
          <SectionTitle icon={<Check size={18} />} title="Begründungen" detail="Aktive Regeln und vorbereitete Entscheidungen" />
          <div className="context-reason-list">
            {explanations.map((group) => (
              <section className="context-reason-group" key={group.title}>
                <div>
                  <strong>{group.title}</strong>
                  <span>{group.outcome}</span>
                </div>
                <ul>
                  {group.items.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </section>
            ))}
          </div>
        </article>

        <article className="context-panel" data-testid="context-confidence">
          <SectionTitle icon={<BarChart3 size={18} />} title="Confidence" detail="Schlichte Balken aus Service-Werten" />
          <div className="context-confidence-list">
            {confidence.map((item) => (
              <div className="context-confidence-row" key={item.label}>
                <div>
                  <span>{item.label}</span>
                  <strong>{formatPercent(item.value)}</strong>
                </div>
                <div className="context-progress" aria-label={`${item.label} ${formatPercent(item.value)}`}>
                  <span className={`context-progress-fill pct-${percentClass(item.value)}`} />
                </div>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="context-two-column">
        <article className="context-panel" data-testid="context-timeline">
          <SectionTitle icon={<Clock3 size={18} />} title="Timeline" detail="Letzte Context-Wechsel" />
          <div className="context-timeline">
            {timeline.length === 0 && <p className="context-muted-note">Noch keine Context-Wechsel vorhanden.</p>}
            {timeline.map((item) => (
              <div className="context-timeline-item" key={item.key}>
                <time>{item.time}</time>
                <div>
                  <strong>{item.title}</strong>
                  <span>{item.detail}</span>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="context-panel" data-testid="context-history">
          <SectionTitle icon={<Clock3 size={18} />} title="Historie" detail="Heute, gestern und letzte Woche" />
          <div className="context-history-list">
            {groupedHistory.map((group) => (
              <section className="context-history-group" key={group.label}>
                <h2>{group.label}</h2>
                <div>
                  {group.items.map((item) => (
                    <span key={item.label}>{item.label}: <strong>{item.value}</strong></span>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </article>
      </section>

      <section className="context-debug" data-testid="context-debug">
        <button type="button" onClick={() => setDebugOpen((current) => !current)} aria-expanded={debugOpen}>
          <span>Debug</span>
          <ChevronDown size={18} />
        </button>
        {debugOpen && (
          <div className="context-debug-body">
            <section>
              <h2>Aktive Regeln</h2>
              {(!debug.active_rules || debug.active_rules.length === 0) && <p className="context-muted-note">Keine aktiven Regeln vom ContextService geliefert.</p>}
              <ul>
                {(debug.active_rules || []).map((rule) => <li key={rule}>{displayRule(rule)}</li>)}
              </ul>
            </section>
            <section>
              <h2>Context JSON</h2>
              <pre>{JSON.stringify(debug, null, 2)}</pre>
            </section>
          </div>
        )}
      </section>
    </main>
  );
}

function SectionTitle({ icon, title, detail }: { icon: ReactNode; title: string; detail: string }) {
  return (
    <div className="context-section-title">
      <div>{icon}<strong>{title}</strong></div>
      <span>{detail}</span>
    </div>
  );
}

function contextSummary(status: ContextStatus, debug: ContextDebug) {
  return status.summary || status.reason || status.message || debug.summary || debug.reason || debug.message || 'ContextService liefert noch keinen Steve-denkt-Text.';
}

function currentContextCards(status: ContextStatus) {
  return [
    { label: 'Haus', value: status.house || '-', detail: 'HouseState', tone: toneFor(status.house), icon: <Home size={22} /> },
    { label: 'Anwesenheit', value: status.presence || '-', detail: 'PresenceState', tone: toneFor(status.presence), icon: <Users size={22} /> },
    { label: 'Garage', value: status.garage || '-', detail: 'GarageState', tone: toneFor(status.garage), icon: <Warehouse size={22} /> },
    { label: 'Schlaf', value: status.sleep || '-', detail: 'Sleep Context', tone: toneFor(status.sleep), icon: <Moon size={22} /> },
    { label: 'Gäste', value: status.guest ? 'JA' : 'NEIN', detail: 'Guest Heuristic', tone: status.guest ? 'guests' : 'neutral', icon: <Users size={22} /> },
    { label: 'Confidence', value: formatPercent(status.confidence), detail: 'Gesamtwert', tone: 'confidence', icon: <BarChart3 size={22} /> },
  ];
}

function liveSignalCards(debug: ContextDebug) {
  const signals = debug.signals || {};
  const terraceCards = signals.terrace_presence
    ? [liveSignal('Terrassenpräsenz', signals.terrace_presence)]
    : [];
  return [
    ...terraceCards,
    liveSignal('Terrassentür', signals.terrace_door, 'door'),
    liveSignal('Wohnzimmer', signals.living_presence || signals.living_light || signals.tv),
    liveSignal('Schlafzimmer', signals.bedroom_presence || signals.bedroom_light),
    liveSignal('Auto', signals.vehicle),
    liveSignal('Home Zone', signals.person),
    liveSignal('Garagentor', signals.garage_door, 'cover'),
  ];
}

function liveSignal(label: string, signal: ContextSignal | ContextSignal[] | null | undefined, kind = '') {
  if (Array.isArray(signal)) {
    const active = signal.filter((item) => activeSignalState(item.state)).length;
    return { label, state: active ? 'Aktiv' : 'Leer', source: `${active}/${signal.length} Signale` };
  }
  if (!signal) return { label, state: 'Unbekannt', source: 'Kein Signal im ContextService' };
  return {
    label,
    state: readableSignalState(signal.state, kind),
    source: signal.name || signal.entity_id || 'ContextService',
  };
}

function explanationGroups(status: ContextStatus, debug: ContextDebug) {
  const reasons = debug.reasons || {};
  const activeRules = debug.active_rules || [];
  const decisions = Array.isArray(status.decisions) ? status.decisions : [];
  const groups = [
    {
      title: 'Garage',
      outcome: status.garage ? `Steve bereitet ${status.garage} vor.` : 'Keine Garagenentscheidung.',
      items: reasons.garage || reasons.departure || decisions.find((item) => item.target === 'garage')?.rules || activeRules.filter((rule) => rule.includes('garage') || rule.includes('vehicle') || rule.includes('departure')),
    },
    {
      title: 'Haus',
      outcome: status.house ? `Hausstatus ist ${status.house}.` : 'Kein Hausstatus.',
      items: reasons.house || activeRules.filter((rule) => rule.includes('house') || rule.includes('living') || rule.includes('terrace') || rule.includes('guest')),
    },
    {
      title: 'Schlaf',
      outcome: status.sleep ? `Schlafkontext ist ${status.sleep}.` : 'Kein Schlafkontext.',
      items: reasons.sleep || activeRules.filter((rule) => rule.includes('sleep') || rule.includes('bedroom') || rule.includes('quiet')),
    },
  ];
  return groups.map((group) => ({
    ...group,
    items: (group.items || []).length ? (group.items || []).map(displayRule) : ['ContextService liefert für diesen Bereich noch keine Detailregeln.'],
  }));
}

function confidenceItems(status: ContextStatus, debug: ContextDebug) {
  const details = debug.confidence_details || {};
  return [
    { label: 'Hausstatus', value: numberValue(details.house, status.confidence) },
    { label: 'Garage', value: numberValue(details.garage, status.confidence) },
    { label: 'Schlaf', value: numberValue(details.sleep, status.confidence) },
    { label: 'Anwesenheit', value: numberValue(details.presence, status.confidence) },
  ];
}

function timelineItems(history: ContextHistoryItem[]) {
  const ordered = [...history].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  const events: Array<{ key: string; time: string; title: string; detail: string }> = [];
  ordered.forEach((item, index) => {
    const previous = ordered[index - 1];
    const fields: Array<keyof ContextHistoryItem> = ['presence', 'garage', 'house', 'transition'];
    fields.forEach((field) => {
      const value = String(item[field] || '');
      if (!value || previous?.[field] === value) return;
      events.push({
        key: `${item.id}-${field}-${value}`,
        time: formatTime(item.created_at),
        title: labelForField(field),
        detail: value,
      });
    });
  });
  return events.slice(-12).reverse();
}

function historyGroups(history: ContextHistoryItem[]) {
  const now = new Date();
  const today = history.filter((item) => sameDay(item.created_at, now));
  const yesterday = history.filter((item) => sameDay(item.created_at, addDays(now, -1)));
  const week = history.filter((item) => new Date(item.created_at).getTime() >= addDays(now, -7).getTime());
  return [
    { label: 'Heute', items: historySummary(today) },
    { label: 'Gestern', items: historySummary(yesterday) },
    { label: 'Letzte Woche', items: historySummary(week) },
  ];
}

function historySummary(items: ContextHistoryItem[]) {
  return [
    { label: 'Hausstatus', value: mostRecent(items, 'house') },
    { label: 'Garage', value: mostRecent(items, 'garage') },
    { label: 'Schlaf', value: mostRecentPayload(items, 'sleep') },
    { label: 'Kurzabwesenheiten', value: countValue(items, 'presence', 'SHORT_AWAY') },
    { label: 'Gäste', value: countGuest(items) },
  ];
}

function mostRecent(items: ContextHistoryItem[], key: keyof ContextHistoryItem) {
  return String(items[0]?.[key] || '-');
}

function mostRecentPayload(items: ContextHistoryItem[], key: keyof ContextDebug) {
  return String(items[0]?.payload?.[key] || '-');
}

function countValue(items: ContextHistoryItem[], key: keyof ContextHistoryItem, value: string) {
  return String(items.filter((item) => item[key] === value).length);
}

function countGuest(items: ContextHistoryItem[]) {
  return String(items.filter((item) => item.payload?.guest === true).length);
}

function toneFor(value?: string) {
  const state = String(value || '').toLowerCase();
  if (state.includes('home')) return 'home';
  if (state.includes('away')) return state.includes('short') ? 'short-away' : 'away';
  if (state.includes('sleep')) return 'sleeping';
  if (state.includes('relax')) return 'relaxing';
  if (state.includes('guest')) return 'guests';
  if (state.includes('open')) return 'short-away';
  if (state.includes('close')) return 'away';
  return 'neutral';
}

function activeSignalState(value?: string) {
  return ['on', 'home', 'open', 'playing', 'detected', 'occupied'].includes(String(value || '').toLowerCase());
}

function readableSignalState(value?: string, kind = '') {
  const state = String(value || '').toLowerCase();
  if (kind === 'cover') {
    if (state === 'open') return 'Offen';
    if (state === 'closed') return 'Geschlossen';
    if (state === 'opening') return 'Öffnet';
    if (state === 'closing') return 'Schließt';
  }
  if (kind === 'door') {
    if (['open', 'on'].includes(state)) return 'Offen';
    if (['closed', 'off'].includes(state)) return 'Geschlossen';
  }
  if (activeSignalState(state)) return 'Aktiv';
  if (['off', 'not_home', 'closed', 'idle', 'standby'].includes(state)) return 'Leer';
  return value || 'Unbekannt';
}

function displayRule(value: string) {
  return value.replace(/_/g, ' ');
}

function formatPercent(value?: number) {
  const number = numberValue(value, 0);
  return `${Math.round(number * 100)} %`;
}

function numberValue(value: unknown, fallback: number) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(number, 1)) : fallback;
}

function percentClass(value: number) {
  return Math.max(0, Math.min(100, Math.round(numberValue(value, 0) * 100 / 5) * 5));
}

function formatDateTime(value?: string) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function formatTime(value?: string) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' }).format(date);
}

function sameDay(value: string, day: Date) {
  const date = new Date(value);
  return date.getFullYear() === day.getFullYear() && date.getMonth() === day.getMonth() && date.getDate() === day.getDate();
}

function addDays(date: Date, days: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function labelForField(field: keyof ContextHistoryItem) {
  if (field === 'presence') return 'Anwesenheit';
  if (field === 'garage') return 'Garage';
  if (field === 'house') return 'Haus';
  if (field === 'transition') return 'Transition';
  return String(field);
}
