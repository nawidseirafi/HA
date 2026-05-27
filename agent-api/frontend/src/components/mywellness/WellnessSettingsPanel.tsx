import { Activity, CalendarClock, ListChecks, Radar, Save, UploadCloud } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  api,
  type AgentStatus,
  type MyWellnessHealthSettings,
  type MyWellnessSettingsPayload,
  type WithingsEntityCandidate,
} from '../../api/client';

interface Props {
  status: AgentStatus | null;
  loading: boolean;
  onSave: (payload: MyWellnessSettingsPayload) => void;
  mode?: 'booking' | 'health' | 'all';
}

function toTimeInput(value?: string) {
  return (value || '').slice(0, 8);
}

export function WellnessSettingsPanel({ status, loading, onSave, mode = 'all' }: Props) {
  const [agentEnabled, setAgentEnabled] = useState(true);
  const [prepareEnabled, setPrepareEnabled] = useState(true);
  const [bookingEnabled, setBookingEnabled] = useState(true);
  const [prepareTime, setPrepareTime] = useState('17:00:00');
  const [bookingTime, setBookingTime] = useState('20:59:58');
  const [days, setDays] = useState(2);
  const [courses, setCourses] = useState('Cross-Power\nBody Workout\nFunctional Training');
  const [healthSettings, setHealthSettings] = useState<MyWellnessHealthSettings | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthNotice, setHealthNotice] = useState('');
  const [healthError, setHealthError] = useState('');
  const [withingsCandidates, setWithingsCandidates] = useState<WithingsEntityCandidate[]>([]);

  useEffect(() => {
    if (!status) return;
    setAgentEnabled(status.enabled !== false);
    setPrepareEnabled(status.prepare_enabled !== false);
    setBookingEnabled(status.booking_enabled !== false);
    setPrepareTime(toTimeInput(status.prepare_time) || '17:00:00');
    setBookingTime(toTimeInput(status.booking_time) || '20:59:58');
    setDays(status.days ?? 2);
    setCourses((status.desired_courses ?? []).join('\n'));
  }, [status]);

  useEffect(() => {
    let active = true;
    api.mywellnessHealthStatus()
      .then((result) => {
        if (active) setHealthSettings(result.settings);
      })
      .catch((err) => {
        if (active) setHealthError(err instanceof Error ? err.message : 'Health-Einstellungen konnten nicht geladen werden.');
      });
    return () => { active = false; };
  }, []);

  const setHealthField = (field: keyof MyWellnessHealthSettings, value: string | boolean) => {
    setHealthSettings((current) => ({ ...(current ?? { enabled: true }), [field]: value }));
  };

  const saveHealthSettings = async () => {
    if (!healthSettings) return;
    setHealthLoading(true);
    setHealthNotice('');
    setHealthError('');
    try {
      const next = await api.updateMywellnessHealthSettings(healthSettings);
      setHealthSettings(next);
      setHealthNotice('Health / Home Assistant gespeichert.');
    } catch (err) {
      setHealthError(err instanceof Error ? err.message : 'Health-Einstellungen konnten nicht gespeichert werden.');
    } finally {
      setHealthLoading(false);
    }
  };

  const discoverWithings = async () => {
    setHealthLoading(true);
    setHealthNotice('');
    setHealthError('');
    try {
      const result = await api.discoverMywellnessWithingsEntities();
      setWithingsCandidates(result.candidates);
      setHealthNotice(result.error || `${result.candidates.length} mögliche Withings Entities gefunden.`);
    } catch (err) {
      setHealthError(err instanceof Error ? err.message : 'Withings Entities konnten nicht gesucht werden.');
    } finally {
      setHealthLoading(false);
    }
  };

  const importWithings = async () => {
    if (!healthSettings) return;
    setHealthLoading(true);
    setHealthNotice('');
    setHealthError('');
    try {
      const saved = await api.updateMywellnessHealthSettings(healthSettings);
      setHealthSettings(saved);
      const result = await api.importMywellnessWithings();
      if (result.mapping_source === 'auto_discovery') {
        setHealthNotice(result.missing.length ? 'Withings automatisch gefunden, einige Werte sind nicht verfügbar.' : 'Withings Werte automatisch gefunden und importiert.');
      } else {
        setHealthNotice(result.missing.length ? 'Einige Werte sind nicht verfügbar.' : 'Withings Werte aus Home Assistant importiert.');
      }
    } catch (err) {
      setHealthError(err instanceof Error ? err.message : 'Withings Werte konnten nicht importiert werden.');
    } finally {
      setHealthLoading(false);
    }
  };

  return (
    <div className="panel wellness-settings-panel">
      {mode !== 'health' && (
      <form
        className="wellness-settings-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSave({
            enabled: agentEnabled,
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
            <input type="checkbox" checked={agentEnabled} onChange={(event) => setAgentEnabled(event.target.checked)} />
            <span />
            <strong>Automationen aktiv</strong>
          </label>
          <span className={`agent-state-pill ${agentEnabled ? 'ok' : 'waiting'}`}>{agentEnabled ? 'Aktiv' : 'Pausiert'}</span>
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
      )}

      {mode !== 'booking' && (
      <>
      <section className="wellness-settings-section">
        <div className="wellness-settings-section-head">
          <span><Activity size={18} /></span>
          <div>
            <h3>Wellness-Profil</h3>
            <p>Diese Angaben nutzt nur die Wellness-Analyse als Kontext.</p>
          </div>
        </div>
        <div className="wellness-settings-grid">
          <label className="wellness-field">
            <small>Geburtsdatum</small>
            <input
              type="date"
              value={healthSettings?.profile_birth_date ?? ''}
              onChange={(event) => setHealthField('profile_birth_date', event.target.value)}
            />
          </label>
          <label className="wellness-field wide">
            <small>Supplements</small>
            <textarea
              value={healthSettings?.profile_supplements ?? ''}
              onChange={(event) => setHealthField('profile_supplements', event.target.value)}
              rows={4}
              placeholder="B12, Vitamin D, Magnesium"
            />
          </label>
          <label className="wellness-field wide">
            <small>Notizen</small>
            <textarea
              value={healthSettings?.profile_notes ?? ''}
              onChange={(event) => setHealthField('profile_notes', event.target.value)}
              rows={3}
              placeholder="z. B. Trainingsziel, Alltag, Schlafrhythmus"
            />
          </label>
        </div>
        <div className="wellness-settings-footer">
          <button className="button secondary" type="button" disabled={healthLoading || !healthSettings} onClick={saveHealthSettings}>
            <Save size={18} />
            Profil speichern
          </button>
        </div>
      </section>

      <section className="wellness-settings-section">
        <div className="wellness-settings-section-head">
          <span><Activity size={18} /></span>
          <div>
            <h3>Health / Home Assistant</h3>
            <p>Ordne Home-Assistant-Entities den Health-Metriken zu. Fehlende Werte bleiben leer.</p>
          </div>
        </div>
        {healthError && <div className="inline-error">{healthError}</div>}
        {healthNotice && <div className="wellness-inline-success">{healthNotice}</div>}
        <label className="wellness-toggle-line">
          <input
            type="checkbox"
            checked={healthSettings?.enabled !== false}
            onChange={(event) => setHealthField('enabled', event.target.checked)}
          />
          <span />
          <strong>Health-Analyse aktiv</strong>
        </label>
        <div className="wellness-settings-grid">
          <HealthEntityField label="Schritte" value={healthSettings?.ha_entity_steps} onChange={(value) => setHealthField('ha_entity_steps', value)} />
          <HealthEntityField label="Aktive Kalorien" value={healthSettings?.ha_entity_active_calories} onChange={(value) => setHealthField('ha_entity_active_calories', value)} />
          <HealthEntityField label="Schlafstunden" value={healthSettings?.ha_entity_sleep_hours} onChange={(value) => setHealthField('ha_entity_sleep_hours', value)} />
          <HealthEntityField label="Ruhepuls" value={healthSettings?.ha_entity_resting_heart_rate} onChange={(value) => setHealthField('ha_entity_resting_heart_rate', value)} />
          <HealthEntityField label="HRV" value={healthSettings?.ha_entity_hrv} onChange={(value) => setHealthField('ha_entity_hrv', value)} />
          <HealthEntityField label="Gewicht" value={healthSettings?.ha_entity_weight} onChange={(value) => setHealthField('ha_entity_weight', value)} />
          <HealthEntityField label="Blutdruck systolisch" value={healthSettings?.ha_entity_blood_pressure_systolic} onChange={(value) => setHealthField('ha_entity_blood_pressure_systolic', value)} />
          <HealthEntityField label="Blutdruck diastolisch" value={healthSettings?.ha_entity_blood_pressure_diastolic} onChange={(value) => setHealthField('ha_entity_blood_pressure_diastolic', value)} />
        </div>
        <div className="wellness-settings-footer">
          <button className="button secondary" type="button" disabled={healthLoading || !healthSettings} onClick={saveHealthSettings}>
            <Save size={18} />
            Health speichern
          </button>
        </div>
      </section>

      <section className="wellness-settings-section">
        <div className="wellness-settings-section-head">
          <span><Radar size={18} /></span>
          <div>
            <h3>Withings / Home Assistant</h3>
            <p>Withings bleibt in Home Assistant. Der Agent liest nur die konfigurierten HA Entities.</p>
          </div>
        </div>
        <div className="wellness-settings-grid">
          <HealthEntityField label="Gewicht" value={healthSettings?.ha_entity_withings_weight} onChange={(value) => setHealthField('ha_entity_withings_weight', value)} />
          <HealthEntityField label="BMI" value={healthSettings?.ha_entity_withings_bmi} onChange={(value) => setHealthField('ha_entity_withings_bmi', value)} />
          <HealthEntityField label="Fettmasse" value={healthSettings?.ha_entity_withings_fat_mass} onChange={(value) => setHealthField('ha_entity_withings_fat_mass', value)} />
          <HealthEntityField label="Muskelmasse" value={healthSettings?.ha_entity_withings_muscle_mass} onChange={(value) => setHealthField('ha_entity_withings_muscle_mass', value)} />
          <HealthEntityField label="Körperwasser" value={healthSettings?.ha_entity_withings_body_water} onChange={(value) => setHealthField('ha_entity_withings_body_water', value)} />
          <HealthEntityField label="Puls / Ruhepuls" value={healthSettings?.ha_entity_withings_heart_rate} onChange={(value) => setHealthField('ha_entity_withings_heart_rate', value)} />
          <HealthEntityField label="Blutdruck systolisch" value={healthSettings?.ha_entity_withings_systolic_blood_pressure} onChange={(value) => setHealthField('ha_entity_withings_systolic_blood_pressure', value)} />
          <HealthEntityField label="Blutdruck diastolisch" value={healthSettings?.ha_entity_withings_diastolic_blood_pressure} onChange={(value) => setHealthField('ha_entity_withings_diastolic_blood_pressure', value)} />
          <HealthEntityField label="Schlafscore" value={healthSettings?.ha_entity_withings_sleep_score} onChange={(value) => setHealthField('ha_entity_withings_sleep_score', value)} />
          <HealthEntityField label="Schlafdauer" value={healthSettings?.ha_entity_withings_sleep_duration} onChange={(value) => setHealthField('ha_entity_withings_sleep_duration', value)} />
          <HealthEntityField label="Tiefschlaf" value={healthSettings?.ha_entity_withings_deep_sleep} onChange={(value) => setHealthField('ha_entity_withings_deep_sleep', value)} />
          <HealthEntityField label="Leichtschlaf" value={healthSettings?.ha_entity_withings_light_sleep} onChange={(value) => setHealthField('ha_entity_withings_light_sleep', value)} />
          <HealthEntityField label="REM Schlaf" value={healthSettings?.ha_entity_withings_rem_sleep} onChange={(value) => setHealthField('ha_entity_withings_rem_sleep', value)} />
        </div>
        {withingsCandidates.length > 0 && (
          <div className="wellness-candidate-list">
            {withingsCandidates.slice(0, 12).map((candidate) => (
              <button
                key={candidate.entity_id}
                type="button"
                onClick={() => candidate.suggested_metric && setHealthField(candidate.suggested_metric, candidate.entity_id)}
              >
                <strong>{candidate.name || candidate.entity_id}</strong>
                <small>{candidate.entity_id}{candidate.unit ? ` · ${candidate.unit}` : ''}</small>
              </button>
            ))}
          </div>
        )}
        <div className="wellness-settings-footer with-actions">
          <button className="button ghost" type="button" disabled={healthLoading} onClick={discoverWithings}>
            <Radar size={18} />
            Withings Entities suchen
          </button>
          <button className="button secondary" type="button" disabled={healthLoading || !healthSettings} onClick={importWithings}>
            <UploadCloud size={18} />
            Withings Werte importieren
          </button>
          <button className="button primary" type="button" disabled={healthLoading || !healthSettings} onClick={saveHealthSettings}>
            <Save size={18} />
            Speichern
          </button>
        </div>
      </section>
      </>
      )}
    </div>
  );
}

function HealthEntityField({ label, value, onChange }: { label: string; value?: string; onChange: (value: string) => void }) {
  return (
    <label className="wellness-field">
      <small>{label}</small>
      <input value={value ?? ''} onChange={(event) => onChange(event.target.value)} placeholder="sensor..." />
    </label>
  );
}
