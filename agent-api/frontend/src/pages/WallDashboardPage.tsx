import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
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
import { api, type WallDashboardData, type WallLight, type WallLightGroup } from '../api/client';

type WallSection = 'home' | 'lights' | 'climate' | 'security' | 'agents';

export function WallDashboardPage() {
  const [data, setData] = useState<WallDashboardData | null>(null);
  const [section, setSection] = useState<WallSection>('home');
  const [selectedFloor, setSelectedFloor] = useState('Alle Etagen');
  const [loading, setLoading] = useState(false);
  const [busyEntity, setBusyEntity] = useState('');
  const [error, setError] = useState('');
  const [now, setNow] = useState(new Date());

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const next = await api.wallDashboard();
      setData(next);
      if (!next.light_groups.some((group) => group.area === selectedFloor)) {
        setSelectedFloor('Alle Etagen');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Wall-Dashboard konnte nicht geladen werden.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, [selectedFloor]);

  useEffect(() => {
    load();
    const refresh = window.setInterval(() => load(true), 15000);
    const clock = window.setInterval(() => setNow(new Date()), 1000);
    return () => {
      window.clearInterval(refresh);
      window.clearInterval(clock);
    };
  }, [load]);

  const visibleGroups = useMemo(() => {
    if (!data) return [];
    if (selectedFloor === 'Alle Etagen') return data.light_groups;
    return data.light_groups.filter((group) => group.area === selectedFloor);
  }, [data, selectedFloor]);

  const allSelectedLights = useMemo(() => visibleGroups.flatMap((group) => group.items), [visibleGroups]);

  const callLight = async (service: 'turn_on' | 'turn_off', entity_id: string | string[], payload: Record<string, unknown> = {}) => {
    setBusyEntity(Array.isArray(entity_id) ? 'bulk' : entity_id);
    setError('');
    try {
      await api.callHomeAssistantService({ domain: 'light', service, entity_id, data: payload });
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Aktion fehlgeschlagen.');
    } finally {
      setBusyEntity('');
    }
  };

  const setBrightness = async (light: WallLight, value: number) => {
    await callLight('turn_on', light.entity_id, { brightness_pct: value });
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
            <span>{now.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: 'long' })}</span>
            <h1>{titleFor(section)}</h1>
            <p>{subtitleFor(section, activeLights, totalLights, problemCount)}</p>
          </div>
          <div className="wall-header-side">
            <strong>{now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}</strong>
            <button type="button" onClick={() => load()} disabled={loading} aria-label="Aktualisieren">
              <RefreshCw size={18} /> Aktualisieren
            </button>
          </div>
        </header>

        {error && <section className="wall-error">{error}</section>}
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
          <strong>{new Date(data.updated_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}</strong>
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
                <article key={light.entity_id} className="wall-light-row">
                  <div className={`wall-dot ${light.on ? 'on' : ''}`} />
                  <div>
                    <strong>{light.name}</strong>
                    <label>
                      <span>Helligkeit</span>
                      <span>{light.brightness_pct ?? (light.on ? 100 : 0)}%</span>
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="100"
                      value={light.brightness_pct ?? (light.on ? 100 : 1)}
                      onChange={(event) => onBrightness(light, Number(event.target.value))}
                    />
                  </div>
                  <button className={`wall-switch ${light.on ? 'on' : ''}`} onClick={() => onToggle(light)} disabled={busyEntity === light.entity_id} aria-label={`${light.name} schalten`} />
                </article>
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
        <p>Nächster Lauf: {wellness.next_scheduled_run ? new Date(wellness.next_scheduled_run).toLocaleString('de-DE') : 'nicht geplant'}</p>
      </section>
      <section className="wall-panel">
        <div className="wall-section-title"><span>Market Agent</span><Zap size={20} /></div>
        <h2>{market.status === 'ok' ? 'Bereit' : 'Fehler'}</h2>
        <p>{market.enabled_count ?? 0}/{market.watchlist_count ?? 0} Watchlist aktiv</p>
      </section>
    </div>
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
  return Number(value).toLocaleString('de-DE', { maximumFractionDigits: 1 });
}
