import { useEffect, useMemo, useState } from 'react';
import { api, type SeniorSensorRole, type SeniorSetupStatus } from '@shared/api/client';

export function DashboardPage() {
  const [status, setStatus] = useState<SeniorSetupStatus | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const next = await api.seniorSetupStatus();
        if (active) {
          setStatus(next);
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
  const profileName = status?.profile?.name?.trim() || 'Zuhause';
  const bars = useMemo(() => activityBarsFromRoles(roles), [roles]);
  const lastSeen = latest ? relativeTime(latest.last_changed || latest.last_updated || latest.updated_at) : 'noch keine Daten';
  const morning = firstActivityTime(roles);
  const kitchen = lastRoomActivity(roles, 'kitchen');

  return (
    <section className="sc-page sc-simple-dashboard" aria-label="Sentero Tagesstatus">
      <header className="sc-simple-hero">
        <p className="sc-simple-date">{formatHeaderDate(new Date())}</p>
        <p className="sc-simple-person"><span aria-hidden="true" /> {profileName} · Zuhause</p>
        <h2>{error ? 'Bitte prüfen.' : 'Alles in Ordnung.'}</h2>
        <p className="sc-simple-copy">
          {error ? 'Aktuelle Daten konnten gerade nicht geladen werden.' : latest ? 'Der aktuelle Verlauf basiert auf den verbundenen Sensoren.' : 'Noch keine Sensoraktivität vorhanden.'}
        </p>
      </header>

      <article className="sc-simple-day-card" aria-label="Tagesverlauf">
        <div className="sc-simple-day-head">
          <strong>Tagesverlauf</strong>
          <span>{error ? 'Prüfen' : 'Ruhig'}</span>
        </div>
        <div className="sc-simple-bars" aria-hidden="true">
          {bars.map((height, index) => (
            <i key={`${height}-${index}`} style={{ height: `${height}%` }} />
          ))}
        </div>
      </article>

      <section className="sc-simple-facts" aria-label="Wichtige Tagespunkte">
        <Fact label="Aufgestanden" value={morning || 'Noch offen'} />
        <Fact label="In der Küche" value={kitchen || 'Keine Aktivität'} />
        <Fact label="Letzte Bewegung" value={lastSeen} highlight={Boolean(latest)} />
      </section>
    </section>
  );
}

function Fact({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="sc-simple-fact">
      <span>{label}</span>
      <strong className={highlight ? 'highlight' : ''}>{value}</strong>
    </div>
  );
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

function activityBarsFromRoles(roles: SeniorSensorRole[]) {
  const hours = Array.from({ length: 10 }, () => 18);
  const today = new Date();
  for (const role of roles) {
    const value = timestamp(role.last_changed || role.last_updated || role.updated_at);
    if (!value) continue;
    const date = new Date(value);
    if (date.toDateString() !== today.toDateString()) continue;
    const index = Math.min(9, Math.max(0, Math.floor((date.getHours() - 6) / 2)));
    hours[index] = Math.min(88, hours[index] + 18);
  }
  return hours;
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
