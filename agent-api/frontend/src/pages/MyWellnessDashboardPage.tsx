import { useCallback, useEffect, useState } from 'react';
import { CalendarCheck, Dumbbell, Settings } from 'lucide-react';
import type { Route } from '../App';
import { api, type AgentStatus, type Course, type MyWellnessLog, type MyWellnessSettingsPayload } from '../api/client';
import { WellnessActivityFeed } from '../components/mywellness/WellnessActivityFeed';
import { WellnessControlCenter } from '../components/mywellness/WellnessControlCenter';
import { WellnessDashboardCards } from '../components/mywellness/WellnessDashboardCards';
import { WellnessSettingsDrawer } from '../components/mywellness/WellnessSettingsDrawer';
import { formatCourseDate } from '../components/mywellness/courseFormat';

export function MyWellnessDashboardPage({ navigate }: { navigate: (route: Route) => void }) {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [bookings, setBookings] = useState<Course[]>([]);
  const [logs, setLogs] = useState<MyWellnessLog[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const [nextStatus, nextBookings, nextLogs] = await Promise.all([
        api.mywellnessStatus(),
        api.mywellnessBookings(),
        api.mywellnessLogs(),
      ]);
      setStatus(nextStatus);
      setBookings(nextBookings);
      setLogs(nextLogs.items ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'MyWellness konnte nicht geladen werden.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load(true), 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  const run = async (action: 'prepare' | 'book') => {
    setLoading(true);
    setNotice('');
    setError('');
    try {
      const result = action === 'prepare' ? await api.runMywellnessPrepare() : await api.runMywellnessBook();
      setStatus(result.status);
      setNotice(action === 'prepare' ? 'Kursliste wurde vorbereitet.' : 'Buchungsaktion wurde ausgeführt.');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Aktion fehlgeschlagen.');
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
      <header className="wellness-hero-header">
        <div>
          <span className="eyebrow">MyWellness</span>
          <h1>MyWellness</h1>
          <p>Kurs-Suche, Buchungsstatus und Agent-Steuerung.</p>
        </div>
        <button className="icon-button" type="button" onClick={() => setDrawerOpen(true)} aria-label="Einstellungen öffnen"><Settings size={19} /></button>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      {notice && <section className="panel success-panel">{notice}</section>}
      <WellnessDashboardCards status={status} />
      <section className="wellness-dashboard-grid">
        <WellnessControlCenter
          status={status}
          loading={loading}
          onEnable={async () => { setStatus(await api.enableMywellnessAgent()); await load(true); }}
          onDisable={async () => { setStatus(await api.disableMywellnessAgent()); await load(true); }}
          onPrepare={() => run('prepare')}
          onBook={() => run('book')}
        />
        <section className="wellness-booking-summary">
          <div className="section-title">
            <div>
              <span className="eyebrow">Aktuell</span>
              <h2>Deine Buchungen</h2>
            </div>
            <button className="button ghost" type="button" onClick={() => navigate({ name: 'mywellnessBookings' })}>Alle ansehen</button>
          </div>
          {bookings.slice(0, 3).map((booking) => (
            <article key={`${booking.id}-${booking.startTime ?? booking.starts_at}`}>
              <span><CalendarCheck size={16} /></span>
              <div>
                <strong>{booking.title}</strong>
                <small>&nbsp;</small>
                <small>{formatCourseDate(booking.startTime ?? booking.starts_at)}</small>
              </div>

            </article>
          ))}
          {bookings.length === 0 && <div className="wellness-empty-state"><Dumbbell size={18} /> Keine aktuellen Buchungen.</div>}
        </section>
      </section>
      
      <WellnessActivityFeed items={logs} compact />
      <WellnessSettingsDrawer open={drawerOpen} status={status} loading={loading} onClose={() => setDrawerOpen(false)} onSave={saveSettings} />
    </div>
  );
}
