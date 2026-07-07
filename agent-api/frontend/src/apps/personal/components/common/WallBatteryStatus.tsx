import BoltRoundedIcon from '@mui/icons-material/BoltRounded';

type WallBatteryStatusProps = {
  level: number | null;
  charging?: boolean;
  size?: 'sm' | 'md' | 'lg';
};

export function WallBatteryStatus({level, charging = false, size = 'md'}: WallBatteryStatusProps) {
  const normalizedLevel = normalizeBatteryLevel(level);
  const label = normalizedLevel === null ? '—' : `${Math.round(normalizedLevel)}%`;
  const fillWidth = normalizedLevel === null ? 0 : (22 * normalizedLevel) / 100;

  return (
    <span className={`wall-battery-status ${batteryTone(normalizedLevel)} ${size}`}>
      <span className="wall-battery-icon" aria-hidden="true">
        <svg className="wall-battery-svg" viewBox="0 0 32 18" focusable="false">
          <rect className="wall-battery-shell" x="1.5" y="2.5" width="25" height="13" rx="3"/>
          <rect className="wall-battery-cap" x="28" y="6" width="3" height="6" rx="1.2"/>
          <rect className="wall-battery-fill" x="3.5" y="4.5" width={fillWidth} height="9" rx="1.7"/>
        </svg>
        {charging && <BoltRoundedIcon className="wall-battery-bolt" fontSize="inherit"/>}
      </span>
      <span className="wall-battery-label">{label}</span>
    </span>
  );
}

function normalizeBatteryLevel(level: number | null) {
  if (level === null || level === undefined || !Number.isFinite(Number(level))) return null;
  return Math.max(0, Math.min(100, Number(level)));
}

function batteryTone(level: number | null) {
  if (level === null) return 'unknown';
  if (level <= 14) return 'critical';
  if (level <= 29) return 'orange';
  if (level <= 59) return 'warn';
  return 'normal';
}
