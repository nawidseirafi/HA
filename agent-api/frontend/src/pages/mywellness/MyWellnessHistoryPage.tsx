import { useCallback, useEffect, useMemo, useState } from 'react';
import { Search, Settings } from 'lucide-react';
import type { Route } from '../../App';
import { api, type AgentStatus, type MyWellnessLog, type MyWellnessSettingsPayload } from '../../api/client';
import { WellnessActivityFeed } from '../../components/mywellness/WellnessActivityFeed';
import { WellnessSettingsDrawer } from '../../components/mywellness/WellnessSettingsDrawer';

export function MyWellnessHistoryPage({ navigate: _navigate }: { navigate: (route: Route) => void }) {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [logs, setLogs] = useState<MyWellnessLog[]>([]);
  const [query, setQuery] = useState('');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [nextStatus, nextLogs] = await Promise.all([api.mywellnessStatus(), api.mywellnessLogs()]);
      setStatus(nextStatus);
      setLogs(nextLogs.items ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verlauf konnte nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const visibleLogs = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return logs;
    return logs.filter((item) => `${item.action_type} ${item.status} ${item.message}`.toLowerCase().includes(needle));
  }, [logs, query]);

  const saveSettings = async (payload: MyWellnessSettingsPayload) => {
    setStatus(await api.updateMywellnessSettings(payload));
    setDrawerOpen(false);
    await load();
  };

  return (
    <div className="page-stack wellness-app">
      <header className="wellness-hero-header compact">
        <div>
          <span className="eyebrow">MyWellness</span>
          <h1>Verlauf</h1>
          <p>Alle Aktionen, Fehler und erfolgreichen Buchungen als Timeline.</p>
        </div>
        <button className="icon-button" type="button" onClick={() => setDrawerOpen(true)} aria-label="Einstellungen öffnen"><Settings size={19} /></button>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      <section className="wellness-search-panel">
        <Search size={17} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Verlauf durchsuchen" />
      </section>
      <WellnessActivityFeed items={visibleLogs} />
      <WellnessSettingsDrawer open={drawerOpen} status={status} loading={loading} onClose={() => setDrawerOpen(false)} onSave={saveSettings} />
    </div>
  );
}
