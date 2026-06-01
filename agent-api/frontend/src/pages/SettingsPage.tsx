import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api, type PathSetting, type SettingsInfo } from '../api/client';

function StatusBadge({ ok, label }: { ok: boolean; label?: string }) {
  return <span className={`settings-badge ${ok ? 'ok' : 'warn'}`}>{label ?? (ok ? 'aktiv' : 'fehlt')}</span>;
}

function PathRow({ label, value }: { label: string; value: PathSetting }) {
  return (
    <div className="settings-row settings-path-row">
      <strong>{label}</strong>
      <span className="settings-path-value" title={value.path}>
        <code>{value.path || '-'}</code>
        <StatusBadge ok={value.exists} label={value.exists ? 'vorhanden' : 'fehlt'} />
      </span>
    </div>
  );
}

function SettingRow({ label, value }: { label: string; value: string | number | boolean | null | undefined }) {
  if (typeof value === 'boolean') {
    return (
      <div className="settings-row">
        <strong>{label}</strong>
        <span><StatusBadge ok={value} label={value ? 'Ja' : 'Nein'} /></span>
      </div>
    );
  }
  const display = value ?? '-';
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
          <div className="settings-section-title">
            <span className="eyebrow">System</span>
            <h2>API, Auth und Dateien</h2>
          </div>

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
            <PathRow label="Logdatei" value={settings.storage.log_file} />
            {settings.storage.configured_log_file && (
              <PathRow label="Config Logdatei" value={settings.storage.configured_log_file} />
            )}
          </article>

          <div className="settings-section-title">
            <span className="eyebrow">Agenten</span>
            <h2>Konfiguration und Speicherorte</h2>
          </div>

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
            <SettingRow label="Registry aktiv" value={settings.agents.invoices.registry_enabled} />
            <SettingRow label="API Prefix" value={settings.agents.invoices.api_prefix || '-'} />
            <SettingRow label="Planung" value={settings.agents.invoices.schedule.join(', ') || '-'} />
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
            <SettingRow label="Registry aktiv" value={settings.agents.mywellness.registry_enabled} />
            <SettingRow label="API Prefix" value={settings.agents.mywellness.api_prefix || '-'} />
            <SettingRow label="Zeitraum" value={`${settings.agents.mywellness.days} Tage`} />
            <SettingRow label="Planung" value={settings.agents.mywellness.schedule.join(', ') || '-'} />
            <SettingRow label="Token gesetzt" value={settings.agents.mywellness.token_configured} />
            <SettingRow label="User ID gesetzt" value={settings.agents.mywellness.user_id_configured} />
            <SettingRow label="Facility ID gesetzt" value={settings.agents.mywellness.facility_id_configured} />
            <div className="settings-tags">
              {settings.agents.mywellness.desired_courses.map((course) => <span key={course}>{course}</span>)}
            </div>
          </article>

          {settings.agents.market && (
            <article className="panel settings-card">
              <div className="settings-card-head">
                <div>
                  <span className="eyebrow">Agent</span>
                  <h2>MarketAgent</h2>
                </div>
                <StatusBadge ok={settings.agents.market.enabled} />
              </div>
              <PathRow label="Datenbank" value={settings.agents.market.database} />
              <SettingRow label="Registry aktiv" value={settings.agents.market.registry_enabled} />
              <SettingRow label="API Prefix" value={settings.agents.market.api_prefix || '-'} />
              <SettingRow label="Kursdaten" value={settings.agents.market.price_provider} />
              <SettingRow label="News" value={settings.agents.market.news_provider} />
              <SettingRow label="Trading aktiv" value={settings.agents.market.trading_enabled} />
              <SettingRow label="Hinweis" value={settings.agents.market.disclaimer} />
            </article>
          )}

          <article className="panel settings-card">
            <div className="settings-card-head">
              <div>
                <span className="eyebrow">Agent</span>
                <h2>Vacation</h2>
              </div>
              <StatusBadge ok={settings.agents.vacation.enabled} />
            </div>
            <SettingRow label="Registry aktiv" value={settings.agents.vacation.registry_enabled} />
            <SettingRow label="API Prefix" value={settings.agents.vacation.api_prefix || '-'} />
            <SettingRow label="Mode Entity" value={settings.agents.vacation.mode_entity || '-'} />
            <SettingRow label="Dry Run Default" value={settings.agents.vacation.dry_run_default} />
          </article>

          <div className="settings-section-title">
            <span className="eyebrow">Integrationen</span>
            <h2>KI, Home Assistant und Sicherheit</h2>
          </div>

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
            <SettingRow label="HA URL gesetzt" value={settings.integrations.home_assistant.url_configured} />
            <SettingRow label="HA Token gesetzt" value={settings.integrations.home_assistant.configured} />
            <SettingRow label="HA Notifications" value={settings.integrations.home_assistant.notifications_enabled} />
            <SettingRow label="Notify Service" value={settings.integrations.home_assistant.notify_service || '-'} />
          </article>

          {settings.integrations.household && (
            <article className="panel settings-card">
              <div className="settings-card-head">
                <div>
                  <span className="eyebrow">Integration</span>
                  <h2>Household</h2>
                </div>
                <StatusBadge ok label="Fassade" />
              </div>
              <SettingRow label="Post Entity" value={settings.integrations.household.post_entity} />
              <SettingRow label="Abfall Quelle" value={settings.integrations.household.waste_source} />
              <SettingRow label="Vacation Quelle" value={settings.integrations.household.vacation_source} />
              <SettingRow label="Infrastructure Quelle" value={settings.integrations.household.infrastructure_source} />
            </article>
          )}

          {settings.integrations.infrastructure && (
            <article className="panel settings-card">
              <div className="settings-card-head">
                <div>
                  <span className="eyebrow">Integration</span>
                  <h2>Infrastructure</h2>
                </div>
                <StatusBadge ok={settings.integrations.infrastructure.auto_discovery} label="HA Live" />
              </div>
              <SettingRow label="Quelle" value={settings.integrations.infrastructure.source} />
              <SettingRow label="Auto Discovery" value={settings.integrations.infrastructure.auto_discovery} />
              <SettingRow label="Direkte FritzBox API" value={settings.integrations.infrastructure.direct_fritzbox_api} />
              {Object.entries(settings.integrations.infrastructure.entities).map(([key, value]) => (
                <SettingRow key={key} label={key} value={value || 'Auto'} />
              ))}
            </article>
          )}

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
