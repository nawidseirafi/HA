import { useEffect, useMemo, useState } from 'react';
import { Clock3, Coffee, Footprints, Home, ShieldCheck, Sunrise } from 'lucide-react';
import { api, type SeniorBehaviorAssessment, type SeniorSensorRole, type SeniorSetupStatus } from '@shared/api/client';

export function DashboardPage() {
  const [status, setStatus] = useState<SeniorSetupStatus | null>(null);
  const [behavior, setBehavior] = useState<SeniorBehaviorAssessment | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [next, latestBehavior] = await Promise.all([
          api.seniorSetupStatus(),
          api.seniorBehaviorLatest().catch(() => ({ assessment: null })),
        ]);
        if (active) {
          setStatus(next);
          setBehavior(latestBehavior.assessment);
          setError('');
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : 'Sentero konnte nicht geladen werden.');
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const roles = status?.sensor_roles ?? [];
  const latest = useMemo(() => latestPresenceRole(roles), [roles]);
  const personName = status?.profile?.name?.trim() || 'Mama';
  const activitySlots = useMemo(() => activitySlotsFromRoles(roles), [roles]);
  const hasActivity = activitySlots.some((slot) => slot.active);
  const lastUpdate = latest ? formatTime(new Date(timestamp(latest.last_changed || latest.last_updated || latest.updated_at))) : formatTime(new Date());
  const lastSeen = latest ? relativeTime(latest.last_changed || latest.last_updated || latest.updated_at) : 'Noch keine Daten';
  const morning = firstActivityTime(roles);
  const kitchen = lastRoomActivity(roles, 'kitchen');

  return (
    <section className="sc-page sc-simple-dashboard" aria-label="Sentero Tagesstatus">
      <header className="sc-simple-hero">
        <p className="sc-simple-date">{formatHeaderDate(new Date())}</p>
        <p className="sc-simple-person"><span aria-hidden="true" /> {personName} · Zuhause</p>
        <h2>{error ? 'Bitte prüfen.' : 'Alles in Ordnung.'}</h2>
        <p className="sc-simple-copy">
          {error ? 'Aktuelle Daten konnten gerade nicht geladen werden.' : latest ? 'Der aktuelle Verlauf basiert auf den verbundenen Sensoren.' : 'Noch keine Sensoraktivität vorhanden.'}
        </p>
      </header>

      <article className="sc-dashboard-status-card" aria-label="Aktueller Status">
        <div>
          <Home size={22} aria-hidden="true" />
          <div>
            <strong>{personName} ist zuhause</strong>
            <span>Zuletzt aktualisiert: {lastUpdate}</span>
          </div>
        </div>
        <em><ShieldCheck size={17} aria-hidden="true" /> Alles in Ordnung</em>
      </article>

      <article className={`sc-behavior-card ${behavior?.status || 'green'}`} aria-label="Status heute">
        <div>
          <span aria-hidden="true">{behaviorIcon(behavior?.status)}</span>
          <div>
            <small>Status heute</small>
            <strong>{behaviorTitle(behavior?.status)}</strong>
          </div>
        </div>
        <p>{behavior?.summary || 'Noch keine KI-Bewertung vorhanden. Sentero lernt den Tagesablauf mit den verbundenen Sensoren.'}</p>
        {behavior?.recommendation && <em>{behavior.recommendation}</em>}
      </article>

      <article className="sc-simple-day-card" aria-label="Tagesverlauf">
        <div className="sc-simple-day-head">
          <strong>Tagesverlauf</strong>
          <span>{error ? 'Prüfen' : 'Ruhig'}</span>
        </div>
        <div className={`sc-simple-dayline ${hasActivity ? 'has-activity' : ''}`}>
          <div className="sc-simple-dots" aria-hidden="true">
            {activitySlots.map((slot) => <i key={slot.label} className={slot.active ? 'active' : ''} />)}
          </div>
          <div className="sc-simple-times" aria-hidden="true">
            {activitySlots.map((slot) => <span key={slot.label}>{slot.label}</span>)}
          </div>
          {!hasActivity && <p>Noch keine Aktivität erkannt</p>}
        </div>
      </article>

      <h3 className="sc-simple-section-title">Heute</h3>
      <section className="sc-simple-facts" aria-label="Wichtige Tagespunkte">
        <Fact icon={Sunrise} label="Aufgestanden" value={morning || 'Noch offen'} />
        <Fact icon={Coffee} label="Küche" value={kitchen || 'Keine Aktivität'} />
        <Fact icon={Footprints} label="Letzte Bewegung" value={lastSeen} highlight={Boolean(latest)} />
      </section>
    </section>
  );
}

function Fact({ icon: Icon, label, value, highlight }: { icon: typeof Clock3; label: string; value: string; highlight?: boolean }) {
  return (
    <div className="sc-simple-fact">
      <span><Icon size={20} aria-hidden="true" /></span>
      <div>
        <small>{label}</small>
        <strong className={highlight ? 'highlight' : ''}>{value}</strong>
      </div>
    </div>
  );
}

function behaviorTitle(status?: string | null) {
  if (status === 'yellow') return 'Auffälligkeit erkannt';
  if (status === 'orange') return 'Bitte prüfen';
  if (status === 'red') return 'Handlungsbedarf';
  return 'Alles normal';
}

function behaviorIcon(status?: string | null) {
  if (status === 'yellow') return '🟡';
  if (status === 'orange') return '🟠';
  if (status === 'red') return '🔴';
  return '🟢';
}

function latestPresenceRole(roles: SeniorSensorRole[]) {
  return roles
    .filter((role) => role.configured && role.reachable !== false && isPresenceRole(role))
    .sort((a, b) => timestamp(b.last_changed || b.last_updated || b.updated_at) - timestamp(a.last_changed || a.last_updated || a.updated_at))[0];
}

function isPresenceRole(role: SeniorSensorRole) {
  return role.role.endsWith('presence') || ['motion', 'occupancy', 'presence'].includes(String(role.device_class || ''));
}

function firstActivityTime(roles: SeniorSensorRole[]) {
  const value = roles
    .map((role) => timestamp(role.last_changed || role.last_updated || role.updated_at))
    .filter(Boolean)
    .sort((a, b) => a - b)[0];
  return value ? formatTime(new Date(value)) : '';
}

function lastRoomActivity(roles: SeniorSensorRole[], room: string) {
  const value = roles
    .filter((role) => role.room === room)
    .map((role) => timestamp(role.last_changed || role.last_updated || role.updated_at))
    .filter(Boolean)
    .sort((a, b) => b - a)[0];
  return value ? formatTime(new Date(value)) : '';
}

function activitySlotsFromRoles(roles: SeniorSensorRole[]) {
  const slots = [6, 9, 12, 15, 18, 21].map((hour) => ({ hour, label: String(hour).padStart(2, '0'), active: false }));
  const today = new Date();
  for (const role of roles) {
    const value = timestamp(role.last_changed || role.last_updated || role.updated_at);
    if (!value) continue;
    const date = new Date(value);
    if (date.toDateString() !== today.toDateString()) continue;
    const index = slots.findIndex((slot, slotIndex) => {
      const next = slots[slotIndex + 1]?.hour ?? 24;
      return date.getHours() >= slot.hour && date.getHours() < next;
    });
    if (index >= 0) slots[index].active = true;
  }
  return slots;
}

function timestamp(value?: string | null) {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function relativeTime(value?: string | null) {
  const time = timestamp(value);
  if (!time) return 'noch keine Daten';
  const minutes = Math.max(0, Math.round((Date.now() - time) / 60000));
  if (minutes < 1) return 'gerade eben';
  if (minutes < 60) return `vor ${minutes} Min.`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `vor ${hours} Std.`;
  return formatDateTime(new Date(time));
}

function formatTime(date: Date) {
  return new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' }).format(date);
}

function formatDateTime(date: Date) {
  return new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date);
}

function formatHeaderDate(date: Date) {
  return new Intl.DateTimeFormat('de-DE', { weekday: 'long', hour: '2-digit', minute: '2-digit' }).format(date);
}
