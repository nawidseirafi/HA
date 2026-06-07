import { useCallback, useEffect, useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import type { Route } from '../../App';
import { api, type MyWellnessLog } from '@shared/api/client';
import { WellnessActivityFeed } from '../../components/mywellness/WellnessActivityFeed';

export function MyWellnessHistoryPage({ navigate: _navigate }: { navigate: (route: Route) => void }) {
  const [logs, setLogs] = useState<MyWellnessLog[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const nextLogs = await api.mywellnessLogs();
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

  return (
    <div className="page-stack wellness-app">
      <header className="wellness-hero-header compact">
        <div>
          <span className="eyebrow">MyWellness</span>
          <h1>Verlauf</h1>
          <p>Alle Aktionen, Fehler und erfolgreichen Buchungen als Timeline.</p>
        </div>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      <section className="wellness-search-panel">
        <Search size={17} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Verlauf durchsuchen" />
      </section>
      <WellnessActivityFeed items={visibleLogs} />
    </div>
  );
}
