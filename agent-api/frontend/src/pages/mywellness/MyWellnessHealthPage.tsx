import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Activity, Brain, Dumbbell, Flame, Footprints, HeartPulse, Moon, Scale, Settings, Sparkles } from 'lucide-react';
import { api, type AgentStatus, type MyWellnessHealthStatus, type MyWellnessSettingsPayload } from '../../api/client';
import { WellnessSettingsDrawer } from '../../components/mywellness/WellnessSettingsDrawer';

export function MyWellnessHealthPage() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [health, setHealth] = useState<MyWellnessHealthStatus | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const [nextStatus, nextHealth] = await Promise.all([
        api.mywellnessStatus(),
        api.mywellnessHealthStatus(),
      ]);
      setStatus(nextStatus);
      setHealth(nextHealth);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Health-Daten konnten nicht geladen werden.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const importWithings = async () => {
    setLoading(true);
    setNotice('');
    setError('');
    try {
      const result = await api.importMywellnessWithings();
      setNotice(result.missing.length ? 'Einige Withings Werte sind nicht verfügbar.' : 'Withings Werte aus Home Assistant importiert.');
      setHealth(await api.mywellnessHealthStatus());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Withings Werte konnten nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  };

  const analyzeHealth = async () => {
    setLoading(true);
    setNotice('');
    setError('');
    try {
      await api.analyzeMywellnessHealth();
      setNotice('Wellness-Analyse wurde erstellt.');
      setHealth(await api.mywellnessHealthStatus());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Wellness-Analyse fehlgeschlagen.');
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async (payload: MyWellnessSettingsPayload) => {
    setLoading(true);
    setError('');
    try {
      setStatus(await api.updateMywellnessSettings(payload));
      setNotice('Einstellungen gespeichert.');
      setDrawerOpen(false);
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Einstellungen konnten nicht gespeichert werden.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-stack wellness-app">
      <header className="wellness-hero-header compact">
        <div>
          <span className="eyebrow">MyWellness</span>
          <h1>Health</h1>
          <p>Recovery, Readiness und Withings-Werte aus Home Assistant.</p>
        </div>
        <button className="icon-button" type="button" onClick={() => setDrawerOpen(true)} aria-label="Einstellungen öffnen"><Settings size={19} /></button>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      {notice && <section className="panel success-panel">{notice}</section>}

      <section className="wellness-health-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">Health</span>
            <h2>Recovery & Readiness</h2>
          </div>
          <div className="wellness-control-actions">
            <button className="button secondary" type="button" onClick={importWithings} disabled={loading}>
              <Scale size={16} /> Withings Werte importieren
            </button>
            <button className="button primary" type="button" onClick={analyzeHealth} disabled={loading}>
              <Brain size={16} /> Wellness-Analyse starten
            </button>
          </div>
        </div>
        <div className="wellness-health-layout">
          <div className="wellness-health-grid">
            <HealthStat icon={<Sparkles size={18} />} label="Recovery Score" value={scoreValue(health?.latest_report?.recovery_score)} tone={scoreTone(health?.latest_report?.recovery_score)} />
            <HealthStat icon={<Dumbbell size={18} />} label="Training Readiness" value={scoreValue(health?.latest_report?.training_readiness)} tone={scoreTone(health?.latest_report?.training_readiness)} />
            <HealthStat icon={<Flame size={18} />} label="Stress Level" value={levelLabel(health?.latest_report?.stress_level)} tone={stressTone(health?.latest_report?.stress_level)} />
            <HealthStat icon={<Moon size={18} />} label="Schlaf" value={metricValue(health?.latest_metrics?.sleep_hours, 'h')} />
            <HealthStat icon={<Footprints size={18} />} label="Schritte" value={metricValue(health?.latest_metrics?.steps)} />
            <HealthStat icon={<Flame size={18} />} label="Kalorien" value={metricValue(health?.latest_metrics?.active_calories, 'kcal')} />
            <HealthStat icon={<HeartPulse size={18} />} label="Ruhepuls" value={metricValue(health?.latest_metrics?.resting_heart_rate, 'bpm')} />
            <HealthStat icon={<Activity size={18} />} label="HRV" value={metricValue(health?.latest_metrics?.hrv, 'ms')} />
            <HealthStat icon={<Scale size={18} />} label="Gewicht" value={metricValue(health?.latest_metrics?.weight, 'kg')} />
            <HealthStat icon={<Activity size={18} />} label="BMI" value={metricValue(health?.latest_metrics?.bmi)} />
            <HealthStat icon={<Moon size={18} />} label="Schlafscore" value={metricValue(health?.latest_metrics?.sleep_score)} />
            <HealthStat icon={<HeartPulse size={18} />} label="Blutdruck" value={bloodPressureValue(health?.latest_metrics?.blood_pressure_systolic, health?.latest_metrics?.blood_pressure_diastolic)} />
            <HealthStat icon={<Activity size={18} />} label="Körperfett" value={metricValue(health?.latest_metrics?.fat_mass, 'kg')} />
            <HealthStat icon={<Dumbbell size={18} />} label="Muskelmasse" value={metricValue(health?.latest_metrics?.muscle_mass, 'kg')} />
          </div>
          <article className="wellness-report-panel">
            <div className="wellness-report-head">
              <span><Brain size={18} /></span>
              <div>
                <strong>KI Empfehlung</strong>
                <small>{health?.latest_report?.report_date ?? 'Noch keine Analyse'}</small>
              </div>
            </div>
            <p>{health?.latest_report?.summary || 'Importiere Withings-Werte und starte danach eine Wellness-Analyse.'}</p>
            {!hasWithingsConfigured(health) && <p>Noch keine Withings Entities verbunden.</p>}
            <p>{health?.latest_report?.recommendation || 'Die regelbasierte Recovery-Bewertung funktioniert auch, wenn die KI nicht erreichbar ist.'}</p>
            {health?.latest_report?.recommended_workout_type && (
              <span className="booking-pill available">{health.latest_report.recommended_workout_type}</span>
            )}
            {health?.latest_report?.warnings?.length ? (
              <small className="wellness-report-warning">{health.latest_report.warnings[0]}</small>
            ) : null}
          </article>
        </div>
      </section>

      <WellnessSettingsDrawer open={drawerOpen} status={status} loading={loading} mode="health" onClose={() => setDrawerOpen(false)} onSave={saveSettings} />
    </div>
  );
}

function HealthStat({ icon, label, value, tone = 'info' }: { icon: ReactNode; label: string; value: string; tone?: 'success' | 'warning' | 'muted' | 'info' }) {
  return (
    <article className={`wellness-stat-card compact ${tone}`}>
      <div className="wellness-stat-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function metricValue(value?: number | null, unit = '') {
  if (value === null || value === undefined) return 'Keine Daten';
  const formatted = Number.isInteger(value) ? value.toLocaleString('de-DE') : value.toLocaleString('de-DE', { maximumFractionDigits: 1 });
  return unit ? `${formatted} ${unit}` : formatted;
}

function scoreValue(value?: number | null) {
  return value === null || value === undefined ? 'Keine Analyse' : `${value}/100`;
}

function scoreTone(value?: number | null): 'success' | 'warning' | 'muted' | 'info' {
  if (value === null || value === undefined) return 'muted';
  if (value >= 70) return 'success';
  if (value >= 45) return 'warning';
  return 'muted';
}

function stressTone(value?: string | null): 'success' | 'warning' | 'muted' | 'info' {
  if (value === 'low') return 'success';
  if (value === 'medium') return 'warning';
  if (value === 'high') return 'muted';
  return 'info';
}

function levelLabel(value?: string | null) {
  if (value === 'low') return 'Niedrig';
  if (value === 'medium') return 'Mittel';
  if (value === 'high') return 'Hoch';
  return 'Keine Analyse';
}

function bloodPressureValue(systolic?: number | null, diastolic?: number | null) {
  if (systolic === null || systolic === undefined || diastolic === null || diastolic === undefined) return 'Keine Daten';
  return `${Math.round(systolic)}/${Math.round(diastolic)}`;
}

function hasWithingsConfigured(health: MyWellnessHealthStatus | null) {
  if (!health?.settings) return false;
  return Object.entries(health.settings).some(([key, value]) => key.startsWith('ha_entity_withings_') && Boolean(value));
}
