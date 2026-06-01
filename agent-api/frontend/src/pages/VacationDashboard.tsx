import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import {
  BellRing,
  CalendarCheck,
  CalendarDays,
  History,
  Plane,
  Power,
  RefreshCw,
  ShieldCheck,
  UserRoundCheck,
} from 'lucide-react';
import {
  api,
  type PresenceProfile,
  type VacationHistory,
  type VacationPeriod,
  type VacationProfilesResponse,
  type VacationReminder,
  type VacationStatus,
} from '../api/client';

type VacationTab = 'overview' | 'vacation' | 'reminders' | 'presence' | 'history';

const tabs: Array<{ id: VacationTab; label: string; icon: typeof Plane }> = [
  { id: 'overview', label: 'Übersicht', icon: ShieldCheck },
  { id: 'vacation', label: 'Urlaub', icon: Plane },
  { id: 'reminders', label: 'Reminder', icon: BellRing },
  { id: 'presence', label: 'Anwesenheit', icon: UserRoundCheck },
  { id: 'history', label: 'Historie', icon: History },
];

export function VacationDashboard() {
  const [activeTab, setActiveTab] = useState<VacationTab>('overview');
  const [status, setStatus] = useState<VacationStatus | null>(null);
  const [reminders, setReminders] = useState<VacationReminder[]>([]);
  const [history, setHistory] = useState<VacationHistory | null>(null);
  const [profileStats, setProfileStats] = useState<VacationProfilesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const [nextStatus, nextReminders, nextHistory, nextProfiles] = await Promise.all([
        api.vacationStatus(),
        api.vacationReminders(),
        api.vacationHistory(100),
        api.vacationProfiles(100),
      ]);
      setStatus(nextStatus);
      setReminders(nextReminders.reminders);
      setHistory(nextHistory);
      setProfileStats(nextProfiles);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Vacation Dashboard konnte nicht geladen werden.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load(true), 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  const setMode = async (active: boolean) => {
    setLoading(true);
    setNotice('');
    setError('');
    try {
      await (active ? api.enableVacationMode() : api.disableVacationMode());
      setNotice(active ? 'Haus-Urlaubsmodus wurde aktiviert.' : 'Haus-Urlaubsmodus wurde deaktiviert.');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Haus-Urlaubsmodus konnte nicht geschaltet werden.');
    } finally {
      setLoading(false);
    }
  };

  const setAgent = async (active: boolean) => {
    setLoading(true);
    setNotice('');
    setError('');
    try {
      const nextStatus = await (active ? api.enableVacationAgent() : api.disableVacationAgent());
      setStatus(nextStatus);
      setNotice(active ? 'Vacation Agent wurde aktiviert.' : 'Vacation Agent wurde deaktiviert.');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Vacation Agent konnte nicht geschaltet werden.');
    } finally {
      setLoading(false);
    }
  };

  const runAgent = async () => {
    setLoading(true);
    setNotice('');
    setError('');
    try {
      await api.runVacationAgent({ dry_run: false });
      setNotice('Vacation Agent wurde ausgeführt.');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Vacation Agent konnte nicht ausgeführt werden.');
    } finally {
      setLoading(false);
    }
  };

  const agent = status?.agent;
  const period = status?.period;
  const mode = status?.vacation_mode;
  const modeActive = Boolean(mode?.active ?? status?.vacation_mode_active);
  const events = history?.events ?? [];
  const periods = history?.periods ?? [];
  const profiles = profileStats?.profiles ?? history?.presence_profiles ?? [];
  const lastActivity = events[0]?.created_at || agent?.last_run || periods[0]?.created_at;
  const schedulerActive = Boolean(agent?.scheduler_running && (agent?.enabled ?? status?.enabled));
  const scheduleText = agent?.schedule_times?.length ? agent.schedule_times.join(', ') : '-';

  return (
    <div className="page-stack wellness-app vacation-app">
      <header className="wellness-hero-header compact">
        <div>
          <span className="eyebrow">Vacation Agent</span>
          <h1>Vacation Agent</h1>
          <p>Überwacht Urlaubsmodus, Reminder, Historie und spätere Anwesenheitssimulation.</p>
        </div>
        <button className="icon-button" type="button" onClick={() => load()} disabled={loading} aria-label="Aktualisieren">
          <RefreshCw size={19} />
        </button>
      </header>

      {error && <section className="panel error-panel">{error}</section>}
      {notice && <section className="panel success-panel">{notice}</section>}

      <nav className="vacation-tabs" aria-label="Vacation Dashboard Tabs">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button key={tab.id} className={activeTab === tab.id ? 'active' : ''} type="button" onClick={() => setActiveTab(tab.id)}>
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </nav>

      {activeTab === 'overview' && (
        <>
          <section className={`vacation-status-card ${(agent?.enabled ?? status?.enabled) ? 'active' : 'inactive'}`}>
            <div className="vacation-status-icon"><ShieldCheck size={28} /></div>
            <div>
              <span className="eyebrow">Agent Status</span>
              <h2>{agent?.enabled ?? status?.enabled ? 'Agent aktiv' : 'Agent inaktiv'}</h2>
              <p>{agent?.status || status?.current_status || 'unknown'} · letzter Lauf {formatDateTime(agent?.last_run)}</p>
            </div>
            <div className="vacation-status-side">
              <span className={`agent-state-pill ${agent?.last_error || status?.last_error ? 'error' : (agent?.enabled ?? status?.enabled) ? 'ok' : 'idle'}`}>
                {agent?.last_error || status?.last_error ? 'Fehler' : (agent?.enabled ?? status?.enabled) ? 'Aktiv' : 'Inaktiv'}
              </span>
              <div className="vacation-status-actions">
                <button className="button primary" type="button" onClick={() => setAgent(true)} disabled={loading || Boolean(agent?.enabled ?? status?.enabled)}>
                  Agent aktivieren
                </button>
                <button className="button secondary" type="button" onClick={() => setAgent(false)} disabled={loading || !Boolean(agent?.enabled ?? status?.enabled)}>
                  Agent deaktivieren
                </button>
                <button className="button ghost" type="button" onClick={runAgent} disabled={loading || !Boolean(agent?.enabled ?? status?.enabled)}>
                  Prüfen
                </button>
              </div>
            </div>
          </section>

          <section className="wellness-card-grid">
            <StatCard icon={<Plane size={20} />} label="Vacation Mode" value={modeActive ? 'Aktiv' : 'Aus'} tone={modeActive ? 'warning' : 'success'} />
            <StatCard icon={<CalendarDays size={20} />} label="Urlaubszeitraum" value={formatPeriodValue(period)} tone={period?.start_date ? 'info' : 'muted'} />
            <StatCard icon={<BellRing size={20} />} label="Reminder" value={`${status?.summary?.reminders ?? reminders.length}`} tone={reminders.length ? 'warning' : 'success'} />
            <StatCard icon={<UserRoundCheck size={20} />} label="Presence Profiles" value={`${status?.summary?.profiles ?? profileStats?.profile_count ?? profiles.length}`} tone={profiles.length ? 'success' : 'muted'} />
            <StatCard icon={<History size={20} />} label="Letzte Aktivität" value={formatDateTime(lastActivity)} tone="muted" />
            <StatCard icon={<CalendarDays size={20} />} label="Kalenderquelle" value={periodSourceLabel(period?.source)} tone={period?.source === 'homeassistant_calendar' ? 'success' : 'muted'} />
            <StatCard icon={<RefreshCw size={20} />} label="Automatik" value={schedulerActive ? 'Läuft' : 'Aus'} tone={schedulerActive ? 'success' : 'muted'} />
            <StatCard icon={<CalendarCheck size={20} />} label="Zeitplan" value={scheduleText} tone="info" />
            <StatCard icon={<History size={20} />} label="Letzter Auto-Lauf" value={formatDateTime(agent?.last_scheduled_run)} tone="muted" />
          </section>
        </>
      )}

      {activeTab === 'vacation' && (
        <>
          <section className={`vacation-status-card ${modeActive ? 'active' : 'inactive'}`}>
            <div className="vacation-status-icon"><Plane size={28} /></div>
            <div>
              <span className="eyebrow">Vacation Mode</span>
              <h2>{modeActive ? 'An' : 'Aus'}</h2>
              <p>Quelle: {mode?.source || status?.mode_entity || 'input_boolean.vacation_mode'}</p>
            </div>
            <div className="vacation-status-side">
              <span className={`agent-state-pill ${modeActive ? 'waiting' : 'ok'}`}>{modeActive ? 'Aktiv' : 'Aus'}</span>
              <div className="vacation-status-actions">
                <button className="button primary" type="button" onClick={() => setMode(true)} disabled={loading || modeActive}>
                  Urlaubsmodus aktivieren
                </button>
                <button className="button secondary" type="button" onClick={() => setMode(false)} disabled={loading || !modeActive}>
                  Urlaubsmodus deaktivieren
                </button>
              </div>
            </div>
          </section>

          <section className="wellness-card-grid">
            <StatCard icon={<CalendarDays size={20} />} label="Kalenderquelle" value={status?.calendar_entity || 'Nicht erkannt'} tone={status?.calendar_entity ? 'success' : 'warning'} />
            <StatCard icon={<CalendarCheck size={20} />} label="Nächster Urlaub" value={period?.title || formatPeriodValue(period)} tone={period?.start_date ? 'info' : 'muted'} />
            <StatCard icon={<CalendarDays size={20} />} label="Startdatum" value={formatDateOnly(period?.start_date)} tone="info" />
            <StatCard icon={<CalendarCheck size={20} />} label="Enddatum" value={formatDateOnly(period?.end_date)} tone="info" />
            <StatCard icon={<Plane size={20} />} label="Urlaubsdauer" value={period?.duration_days ? `${period.duration_days} Tage` : periodDurationValue(period)} tone="success" />
          </section>
          {status?.calendar_error && <section className="panel error-panel">{status.calendar_error}</section>}
        </>
      )}

      {activeTab === 'reminders' && (
        <section className="wellness-booking-summary dense">
          <TableHeader eyebrow="Reminder" title="Offene Reminder" count={reminders.length} />
          <div className="vacation-list">
            {reminders.map((reminder) => (
              <article key={reminder.id} className="vacation-row">
                <span className={`vacation-severity ${severityTone(reminder)}`}>{severityLabel(reminder)}</span>
                <div>
                  <strong>{reminder.title || reminder.reminder_type || 'Reminder'}</strong>
                  <small>{reminder.message || '-'}</small>
                </div>
                <em>{formatDateTime(reminder.due_at || reminder.created_at)}</em>
              </article>
            ))}
            {reminders.length === 0 && <EmptyState icon={<BellRing size={18} />} text="Keine offenen Reminder vorhanden." />}
          </div>
        </section>
      )}

      {activeTab === 'presence' && (
        <>
          <section className="wellness-card-grid">
            <StatCard icon={<UserRoundCheck size={20} />} label="Status" value={profileStats?.status === 'profile_available' ? 'Profile vorhanden' : 'Lernphase'} tone={profiles.length ? 'success' : 'info'} />
            <StatCard icon={<CalendarDays size={20} />} label="Analysierte Tage" value={`${profileStats?.analyzed_days ?? 0}`} tone="info" />
            <StatCard icon={<UserRoundCheck size={20} />} label="Profile" value={`${profileStats?.profile_count ?? profiles.length}`} tone={profiles.length ? 'success' : 'muted'} />
            <StatCard icon={<ShieldCheck size={20} />} label="Confidence" value={`${Math.round((profileStats?.confidence ?? 0) * 100)}%`} tone={profiles.length ? 'success' : 'muted'} />
          </section>
          <section className="wellness-booking-summary dense">
            <TableHeader eyebrow="Anwesenheit" title="Presence Profiles" count={profiles.length} />
            <p>Der Vacation Agent sammelt aktuell Nutzungsdaten für eine spätere Anwesenheitssimulation.</p>
            {profiles.length > 0 && (
              <div className="vacation-list">
                {profiles.map((profile) => (
                  <article key={profile.id} className="vacation-row">
                    <span className="vacation-severity info">{weekdayLabel(profile.weekday)}</span>
                    <div>
                      <strong>{profile.room || 'Unbekannt'}</strong>
                      <small>An {profile.avg_on_time || '-'} · Aus {profile.avg_off_time || '-'}</small>
                    </div>
                    <em>{Math.round(Number(profile.confidence || 0) * 100)}%</em>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {activeTab === 'history' && (
        <>
          <section className="wellness-booking-summary dense">
            <TableHeader eyebrow="Historie" title="Urlaubszeiträume" count={periods.length} />
            <div className="vacation-list">
              {periods.map((item) => (
                <article key={item.id} className="vacation-row history">
                  <span className={`vacation-severity ${periodSeverity(item.source)}`}>{periodSourceLabel(item.source)}</span>
                  <div>
                    <strong>{formatPeriod(item)}</strong>
                    <small>Dauer: {periodDuration(item)} · Quelle: {periodSourceLabel(item.source)}</small>
                  </div>
                  <em>{formatDateTime(item.created_at)}</em>
                </article>
              ))}
              {periods.length === 0 && <EmptyState icon={<History size={18} />} text="Noch keine Urlaubszeiträume vorhanden." />}
            </div>
          </section>
          <section className="wellness-booking-summary dense">
            <TableHeader eyebrow="Events" title="Agent Events" count={events.length} />
            <div className="vacation-list">
              {events.slice(0, 20).map((event) => (
                <article key={event.id} className="vacation-row">
                  <span className={`vacation-severity ${event.severity === 'error' ? 'critical' : event.severity === 'warning' ? 'warning' : 'info'}`}>{event.severity}</span>
                  <div>
                    <strong>{event.event_type}</strong>
                    <small>{event.message || '-'}</small>
                  </div>
                  <em>{formatDateTime(event.created_at)}</em>
                </article>
              ))}
              {events.length === 0 && <EmptyState icon={<History size={18} />} text="Noch keine Events vorhanden." />}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function StatCard({ icon, label, value, tone }: { icon: ReactNode; label: string; value: string; tone: string }) {
  return (
    <section className={`wellness-stat-card ${tone}`}>
      <div className="wellness-stat-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </section>
  );
}

function TableHeader({ eyebrow, title, count }: { eyebrow: string; title: string; count: number }) {
  return (
    <div className="section-title">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      <span className="agent-state-pill ok">{count}</span>
    </div>
  );
}

function EmptyState({ icon, text }: { icon: ReactNode; text: string }) {
  return <div className="wellness-empty-state">{icon} {text}</div>;
}

function toDateInputValue(value?: string | null) {
  if (!value) return '';
  const match = String(value).match(/^\d{4}-\d{2}-\d{2}/);
  return match?.[0] ?? '';
}

function formatDateOnly(value?: string | null) {
  const inputValue = toDateInputValue(value);
  if (!inputValue) return '-';
  const date = new Date(`${inputValue}T00:00:00`);
  if (Number.isNaN(date.getTime())) return '-';
  return new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium' }).format(date);
}

function formatDateTime(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}

function formatPeriodValue(period?: VacationStatus['period'] | null) {
  if (!period?.start_date && !period?.end_date) return '-';
  return `${formatDateOnly(period.start_date)} bis ${formatDateOnly(period.end_date)}`;
}

function periodDurationValue(period?: VacationStatus['period'] | null) {
  const startValue = toDateInputValue(period?.start_date);
  const endValue = toDateInputValue(period?.end_date);
  if (!startValue || !endValue) return '-';
  const start = new Date(`${startValue}T00:00:00`);
  const end = new Date(`${endValue}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return '-';
  return `${Math.max(1, Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1)} Tage`;
}

function formatPeriod(period: VacationPeriod) {
  return `${formatDateOnly(period.start_date)} bis ${formatDateOnly(period.end_date)}`;
}

function periodDuration(period: VacationPeriod) {
  return periodDurationValue(period);
}

function severityTone(reminder: VacationReminder) {
  const value = `${reminder.severity || reminder.status || reminder.reminder_type || ''}`.toLowerCase();
  if (value.includes('critical') || value.includes('high')) return 'critical';
  if (value.includes('warn') || value.includes('medium')) return 'warning';
  return 'info';
}

function severityLabel(reminder: VacationReminder) {
  const tone = severityTone(reminder);
  if (tone === 'critical') return 'Critical';
  if (tone === 'warning') return 'Warning';
  return 'Info';
}

function periodSourceLabel(source?: string | null) {
  if (source === 'homeassistant_calendar' || source === 'calendar') return 'Kalender';
  if (source === 'manual') return 'Manuell';
  if (source === 'import') return 'Import';
  if (source === 'local') return 'Lokal';
  return '-';
}

function periodSeverity(source?: string | null) {
  if (source === 'homeassistant_calendar' || source === 'calendar') return 'info';
  if (source === 'manual') return 'warning';
  return 'info';
}

function weekdayLabel(value?: number | null) {
  const labels = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  return typeof value === 'number' ? labels[value] || '-' : '-';
}
