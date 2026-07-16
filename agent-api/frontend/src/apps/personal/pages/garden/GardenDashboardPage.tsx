import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Activity, AlertTriangle, BatteryMedium, CloudRain, Droplets, PauseCircle, Play, RefreshCw, Sprout, Thermometer, Tractor } from 'lucide-react';
import { api, type GardenDecision, type GardenStatus, type GardenZoneStatus } from '@shared/api/client';

const STATUS_LABELS: Record<string, string> = {
  healthy: 'Im Zielbereich',
  dry: 'Trocken',
  critically_dry: 'Kritisch trocken',
  wet: 'Sehr feucht',
  unknown: 'Unbekannt',
  error: 'Fehler',
};

const DECISION_LABELS: Record<string, string> = {
  no_action: 'Keine Aktion',
  monitor: 'Beobachten',
  irrigate: 'Bewässerung empfohlen',
  stop_irrigation: 'Bewässerung stoppen',
  blocked: 'Blockiert',
};

const MOWER_LABELS: Record<string, string> = {
  parked: 'Geparkt',
  mowing: 'Mäht',
  starting: 'Startet',
  returning: 'Fährt zurück',
  paused: 'Pausiert',
  error: 'Fehler',
  unavailable: 'Nicht erreichbar',
  unknown: 'Unbekannt',
};

export function GardenDashboardPage() {
  const [status, setStatus] = useState<GardenStatus | null>(null);
  const [duration, setDuration] = useState(20);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async (silent = false) => {
    if (!silent) setBusy('load');
    setError('');
    try {
      setStatus(await api.gardenStatus());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Garden Dashboard konnte nicht geladen werden.');
    } finally {
      if (!silent) setBusy('');
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load(true), 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  const zones = status?.zones ?? [];
  const primaryZone = zones[0] ?? null;
  const defaultDuration = useMemo(() => {
    const minutes = primaryZone?.decision.recommended_duration_minutes;
    return typeof minutes === 'number' && Number.isFinite(minutes) ? minutes : 20;
  }, [primaryZone]);

  useEffect(() => {
    setDuration(defaultDuration);
  }, [defaultDuration]);

  const evaluate = async () => {
    setBusy('evaluate');
    setNotice('');
    setError('');
    try {
      await api.evaluateGarden(true);
      setNotice('Garden Agent hat die Zonen neu bewertet.');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bewertung fehlgeschlagen.');
    } finally {
      setBusy('');
    }
  };

  const agentEnabled = status?.agent?.enabled ?? false;
  const controlEnabled = status?.agent?.control_enabled ?? false;
  const actionableZones = status?.summary?.actionable_zones ?? 0;
  const activeRuns = status?.summary?.active_irrigation_runs ?? 0;

  const startIrrigation = async (zone: GardenZoneStatus) => {
    const zoneId = gardenZoneId(zone);
    setBusy(`${zoneId}:start`);
    setNotice('');
    setError('');
    try {
      await api.startGardenIrrigation(zoneId, duration);
      setNotice(`${zone.name} wird für ${duration} Minuten bewässert.`);
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bewässerung wurde nicht gestartet.');
    } finally {
      setBusy('');
    }
  };

  const stopIrrigation = async (zone: GardenZoneStatus) => {
    const zoneId = gardenZoneId(zone);
    setBusy(`${zoneId}:stop`);
    setNotice('');
    setError('');
    try {
      await api.stopGardenIrrigation(zoneId);
      setNotice(`${zone.name}: Bewässerung wurde gestoppt.`);
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bewässerung konnte nicht gestoppt werden.');
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="page-stack garden-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Garden Agent</span>
          <h1>Garten</h1>
          <p>Bewertet Rasen, Bodenfeuchte, Bewässerung und Mähroboter über Home Assistant. Automatik bleibt gesperrt, bis sie in der Konfiguration freigegeben ist.</p>
        </div>
        <div className="page-actions">
          <button className="button secondary" type="button" onClick={() => load()} disabled={Boolean(busy)}>
            <RefreshCw size={18} /> Aktualisieren
          </button>
          <button className="button" type="button" onClick={evaluate} disabled={Boolean(busy)}>
            {busy === 'evaluate' ? <Activity size={18} /> : <Sprout size={18} />} Bewerten
          </button>
        </div>
      </header>

      {error && <section className="panel error-panel">{error}</section>}
      {notice && <section className="panel success-panel">{notice}</section>}

      <section className="wellness-card-grid garden-summary-grid">
        <GardenStat icon={<Sprout size={20} />} label="Agent" value={agentEnabled ? 'Aktiv' : 'Inaktiv'} tone={agentEnabled ? 'success' : 'muted'} />
        <GardenStat icon={<Droplets size={20} />} label="Automatik" value={controlEnabled ? 'Freigegeben' : 'Aus'} tone={controlEnabled ? 'warning' : 'muted'} />
        <GardenStat icon={<AlertTriangle size={20} />} label="Empfehlungen" value={String(actionableZones)} tone={actionableZones > 0 ? 'warning' : 'success'} />
        <GardenStat icon={<PauseCircle size={20} />} label="Laufende Bewässerung" value={String(activeRuns)} tone={activeRuns > 0 ? 'info' : 'muted'} />
      </section>

      <section className="garden-zone-list">
        {zones.map((zone) => (
          <ZoneCard
            key={gardenZoneId(zone)}
            zone={zone}
            duration={duration}
            busy={busy}
            onDurationChange={setDuration}
            onStart={startIrrigation}
            onStop={stopIrrigation}
          />
        ))}
        {!busy && zones.length === 0 && (
          <section className="panel garden-empty">
            <Sprout size={22} />
            <span>Keine Garden-Zone gefunden. Prüfe die Garden-Konfiguration.</span>
          </section>
        )}
      </section>
    </div>
  );
}

function ZoneCard({
  zone,
  duration,
  busy,
  onDurationChange,
  onStart,
  onStop,
}: {
  zone: GardenZoneStatus;
  duration: number;
  busy: string;
  onDurationChange: (value: number) => void;
  onStart: (zone: GardenZoneStatus) => void;
  onStop: (zone: GardenZoneStatus) => void;
}) {
  const zoneId = gardenZoneId(zone);
  const decision = zone.decision ?? emptyDecision(zoneId);
  const values = zone.values ?? emptyValues();
  const entities = zone.entities ?? {};
  const hasOpenRun = Boolean(zone.open_irrigation_run);
  const startDisabled = Boolean(busy) || hasOpenRun || !decision.apply_allowed;
  const primaryBlock = decision.blocks[0]?.message;

  return (
    <article className={`panel garden-zone-card ${decision.status}`}>
      <div className="garden-zone-head">
        <div>
          <span className="eyebrow">Zone</span>
          <h2>{zone.name}</h2>
          <p>{DECISION_LABELS[decision.decision] ?? decision.decision} · {STATUS_LABELS[decision.status] ?? decision.status}</p>
        </div>
        <span className={`agent-state-pill ${toneForDecision(decision)}`}>{decision.apply_allowed ? 'Freigegeben' : 'Sicher gesperrt'}</span>
      </div>

      <div className="garden-metric-grid">
        <Metric icon={<Droplets size={18} />} label="Bodenfeuchte" value={formatPercent(values.moisture)} />
        <Metric icon={<Thermometer size={18} />} label="Bodentemperatur" value={formatTemperature(values.temperature ?? values.soil_temperature ?? null)} />
        <Metric icon={<BatteryMedium size={18} />} label="Sensorakku" value={formatPercent(values.battery)} />
        <Metric icon={<CloudRain size={18} />} label="Regen" value={rainLabel(zone)} />
        <Metric icon={<Droplets size={18} />} label="Eve Aqua" value={values.irrigation_active === true ? 'HA meldet an' : values.irrigation_active === false ? 'Aus' : 'Unbekannt'} />
        <Metric icon={<Tractor size={18} />} label="Mähroboter" value={MOWER_LABELS[values.mower_status] ?? values.mower_status} />
      </div>

      <div className="garden-decision-panel">
        <div>
          <span className="eyebrow">Empfehlung</span>
          <strong>{DECISION_LABELS[decision.decision] ?? decision.decision}</strong>
          <p>{decision.recommended_duration_minutes ? `${decision.recommended_duration_minutes} Minuten empfohlen` : 'Keine Bewässerungsdauer empfohlen'} · bewertet {formatDateTime(decision.evaluated_at)}</p>
        </div>
        <div className="garden-irrigation-controls">
          <label className="garden-duration-field">
            Dauer
            <input
              type="number"
              min={1}
              max={120}
              value={duration}
              onChange={(event) => onDurationChange(Number(event.target.value))}
            />
          </label>
          <button className="button primary" type="button" onClick={() => onStart(zone)} disabled={startDisabled}>
            {busy === `${zoneId}:start` ? <Activity size={18} /> : <Play size={18} />} Start
          </button>
          <button className="button secondary" type="button" onClick={() => onStop(zone)} disabled={Boolean(busy) || !hasOpenRun}>
            {busy === `${zoneId}:stop` ? <Activity size={18} /> : <PauseCircle size={18} />} Stop
          </button>
        </div>
      </div>

      {primaryBlock && <ReasonList title="Blockiert durch" items={decision.blocks} tone="block" />}
      {!primaryBlock && decision.reasons.length > 0 && <ReasonList title="Begründung" items={decision.reasons} tone="reason" />}

      <div className="garden-run-meta">
        <span>Letzte Bewässerung: {formatRun(zone.latest_irrigation_run)}</span>
        <span>Automatik Zone: {zone.automatic_enabled ? 'an' : 'aus'}</span>
      </div>

      <details className="garden-diagnostics">
        <summary>Diagnose</summary>
        <dl>
          {Object.entries(entities).map(([key, binding]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{binding.entity_id || '-'} · {binding.source} · {binding.available ? 'verfügbar' : 'nicht verfügbar'}</dd>
            </div>
          ))}
        </dl>
      </details>
    </article>
  );
}

function GardenStat({ icon, label, value, tone }: { icon: ReactNode; label: string; value: string; tone: string }) {
  return (
    <article className={`wellness-stat-card ${tone}`}>
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="garden-metric">
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ReasonList({ title, items, tone }: { title: string; items: GardenDecision['blocks']; tone: 'block' | 'reason' }) {
  return (
    <section className={`garden-reason-list ${tone}`}>
      <span className="eyebrow">{title}</span>
      {items.map((item) => (
        <p key={item.code}>{item.message}</p>
      ))}
    </section>
  );
}

function toneForDecision(decision: GardenDecision) {
  if (decision.apply_allowed) return 'waiting';
  if (decision.blocks.length > 0) return 'error';
  return 'ok';
}

function gardenZoneId(zone: GardenZoneStatus) {
  return zone.zone_id || zone.id || '';
}

function emptyDecision(zoneId: string): GardenDecision {
  return {
    zone_id: zoneId,
    status: 'unknown',
    decision: 'blocked',
    recommended_duration_minutes: null,
    apply_allowed: false,
    reasons: [],
    blocks: [{ code: 'missing_decision', message: 'Für diese Zone liegt noch keine Garden-Entscheidung vor.' }],
    evaluated_at: '',
  };
}

function emptyValues(): GardenZoneStatus['values'] {
  return {
    moisture: null,
    temperature: null,
    battery: null,
    soil_warning: null,
    irrigation_active: null,
    mower_status: 'unknown',
    rain_active: null,
    rain_probability: null,
  };
}

function formatPercent(value: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value)} %` : '-';
}

function formatTemperature(value: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)} °C` : '-';
}

function rainLabel(zone: GardenZoneStatus) {
  const values = zone.values ?? emptyValues();
  if (values.rain_active === true) return 'Aktiv';
  if (typeof values.rain_probability === 'number') return `${Math.round(values.rain_probability)} %`;
  if (values.rain_active === false) return 'Nein';
  return 'Unbekannt';
}

function formatRun(run: GardenZoneStatus['latest_irrigation_run']) {
  if (!run) return 'noch keine';
  return `${formatDateTime(run.started_at)} · ${run.status}`;
}

function formatDateTime(value?: string | null) {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).format(parsed);
}
