import {Bot, Home, Pause, Play, Wifi, WifiOff} from 'lucide-react';
import type {LawnMowerEntity} from '@shared/types/robotDevices';
import {useLawnMower} from '../../hooks/useLawnMower';
import {WallBatteryStatus} from '../common/WallBatteryStatus';

type WallMowerCardProps = {
  mower: LawnMowerEntity;
  onUpdated?: () => void;
};

export function WallMowerCard({mower, onUpdated}: WallMowerCardProps) {
  const {actions, busyAction, offline, call} = useLawnMower(mower, onUpdated);
  const [statusLabel, statusTone] = lawnMowerStatus(mower.raw_status || mower.state);
  const batteryLevel = mowerBatteryLevel(mower);
  const charging = mowerStateIsCharging(mower);
  const connectionLabel = offline ? 'Nicht erreichbar' : 'Verbunden';
  const updated = formatMowerUpdate(mower.last_updated);

  const runAction = async (service: Parameters<typeof call>[0]) => {
    try {
      await call(service);
    } catch {
      // Die Wall bleibt ruhig; der nächste Dashboard-Refresh zeigt den echten Zustand.
    }
  };

  return (
    <article className={`wall-mower-card wall-robot-card ${statusTone}`}>
      <div className="wall-mower-head">
        <span className="wall-mower-icon"><Bot size={28}/></span>
        <div>
          <small>🤖 Gartenroboter</small>
          <h3>{mower.name}</h3>
        </div>
        <b className={`wall-mower-status ${statusTone}`}>{statusLabel}</b>
      </div>

      <div className="wall-mower-body">
        <div className="wall-mower-metric-row">
          <span>Status</span>
          <strong>{statusLabel}</strong>
        </div>
        <div className="wall-mower-metric-row">
          <span>Verbindung</span>
          <strong className={offline ? 'offline' : 'online'}>
            {offline ? <WifiOff size={17}/> : <Wifi size={17}/>}
            {connectionLabel}
          </strong>
        </div>
        {updated && (
          <div className="wall-mower-metric-row subtle">
            <span>Aktualisiert</span>
            <strong>{updated}</strong>
          </div>
        )}
      </div>

      <div className="wall-mower-battery">
        <span>Akku</span>
        <WallBatteryStatus level={batteryLevel} charging={charging} size="lg"/>
      </div>

      <div className="wall-mower-actions">
        <button
          type="button"
          className="primary"
          disabled={actions.start.disabled}
          onClick={() => runAction('start_mowing')}
        >
          <Play size={19}/>
          {busyAction === 'start_mowing' ? 'Startet...' : 'Mähen starten'}
        </button>
        <button
          type="button"
          disabled={actions.pause.disabled}
          onClick={() => runAction('pause')}
        >
          <Pause size={19}/>
          {busyAction === 'pause' ? 'Pausiert...' : 'Pause'}
        </button>
        <button
          type="button"
          disabled={actions.dock.disabled}
          onClick={() => runAction('dock')}
        >
          <Home size={19}/>
          {busyAction === 'dock' ? 'Fährt...' : 'Zur Station'}
        </button>
      </div>
    </article>
  );
}

function lawnMowerStatus(value: string): [string, string] {
  const state = String(value || '').toLowerCase();
  const labels: Record<string, [string, string]> = {
    docked: ['In Ladestation', 'ok'],
    mowing: ['Mäht', 'active'],
    paused: ['Pausiert', 'warn'],
    returning: ['Fährt zurück', 'active'],
    charging: ['Lädt', 'ok'],
    idle: ['Bereit', 'neutral'],
    unavailable: ['Nicht erreichbar', 'offline'],
    unknown: ['Nicht erreichbar', 'offline'],
    error: ['Fehler', 'critical'],
  };
  return labels[state] ?? [labelState(state), 'neutral'];
}

function labelState(value: string) {
  return String(value || 'Unbekannt')
    .replace(/_/g, ' ')
    .replace(/^\w/, (char) => char.toUpperCase());
}

function mowerBatteryLevel(mower: LawnMowerEntity) {
  const value = Number(mower.battery_level);
  if (!Number.isFinite(value)) return textBatteryLevel(mower.state);
  return Math.max(0, Math.min(100, value));
}

function textBatteryLevel(value?: string | null) {
  const state = String(value || '').trim().toLowerCase();
  const levels: Record<string, number> = {
    critical: 5,
    empty: 5,
    low: 10,
    medium: 50,
    normal: 75,
    high: 100,
    full: 100,
    ok: 100,
    charging: 100,
  };
  return levels[state] ?? null;
}

function mowerStateIsCharging(mower: LawnMowerEntity) {
  const state = String(mower.raw_status || mower.state || '').toLowerCase();
  return state === 'charging';
}

function formatMowerUpdate(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}
