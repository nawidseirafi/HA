import { useEffect, useMemo, useState } from 'react';
import { api, type SeniorSensorRole } from '@shared/api/client';

export function HistoryPage() {
  const [sensors, setSensors] = useState<SeniorSensorRole[]>([]);

  useEffect(() => {
    void api.seniorSensorRoles(true).then((result) => setSensors(result.sensor_roles)).catch(() => undefined);
  }, []);

  const items = useMemo(() => sensors
    .filter((sensor) => sensor.last_changed || sensor.last_updated || sensor.updated_at)
    .sort((a, b) => stamp(b) - stamp(a))
    .slice(0, 12), [sensors]);

  return (
    <section className="sc-page">
      <div className="sc-hero-copy">
        <p className="sc-kicker">Verlauf</p>
        <h1>Letzte Sensoraktivität.</h1>
        <p>{items.length ? 'Der Verlauf basiert auf echten Sensor-Zeitstempeln.' : 'Noch kein Sensorverlauf verfügbar.'}</p>
      </div>
      <div className="sc-timeline">
        {items.map((sensor) => (
          <article className="sc-timeline-item calm" key={sensor.role}>
            <time>{format(stamp(sensor))}</time>
            <div>
              <strong>{sensor.label || sensor.role}</strong>
              <p>{sensor.reachable === false ? 'Sensor ist nicht erreichbar.' : 'Sensor wurde aktualisiert.'}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function stamp(sensor: SeniorSensorRole) {
  const parsed = new Date(sensor.last_changed || sensor.last_updated || sensor.updated_at || '').getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function format(value: number) {
  if (!value) return 'Noch offen';
  return new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}
