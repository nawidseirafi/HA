import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api, type PathSetting, type SettingsInfo } from '../api/client';

function StatusBadge({ ok, label }: { ok: boolean; label?: string }) {
  return <span className={`settings-badge ${ok ? 'ok' : 'warn'}`}>{label ?? (ok ? 'aktiv' : 'fehlt')}</span>;
}

function PathRow({ label, value }: { label: string; value: PathSetting }) {
  return (
    <div className="settings-row">
      <strong>{label}</strong>
      <span title={value.path}>{value.path || '-'} <StatusBadge ok={value.exists} label={value.exists ? 'vorhanden' : 'fehlt'} /></span>
    </div>
  );
}

function SettingRow({ label, value }: { label: string; value: string | number | boolean | null | undefined }) {
  const display = typeof value === 'boolean' ? (value ? 'Ja' : 'Nein') : (value ?? '-');
  return (
    <div className="settings-row">
      <strong>{label}</strong>
      <span>{display}</span>
    </div>
  );
}

export function SettingsPage() {
  const [settings, setSettings] = useState<SettingsInfo | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const loadSettings = async () => {
    setLoading(true);
    setError('');
    try {
      setSettings(await api.settings());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Settings konnten nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">System</span>
          <h1>Settings</h1>
          <p>Aktuelle Laufzeit- und Agent-Konfiguration ohne Secret-Werte.</p>
        </div>
        <button className="button secondary" onClick={loadSettings} disabled={loading}>
          <RefreshCw size={16} /> {loading ? 'Lade...' : 'Aktualisieren'}
        </button>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      {!settings && !error && <section className="panel settings-list">Settings werden geladen...</section>}
      {settings && (
        <section className="settings-grid">
          <article className="panel settings-card">
            <div className="settings-card-head">
              <div>
                <span className="eyebrow">API</span>
                <h2>Backend</h2>
              </div>
              <StatusBadge ok label="online" />
            </div>
            <SettingRow label="Version" value={settings.api.version} />
            <SettingRow label="Adresse" value={`${settings.api.host}:${settings.api.port}`} />
            <SettingRow label="Config" value={settings.api.config_file} />
          </article>

          <article className="panel settings-card">
            <div className="settings-card-head">
              <div>
                <span className="eyebrow">Security</span>
                <h2>Auth</h2>
              </div>
              <StatusBadge ok={settings.auth.enabled} label={settings.auth.mode} />
            </div>
            <SettingRow label="Username ENV" value={settings.auth.username_env} />
            <SettingRow label="Passwort gesetzt" value={settings.auth.password_configured} />
            <SettingRow label="JWT Secret gesetzt" value={settings.auth.jwt_secret_configured} />
            <SettingRow label="Token Laufzeit" value={`${settings.auth.token_ttl_days} Tage`} />
          </article>

          <article className="panel settings-card">
            <div className="settings-card-head">
              <div>
                <span className="eyebrow">Frontend</span>
                <h2>App</h2>
              </div>
              <StatusBadge ok={settings.frontend.production_dist_exists} label={settings.frontend.production_dist_exists ? 'Build vorhanden' : 'Dev'} />
            </div>
            <SettingRow label="Dev Server" value={settings.frontend.dev_server} />
            <SettingRow label="Production Build" value={settings.frontend.production_dist} />
          </article>

          <article className="panel settings-card">
            <div className="settings-card-head">
              <div>
                <span className="eyebrow">Storage</span>
                <h2>Dateien</h2>
              </div>
            </div>
            <PathRow label="Uploads" value={settings.storage.uploads} />
            <PathRow label="Statusdatei" value={settings.storage.status_file} />
            <PathRow label="Logdatei" value={settings.storage.log_file} />
          </article>

          <article className="panel settings-card">
            <div className="settings-card-head">
              <div>
                <span className="eyebrow">Agent</span>
                <h2>Rechnungen</h2>
              </div>
              <StatusBadge ok={settings.agents.invoices.enabled} />
            </div>
            <PathRow label="Inbox" value={settings.agents.invoices.upload_dir} />
            <PathRow label="Datenbank" value={settings.agents.invoices.database} />
            <SettingRow label="KI-Auswertung" value={settings.agents.invoices.ai_extraction_enabled} />
            <SettingRow label="E-Mail Import" value={settings.agents.invoices.email_enabled} />
            <SettingRow label="Portal Import" value={settings.agents.invoices.portal_import_enabled} />
            <SettingRow label="Poll Interval" value={`${settings.agents.invoices.poll_interval_seconds ?? '-'} Sekunden`} />
          </article>

          <article className="panel settings-card">
            <div className="settings-card-head">
              <div>
                <span className="eyebrow">Agent</span>
                <h2>MyWellness</h2>
              </div>
              <StatusBadge ok={settings.agents.mywellness.enabled} />
            </div>
            <PathRow label="Datenbank" value={settings.agents.mywellness.database} />
            <SettingRow label="Zeitraum" value={`${settings.agents.mywellness.days} Tage`} />
            <SettingRow label="Planung" value={settings.agents.mywellness.schedule.join(', ') || '-'} />
            <SettingRow label="Token gesetzt" value={settings.agents.mywellness.token_configured} />
            <SettingRow label="User ID gesetzt" value={settings.agents.mywellness.user_id_configured} />
            <SettingRow label="Facility ID gesetzt" value={settings.agents.mywellness.facility_id_configured} />
            <div className="settings-tags">
              {settings.agents.mywellness.desired_courses.map((course) => <span key={course}>{course}</span>)}
            </div>
          </article>

          <article className="panel settings-card">
            <div className="settings-card-head">
              <div>
                <span className="eyebrow">Integration</span>
                <h2>KI & Home Assistant</h2>
              </div>
            </div>
            <SettingRow label="LLM Provider" value={settings.integrations.llm.provider} />
            <SettingRow label="LLM Modell" value={settings.integrations.llm.model} />
            <SettingRow label="API Key gesetzt" value={settings.integrations.llm.api_key_configured} />
            <SettingRow label="HA Token gesetzt" value={settings.integrations.home_assistant.configured} />
            <SettingRow label="HA Notifications" value={settings.integrations.home_assistant.notifications_enabled} />
            <SettingRow label="Notify Service" value={settings.integrations.home_assistant.notify_service || '-'} />
          </article>

          <article className="panel settings-card">
            <div className="settings-card-head">
              <div>
                <span className="eyebrow">Hinweis</span>
                <h2>Secrets</h2>
              </div>
              <StatusBadge ok={!settings.security.secrets_visible} label="versteckt" />
            </div>
            <SettingRow label="Secret-Werte sichtbar" value={settings.security.secrets_visible} />
            <SettingRow label="Info" value={settings.security.note} />
          </article>
        </section>
      )}
    </div>
  );
}
