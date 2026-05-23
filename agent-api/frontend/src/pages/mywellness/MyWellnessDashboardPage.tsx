import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarCheck, ChevronRight, Dumbbell, Settings } from 'lucide-react';
import type { Route } from '../../App';
import { api, type AgentStatus, type Course, type MyWellnessLog, type MyWellnessSettingsPayload } from '../../api/client';
import { WellnessActivityFeed } from '../../components/mywellness/WellnessActivityFeed';
import { WellnessCourseCard } from '../../components/mywellness/WellnessCourseCard';
import { WellnessDashboardCards } from '../../components/mywellness/WellnessDashboardCards';
import { WellnessSettingsDrawer } from '../../components/mywellness/WellnessSettingsDrawer';
import { formatCourseDate, parseCourseDate } from '../../components/mywellness/courseFormat';

export function MyWellnessDashboardPage({ navigate }: { navigate: (route: Route) => void }) {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [bookings, setBookings] = useState<Course[]>([]);
  const [upcoming, setUpcoming] = useState<Course[]>([]);
  const [logs, setLogs] = useState<MyWellnessLog[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [actionCourseId, setActionCourseId] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const [nextStatus, nextBookings, nextLogs, nextUpcoming] = await Promise.all([
        api.mywellnessStatus(),
        api.mywellnessBookings(),
        api.mywellnessLogs(),
        api.mywellnessUpcomingCourses().catch(() => [] as Course[]),
      ]);
      setStatus(nextStatus);
      setBookings(nextBookings);
      setLogs(nextLogs.items ?? []);
      setUpcoming(nextUpcoming);
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

  const toggleAgent = async () => {
    setLoading(true);
    setNotice('');
    setError('');
    try {
      const active = status?.enabled !== false;
      const next = active ? await api.disableMywellnessAgent() : await api.enableMywellnessAgent();
      setStatus(next);
      setNotice(active ? 'Agent pausiert.' : 'Agent aktiviert.');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Aktion fehlgeschlagen.');
    } finally {
      setLoading(false);
    }
  };

  const bookCourse = async (course: Course) => {
    setActionCourseId(course.id);
    setNotice('');
    setError('');
    try {
      const result = await api.bookMywellnessCourse(course.id);
      setNotice(result.message || 'Kurs gebucht.');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Buchung fehlgeschlagen.');
    } finally {
      setActionCourseId(null);
    }
  };

  const cancelCourse = async (course: Course) => {
    setActionCourseId(course.id);
    setNotice('');
    setError('');
    try {
      const result = await api.cancelMywellnessCourse(course.id);
      setNotice(result.message || 'Buchung storniert.');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Stornierung fehlgeschlagen.');
    } finally {
      setActionCourseId(null);
    }
  };

  const upcomingPreview = useMemo(() => {
    const now = Date.now();
    return [...upcoming]
      .filter((course) => {
        const date = parseCourseDate(course.startTime ?? course.starts_at);
        return date ? date.getTime() >= now : true;
      })
      .sort((left, right) => {
        const a = parseCourseDate(left.startTime ?? left.starts_at)?.getTime() ?? 0;
        const b = parseCourseDate(right.startTime ?? right.starts_at)?.getTime() ?? 0;
        return a - b;
      })
      .slice(0, 6);
  }, [upcoming]);

  return (
    <div className="page-stack wellness-app">
      <header className="wellness-hero-header compact">
        <div>
          <span className="eyebrow">MyWellness</span>
          <h1>MyWellness</h1>
          <p>Kurs-Suche, Buchungsstatus und Agent-Steuerung – alles auf einen Blick.</p>
        </div>
        <button className="icon-button" type="button" onClick={() => setDrawerOpen(true)} aria-label="Einstellungen öffnen"><Settings size={19} /></button>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      {notice && <section className="panel success-panel">{notice}</section>}

      <WellnessDashboardCards
        status={status}
        loading={loading}
        onToggleAgent={toggleAgent}
        onScan={() => run('prepare')}
        onBook={() => run('book')}
      />

      <section className="wellness-booking-summary dense">
        <div className="section-title">
          <div>
            <span className="eyebrow">Aktuell</span>
            <h2>Deine Buchungen</h2>
          </div>
          <button className="button ghost" type="button" onClick={() => navigate({ name: 'mywellnessBookings' })}>
            Alle ansehen <ChevronRight size={14} />
          </button>
        </div>
        <div className="wellness-booking-timeline">
          {bookings.slice(0, 4).map((booking) => (
            <article key={`${booking.id}-${booking.startTime ?? booking.starts_at}`}>
              <span><CalendarCheck size={16} /></span>
              <div>
                <strong>{booking.title}</strong>
                <small>{formatCourseDate(booking.startTime ?? booking.starts_at)}</small>
              </div>
            </article>
          ))}
          {bookings.length === 0 && <div className="wellness-empty-state"><Dumbbell size={18} /> Keine aktuellen Buchungen.</div>}
        </div>
      </section>

      <section className="wellness-upcoming-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">Verfügbar</span>
            <h2>Empfohlene Kurse</h2>
          </div>
          <button className="button ghost" type="button" onClick={() => navigate({ name: 'mywellnessCourses' })}>
            Alle Kurse <ChevronRight size={14} />
          </button>
        </div>
        {upcomingPreview.length === 0 ? (
          <div className="wellness-empty-state"><Dumbbell size={18} /> Aktuell keine offenen Kurse gefunden.</div>
        ) : (
          <div className="wellness-course-grid dense">
            {upcomingPreview.map((course) => (
              <WellnessCourseCard
                key={`${course.id}-${course.startTime ?? course.starts_at}`}
                course={course}
                busy={actionCourseId === course.id}
                onBook={bookCourse}
                onCancel={cancelCourse}
              />
            ))}
          </div>
        )}
      </section>

      <WellnessActivityFeed items={logs} compact />
      <WellnessSettingsDrawer open={drawerOpen} status={status} loading={loading} onClose={() => setDrawerOpen(false)} onSave={saveSettings} />
    </div>
  );
}
