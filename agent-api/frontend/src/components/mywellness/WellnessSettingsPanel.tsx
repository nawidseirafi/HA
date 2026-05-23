import { CalendarClock, ListChecks, Save } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { AgentStatus, MyWellnessSettingsPayload } from '../../api/client';

interface Props {
  status: AgentStatus | null;
  loading: boolean;
  onSave: (payload: MyWellnessSettingsPayload) => void;
}

function toTimeInput(value?: string) {
  return (value || '').slice(0, 8);
}

export function WellnessSettingsPanel({ status, loading, onSave }: Props) {
  const [prepareEnabled, setPrepareEnabled] = useState(true);
  const [bookingEnabled, setBookingEnabled] = useState(true);
  const [prepareTime, setPrepareTime] = useState('17:00:00');
  const [bookingTime, setBookingTime] = useState('20:59:58');
  const [days, setDays] = useState(2);
  const [courses, setCourses] = useState('Cross-Power\nBody Workout\nFunctional Training');

  useEffect(() => {
    if (!status) return;
    setPrepareEnabled(status.prepare_enabled !== false);
    setBookingEnabled(status.booking_enabled !== false);
    setPrepareTime(toTimeInput(status.prepare_time) || '17:00:00');
    setBookingTime(toTimeInput(status.booking_time) || '20:59:58');
    setDays(status.days ?? 2);
    setCourses((status.desired_courses ?? []).join('\n'));
  }, [status]);

  return (
    <form
      className="panel wellness-settings-panel"
      onSubmit={(event) => {
        event.preventDefault();
        onSave({
          prepare_enabled: prepareEnabled,
          booking_enabled: bookingEnabled,
          prepare_time: prepareTime,
          booking_time: bookingTime,
          days,
          desired_courses: courses.split(/\r?\n|,/).map((course) => course.trim()).filter(Boolean),
        });
      }}
    >
      <section className="wellness-settings-section">
        <div className="wellness-settings-section-head">
          <span><CalendarClock size={18} /></span>
          <div>
            <h3>Automationen</h3>
            <p>Steuere, wann die Kursliste vorbereitet und Buchungen ausgeführt werden.</p>
          </div>
        </div>
        <div className="wellness-setting-row">
          <label className="wellness-toggle-line">
            <input type="checkbox" checked={prepareEnabled} onChange={(event) => setPrepareEnabled(event.target.checked)} />
            <span />
            <strong>Kursliste vorbereiten</strong>
          </label>
          <label className="wellness-field">
            <small>Uhrzeit</small>
            <input type="time" step="1" value={prepareTime} onChange={(event) => setPrepareTime(event.target.value)} />
          </label>
        </div>
        <div className="wellness-setting-row">
          <label className="wellness-toggle-line">
            <input type="checkbox" checked={bookingEnabled} onChange={(event) => setBookingEnabled(event.target.checked)} />
            <span />
            <strong>Automatisch buchen</strong>
          </label>
          <label className="wellness-field">
            <small>Uhrzeit</small>
            <input type="time" step="1" value={bookingTime} onChange={(event) => setBookingTime(event.target.value)} />
          </label>
        </div>
      </section>

      <section className="wellness-settings-section">
        <div className="wellness-settings-section-head">
          <span><ListChecks size={18} /></span>
          <div>
            <h3>Kurs-Suche</h3>
            <p>Lege fest, welche Kurse der Agent bevorzugt und wie weit er voraus schaut.</p>
          </div>
        </div>
        <div className="wellness-settings-grid">
          <label className="wellness-field">
            <small>Tage voraus</small>
            <input type="number" min={0} max={14} value={days} onChange={(event) => setDays(Number(event.target.value))} />
          </label>
          <label className="wellness-field wide">
            <small>Wunschkurse</small>
            <textarea value={courses} onChange={(event) => setCourses(event.target.value)} rows={5} />
          </label>
        </div>
      </section>

      <div className="wellness-settings-footer">
        <button className="button primary" type="submit" disabled={loading}>
          <Save size={18} />
          Einstellungen speichern
        </button>
      </div>
    </form>
  );
}
