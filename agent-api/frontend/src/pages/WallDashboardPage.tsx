import { Component, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import {
  Activity,
  BatteryWarning,
  Bot,
  CloudSun,
  DoorOpen,
  Home,
  Lightbulb,
  RefreshCw,
  ShieldAlert,
  Thermometer,
  Zap,
} from 'lucide-react';
import { api, type AgentStatus, type WallDashboardData, type WallLight, type WallLightGroup } from '../api/client';
import '../styles/wall.css';

type WallSection = 'home' | 'lights' | 'climate' | 'security' | 'agents';

export function WallDashboardPage() {
  return (
    <WallErrorBoundary>
      <WallDashboardContent />
    </WallErrorBoundary>
  );
}

function WallDashboardContent() {
  const [data, setData] = useState<WallDashboardData | null>(null);
  const [section, setSection] = useState<WallSection>('home');
  const [selectedFloor, setSelectedFloor] = useState('Alle Etagen');
  const [loading, setLoading] = useState(false);
  const [busyEntity, setBusyEntity] = useState('');
  const [error, setError] = useState('');
  const [runtimeError, setRuntimeError] = useState('');
  const [now, setNow] = useState(new Date());
  const brightnessTimers = useRef<Record<string, number>>({});
  const refreshTimer = useRef<number | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const next = await api.wallDashboard();
      setData(next);
      setSelectedFloor((currentFloor) => (
        currentFloor === 'Alle Etagen' || next.light_groups.some((group) => group.area === currentFloor)
          ? currentFloor
          : 'Alle Etagen'
      ));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Wall-Dashboard konnte nicht geladen werden.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const refresh = window.setInterval(() => load(true), 15000);
    const clock = window.setInterval(() => setNow(new Date()), 1000);
    const onError = (event: ErrorEvent) => {
      setRuntimeError(event.error instanceof Error ? `${event.error.name}: ${event.error.message}` : event.message);
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      setRuntimeError(reason instanceof Error ? `${reason.name}: ${reason.message}` : String(reason));
    };
    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);
    return () => {
      window.clearInterval(refresh);
      window.clearInterval(clock);
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
      if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
      Object.values(brightnessTimers.current).forEach((timer) => window.clearTimeout(timer));
    };
  }, [load]);

  const visibleGroups = useMemo(() => {
    if (!data) return [];
    if (selectedFloor === 'Alle Etagen') return data.light_groups;
    return data.light_groups.filter((group) => group.area === selectedFloor);
  }, [data, selectedFloor]);

  const allSelectedLights = useMemo(() => visibleGroups.flatMap((group) => group.items), [visibleGroups]);

  const scheduleRefresh = () => {
    if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
    refreshTimer.current = window.setTimeout(() => load(true), 900);
  };

  const callLight = async (service: 'turn_on' | 'turn_off', entity_id: string | string[], payload: Record<string, unknown> = {}) => {
    const ids = Array.isArray(entity_id) ? entity_id : [entity_id];
    setData((current) => patchWallLights(current, ids, {
      on: service === 'turn_on',
      brightness_pct: typeof payload.brightness_pct === 'number' ? payload.brightness_pct : service === 'turn_off' ? 0 : undefined,
    }));
    setBusyEntity(Array.isArray(entity_id) ? 'bulk' : entity_id);
    setError('');
    try {
      await api.callHomeAssistantService({ domain: 'light', service, entity_id, data: payload });
      scheduleRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Aktion fehlgeschlagen.');
      await load(true);
    } finally {
      setBusyEntity('');
    }
  };

  const setBrightness = (light: WallLight, value: number) => {
    const brightness = clampPercent(value);
    setData((current) => patchWallLights(current, [light.entity_id], { on: true, brightness_pct: brightness }));
    if (brightnessTimers.current[light.entity_id]) {
      window.clearTimeout(brightnessTimers.current[light.entity_id]);
    }
    brightnessTimers.current[light.entity_id] = window.setTimeout(async () => {
      try {
        await api.callHomeAssistantService({
          domain: 'light',
          service: 'turn_on',
          entity_id: light.entity_id,
          data: { brightness_pct: brightness },
        });
        delete brightnessTimers.current[light.entity_id];
        scheduleRefresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Helligkeit konnte nicht gesetzt werden.');
        delete brightnessTimers.current[light.entity_id];
        await load(true);
      }
    }, 220);
  };

  const turnSelected = async (on: boolean) => {
    const ids = allSelectedLights.map((light) => light.entity_id);
    if (ids.length) await callLight(on ? 'turn_on' : 'turn_off', ids);
  };

  const activeLights = data?.lights.filter((light) => light.on).length ?? 0;
  const totalLights = data?.lights.length ?? 0;
  const problemCount = (data?.security.problems.length ?? 0) + (data?.health.unavailable.length ?? 0);

  return (
    <div className="wall-shell">
      <aside className="wall-nav">
        <button className={section === 'home' ? 'active' : ''} onClick={() => setSection('home')} aria-label="Home"><Home size={24} /></button>
        <button className={section === 'lights' ? 'active' : ''} onClick={() => setSection('lights')} aria-label="Lampen"><Lightbulb size={24} /></button>
        <button className={section === 'climate' ? 'active' : ''} onClick={() => setSection('climate')} aria-label="Klima"><Thermometer size={24} /></button>
        <button className={section === 'security' ? 'active' : ''} onClick={() => setSection('security')} aria-label="Sicherheit"><ShieldAlert size={24} /></button>
        <button className={section === 'agents' ? 'active' : ''} onClick={() => setSection('agents')} aria-label="Agenten"><Bot size={24} /></button>
      </aside>

      <main className="wall-main">
        <header className="wall-header">
          <div>
            <span>{formatWallDate(now)}</span>
            <h1>{titleFor(section)}</h1>
            <p>{subtitleFor(section, activeLights, totalLights, problemCount)}</p>
          </div>
          <div className="wall-header-side">
            <strong>{formatClock(now)}</strong>
            <button type="button" onClick={() => load()} disabled={loading} aria-label="Aktualisieren">
              <RefreshCw size={18} /> Aktualisieren
            </button>
          </div>
        </header>

        {error && <section className="wall-error">{error}</section>}
        {runtimeError && <section className="wall-error">Browserfehler: {runtimeError}</section>}
        {!data && !error && <section className="wall-loading">Lade Home Assistant...</section>}

        {data && section === 'home' && <HomeSection data={data} />}
        {data && section === 'lights' && (
          <LightsSection
            groups={data.light_groups}
            visibleGroups={visibleGroups}
            selectedFloor={selectedFloor}
            busyEntity={busyEntity}
            onFloor={setSelectedFloor}
            onToggle={(light) => callLight(light.on ? 'turn_off' : 'turn_on', light.entity_id)}
            onBrightness={setBrightness}
            onBulk={turnSelected}
          />
        )}
        {data && section === 'climate' && <ClimateSection data={data} />}
        {data && section === 'security' && <SecuritySection data={data} />}
        {data && section === 'agents' && <AgentsSection data={data} />}
      </main>
    </div>
  );
}

function HomeSection({ data }: { data: WallDashboardData }) {
  const activeLights = data.lights.filter((light) => light.on).length;
  const open = data.security.openings_open;
  const issues = data.security.problems.length + data.health.unavailable.length;
  return (
    <div className="wall-home-grid">
      <MetricCard icon={<CloudSun size={24} />} label="Wetter" value={data.weather?.state ? labelState(data.weather.state) : 'Keine Daten'} detail={data.weather?.name ?? 'Home Assistant'} />
      <MetricCard icon={<Lightbulb size={24} />} label="Lampen" value={`${activeLights}/${data.lights.length}`} detail="aktiv" />
      <MetricCard icon={<DoorOpen size={24} />} label="Fenster & Türen" value={`${open}/${data.security.openings_total}`} detail="offen" tone={open ? 'warn' : 'ok'} />
      <MetricCard icon={<BatteryWarning size={24} />} label="Batterien" value={`${data.health.low_batteries.length}`} detail="niedrig" tone={data.health.low_batteries.length ? 'warn' : 'ok'} />
      <MetricCard icon={<ShieldAlert size={24} />} label="System" value={`${issues}`} detail="auffällig" tone={issues ? 'warn' : 'ok'} />
      <MetricCard icon={<Bot size={24} />} label="Agenten" value={data.agents.mywellness.is_running ? 'Aktiv' : 'Bereit'} detail="MyWellness" />
      <section className="wall-panel wall-span-2">
        <div className="wall-section-title">
          <span>Etagen</span>
          <strong>{data.light_groups.length}</strong>
        </div>
        <div className="wall-area-strip">
          {data.light_groups.map((group) => (
            <div key={group.area}>
              <strong>{group.area}</strong>
              <span>{group.on}/{group.total} Lampen an</span>
            </div>
          ))}
        </div>
      </section>
      <section className="wall-panel">
        <div className="wall-section-title">
          <span>Letztes Update</span>
          <strong>{formatTime(data.updated_at)}</strong>
        </div>
        <p>{data.home_assistant.entity_count} Home-Assistant-Entities verbunden.</p>
      </section>
    </div>
  );
}

function LightsSection({
  groups,
  visibleGroups,
  selectedFloor,
  busyEntity,
  onFloor,
  onToggle,
  onBrightness,
  onBulk,
}: {
  groups: WallLightGroup[];
  visibleGroups: WallLightGroup[];
  selectedFloor: string;
  busyEntity: string;
  onFloor: (floor: string) => void;
  onToggle: (light: WallLight) => void;
  onBrightness: (light: WallLight, value: number) => void;
  onBulk: (on: boolean) => void;
}) {
  const visibleRooms = visibleGroups.flatMap((group) =>
    (group.rooms?.length ? group.rooms : [{ area: group.area, total: group.total, on: group.on, items: group.items }]).map((room) => ({
      ...room,
      floor: group.area,
    })),
  );

  return (
    <div className="wall-lights">
      <div className="wall-tabs">
        <button className={selectedFloor === 'Alle Etagen' ? 'active' : ''} onClick={() => onFloor('Alle Etagen')}>
          Alle Etagen <span>{groups.reduce((sum, group) => sum + group.on, 0)}/{groups.reduce((sum, group) => sum + group.total, 0)}</span>
        </button>
        {groups.map((group) => (
          <button key={group.area} className={selectedFloor === group.area ? 'active' : ''} onClick={() => onFloor(group.area)}>
            {group.area} <span>{group.on}/{group.total}</span>
          </button>
        ))}
      </div>
      <div className="wall-bulk-actions">
        <button onClick={() => onBulk(false)} disabled={busyEntity === 'bulk'}>Alle aus</button>
        <button className="primary" onClick={() => onBulk(true)} disabled={busyEntity === 'bulk'}>Alle an</button>
      </div>
      <div className="wall-room-grid">
        {visibleRooms.map((room) => (
          <section className="wall-room-card" key={`${room.floor}-${room.area}`}>
            <div className="wall-room-head">
              <span><Lightbulb size={24} /></span>
              <div>
                <h2>{room.area}</h2>
                <p>{room.floor} · {room.on}/{room.total} an</p>
              </div>
            </div>
            <div className="wall-light-list">
              {room.items.map((light) => (
                <LightRow
                  key={light.entity_id}
                  light={light}
                  busy={busyEntity === light.entity_id}
                  onToggle={onToggle}
                  onBrightness={onBrightness}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function ClimateSection({ data }: { data: WallDashboardData }) {
  return (
    <div className="wall-card-grid">
      {data.climate.map((item) => (
        <section className="wall-panel" key={item.entity_id}>
          <div className="wall-section-title">
            <span>{item.area}</span>
            <Thermometer size={20} />
          </div>
          <h2>{item.name}</h2>
          <div className="wall-climate-value">{formatNumber(item.current_temperature)}°C</div>
          <p>Ziel {formatNumber(item.target_temperature)}°C · {item.humidity ?? '--'}% · {labelState(item.state)}</p>
        </section>
      ))}
      {data.climate.length === 0 && <section className="wall-panel">Keine Klima-Entities gefunden.</section>}
    </div>
  );
}

function SecuritySection({ data }: { data: WallDashboardData }) {
  const openItems = data.security.openings.filter((item) => item.state === 'on');
  return (
    <div className="wall-card-grid">
      <MetricCard icon={<DoorOpen size={24} />} label="Offene Kontakte" value={`${openItems.length}`} detail={`${data.security.openings_total} gesamt`} tone={openItems.length ? 'warn' : 'ok'} />
      <MetricCard icon={<ShieldAlert size={24} />} label="Probleme" value={`${data.security.problems.length}`} detail="gemeldet" tone={data.security.problems.length ? 'warn' : 'ok'} />
      <MetricCard icon={<Zap size={24} />} label="Offline" value={`${data.health.unavailable.length}`} detail="unknown/unavailable" tone={data.health.unavailable.length ? 'warn' : 'ok'} />
      <MetricCard icon={<BatteryWarning size={24} />} label="Batterie" value={`${data.health.low_batteries.length}`} detail="niedrig" tone={data.health.low_batteries.length ? 'warn' : 'ok'} />
      <ListPanel title="Offene Fenster & Türen" items={openItems} />
      <ListPanel title="Niedrige Batterien" items={data.health.low_batteries} />
      <ListPanel title="Nicht erreichbar" items={data.health.unavailable.slice(0, 12)} />
    </div>
  );
}

function AgentsSection({ data }: { data: WallDashboardData }) {
  const wellness = data.agents.mywellness;
  const invoices = data.agents.invoices;
  const market = data.agents.market;
  return (
    <div className="wall-card-grid">
      <section className="wall-panel">
        <div className="wall-section-title"><span>Invoice Agent</span><Bot size={20} /></div>
        <h2>{invoices.status === 'ok' ? 'Bereit' : 'Fehler'}</h2>
        <p>{invoices.total ?? 0} Belege · {invoices.needs_review ?? 0} zu prüfen · {invoices.errors ?? 0} Fehler</p>
      </section>
      <section className="wall-panel">
        <div className="wall-section-title"><span>MyWellness</span><Activity size={20} /></div>
        <h2>{wellness.is_running ? 'Läuft' : wellness.enabled === false ? 'Pausiert' : 'Bereit'}</h2>
        <p>Nächster Lauf: {formatWellnessNextRun(wellness)}</p>
      </section>
      <section className="wall-panel">
        <div className="wall-section-title"><span>Market Agent</span><Zap size={20} /></div>
        <h2>{market.status === 'ok' ? 'Bereit' : 'Fehler'}</h2>
        <p>{market.enabled_count ?? 0}/{market.watchlist_count ?? 0} Watchlist aktiv</p>
      </section>
    </div>
  );
}

function LightRow({
  light,
  busy,
  onToggle,
  onBrightness,
}: {
  light: WallLight;
  busy: boolean;
  onToggle: (light: WallLight) => void;
  onBrightness: (light: WallLight, value: number) => void;
}) {
  const brightness = clampPercent(light.brightness_pct ?? (light.on ? 100 : 0));
  return (
    <article className="wall-light-row">
      <div className={`wall-dot ${light.on ? 'on' : ''}`} />
      <div>
        <strong>{light.name}</strong>
        <label>
          <span>Helligkeit</span>
          <span>{brightness}%</span>
        </label>
        <input
          type="range"
          min="0"
          max="100"
          step="1"
          value={brightness}
          onChange={(event) => onBrightness(light, Number(event.target.value))}
        />
      </div>
      <button className={`wall-switch ${light.on ? 'on' : ''}`} onClick={() => onToggle(light)} disabled={busy} aria-label={`${light.name} schalten`} />
    </article>
  );
}

function MetricCard({ icon, label, value, detail, tone = 'info' }: { icon: ReactNode; label: string; value: string; detail: string; tone?: 'info' | 'ok' | 'warn' }) {
  return (
    <section className={`wall-metric ${tone}`}>
      <span>{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
        <p>{detail}</p>
      </div>
    </section>
  );
}

class WallErrorBoundary extends Component<{ children: ReactNode }, { message: string; stack: string }> {
  state = { message: '', stack: '' };

  static getDerivedStateFromError(error: Error) {
    return { message: `${error.name}: ${error.message}`, stack: '' };
  }

  componentDidCatch(_error: Error, info: ErrorInfo) {
    this.setState({ stack: info.componentStack || '' });
  }

  render() {
    if (this.state.message) {
      return (
        <div className="wall-shell">
          <main className="wall-main">
            <section className="wall-error">
              <strong>Wall-Dashboard Fehler</strong>
              <p>{this.state.message}</p>
              {this.state.stack && <pre>{this.state.stack}</pre>}
            </section>
          </main>
        </div>
      );
    }
    return this.props.children;
  }
}

function ListPanel({ title, items }: { title: string; items: Array<{ entity_id: string; name: string; state: string; area?: string }> }) {
  return (
    <section className="wall-panel wall-list-panel">
      <div className="wall-section-title"><span>{title}</span><strong>{items.length}</strong></div>
      {items.length === 0 ? <p>Alles ruhig.</p> : items.slice(0, 8).map((item) => (
        <article key={item.entity_id}>
          <strong>{item.name}</strong>
          <span>{item.area || 'Haus'} · {labelState(item.state)}</span>
        </article>
      ))}
    </section>
  );
}

function titleFor(section: WallSection) {
  if (section === 'lights') return 'Lampen';
  if (section === 'climate') return 'Klima';
  if (section === 'security') return 'Sicherheit';
  if (section === 'agents') return 'Agenten';
  return 'Zuhause';
}

function subtitleFor(section: WallSection, activeLights: number, totalLights: number, problemCount: number) {
  if (section === 'lights') return `${activeLights} von ${totalLights} aktiv`;
  if (section === 'security') return problemCount ? `${problemCount} Geräte prüfen` : 'Keine Geräte auffällig';
  if (section === 'agents') return 'Lokale Automationen und Agentenstatus';
  if (section === 'climate') return 'Temperaturen, Luftfeuchte und Thermostate';
  return 'Hausstatus, Geräte und Agenten auf einen Blick';
}

function labelState(state: string) {
  return state.replace(/_/g, ' ');
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined) return '--';
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  return `${Math.round(number * 10) / 10}`.replace('.', ',');
}

function formatTime(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '--:--';
  return formatClock(date);
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return 'nicht geplant';
  return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()} ${formatClock(date)}`;
}

function formatWellnessNextRun(wellness: Partial<AgentStatus> & { status?: string; error?: string }) {
  const action = nextWellnessAction(wellness);
  if (action === 'book' && wellness.booking_time) return wellness.booking_time.slice(0, 5);
  if (action === 'prepare' && wellness.prepare_time) return wellness.prepare_time.slice(0, 5);
  return wellness.next_scheduled_run ? formatDateTime(wellness.next_scheduled_run) : 'nicht geplant';
}

function nextWellnessAction(wellness: Partial<AgentStatus>) {
  if (wellness.next_scheduled_action) return wellness.next_scheduled_action;
  if (!wellness.next_scheduled_run) return null;
  if (wellness.prepare_enabled !== false && wellness.booking_enabled === false) return 'prepare';
  if (wellness.booking_enabled !== false && wellness.prepare_enabled === false) return 'book';
  const planned = new Date(wellness.next_scheduled_run);
  if (!Number.isFinite(planned.getTime())) return null;
  const plannedTime = `${pad(planned.getHours())}:${pad(planned.getMinutes())}`;
  if (wellness.prepare_time?.slice(0, 5) === plannedTime) return 'prepare';
  if (wellness.booking_time?.slice(0, 5) === plannedTime) return 'book';
  return null;
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function formatClock(date: Date) {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatWallDate(date: Date) {
  const weekdays = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'];
  const months = ['Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  return `${weekdays[date.getDay()]}, ${pad(date.getDate())}. ${months[date.getMonth()]}`;
}

function pad(value: number) {
  return String(value).padStart(2, '0');
}

function patchWallLights(
  current: WallDashboardData | null,
  entityIds: string[],
  patch: Partial<Pick<WallLight, 'on' | 'brightness_pct'>>,
): WallDashboardData | null {
  if (!current) return current;
  const ids = new Set(entityIds);
  const patchLight = (light: WallLight): WallLight => {
    if (!ids.has(light.entity_id)) return light;
    const next = { ...light, ...patch };
    next.state = next.on ? 'on' : 'off';
    return next;
  };
  const countOn = (items: WallLight[]) => items.filter((item) => item.on).length;
  const lights = current.lights.map(patchLight);
  const light_groups = current.light_groups.map((group) => {
    const rooms = (group.rooms ?? []).map((room) => {
      const items = room.items.map(patchLight);
      return { ...room, items, on: countOn(items), total: items.length };
    });
    const items = group.items.map(patchLight);
    return {
      ...group,
      items,
      rooms,
      on: rooms.length ? rooms.reduce((sum, room) => sum + room.on, 0) : countOn(items),
      total: rooms.length ? rooms.reduce((sum, room) => sum + room.total, 0) : items.length,
    };
  });
  return { ...current, lights, light_groups };
}
