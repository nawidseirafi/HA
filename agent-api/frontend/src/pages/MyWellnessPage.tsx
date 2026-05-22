import { useCallback, useEffect, useState } from 'react';
import { Dumbbell } from 'lucide-react';
import { AgentControlPanel } from '../components/mywellness/AgentControlPanel';
import { AgentLogsPanel } from '../components/mywellness/AgentLogsPanel';
import { AgentStatusCard } from '../components/mywellness/AgentStatusCard';
import { AvailableCoursesList } from '../components/mywellness/AvailableCoursesList';
import { CurrentBookingsList } from '../components/mywellness/CurrentBookingsList';
import { api, type AgentStatus, type MyWellnessCourse } from '../api/client';

export function MyWellnessPage() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [courses, setCourses] = useState<MyWellnessCourse[]>([]);
  const [bookings, setBookings] = useState<MyWellnessCourse[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextStatus, nextCourses, nextBookings, nextLogs] = await Promise.all([
        api.mywellnessStatus(),
        api.mywellnessCourses(),
        api.mywellnessBookings(),
        api.mywellnessLogs(),
      ]);
      setStatus(nextStatus);
      setCourses(nextCourses);
      setBookings(nextBookings);
      setLogs(nextLogs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Daten konnten nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const timer = window.setInterval(() => {
      api.mywellnessStatus().then(setStatus).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [loadData]);

  const startAgent = async () => {
    setLoading(true);
    setError(null);
    try {
      setStatus(await api.startMywellnessAgent('prepare'));
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Agent konnte nicht gestartet werden.');
      setLoading(false);
    }
  };

  const stopAgent = async () => {
    setLoading(true);
    setError(null);
    try {
      setStatus(await api.stopMywellnessAgent());
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Agent konnte nicht gestoppt werden.');
      setLoading(false);
    }
  };

  return (
    <div className="page-stack mywellness-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Agent Console</span>
          <h1>MyWellness</h1>
          <p>Kurs-Suche, Buchungsstatus und Agent-Steuerung.</p>
        </div>
        <div className="agent-icon"><Dumbbell size={24} /></div>
      </header>

      {error && <section className="panel error-panel">{error}</section>}

      <div className="mywellness-layout">
        <AgentStatusCard status={status} />
        <div className="mywellness-left-column">
          <AgentControlPanel status={status} loading={loading} onStart={startAgent} onStop={stopAgent} onRefresh={loadData} />
          <AvailableCoursesList courses={courses} />
        </div>
        <div className="mywellness-right-column">
          <CurrentBookingsList bookings={bookings} />
        </div>
        <AgentLogsPanel logs={logs} />
      </div>
    </div>
  );
}
