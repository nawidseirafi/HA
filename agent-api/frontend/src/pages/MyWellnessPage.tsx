import { useCallback, useEffect, useState } from 'react';
import { Dumbbell } from 'lucide-react';
import { AgentControlPanel } from '../components/mywellness/AgentControlPanel';
import { AgentLogsPanel } from '../components/mywellness/AgentLogsPanel';
import { AgentStatusCard } from '../components/mywellness/AgentStatusCard';
import { CurrentBookingsList } from '../components/mywellness/CurrentBookingsList';
import { UpcomingCoursesPanel } from '../components/mywellness/UpcomingCoursesPanel';
import type { CourseFilter } from '../components/mywellness/CourseFilters';
import { api, type AgentStatus, type Course, type MyWellnessCourse } from '../api/client';

export function MyWellnessPage() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [courses, setCourses] = useState<MyWellnessCourse[]>([]);
  const [upcomingCourses, setUpcomingCourses] = useState<Course[]>([]);
  const [bookings, setBookings] = useState<Course[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionCourseId, setActionCourseId] = useState<string | null>(null);
  const [courseFilter, setCourseFilter] = useState<CourseFilter>('today');
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const [nextStatus, nextCourses, nextUpcomingCourses, nextBookings, nextLogs] = await Promise.all([
        api.mywellnessStatus(),
        api.mywellnessCourses(),
        api.mywellnessUpcomingCourses(),
        api.mywellnessBookings(),
        api.mywellnessLogs(),
      ]);
      setStatus(nextStatus);
      setCourses(nextCourses);
      setUpcomingCourses(nextUpcomingCourses);
      setBookings(nextBookings);
      setLogs(nextLogs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Daten konnten nicht geladen werden.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const timer = window.setInterval(() => {
      loadData(true);
    }, 30000);
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

  const bookCourse = async (course: Course) => {
    setActionCourseId(course.id);
    setError(null);
    setNotice(null);
    try {
      const result = await api.bookMywellnessCourse(course.id);
      setNotice(result.message || 'Kurs gebucht.');
      await loadData(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Buchung fehlgeschlagen.');
    } finally {
      setActionCourseId(null);
    }
  };

  const cancelCourse = async (course: Course) => {
    setActionCourseId(course.id);
    setError(null);
    setNotice(null);
    try {
      const result = await api.cancelMywellnessCourse(course.id);
      setNotice(result.message || 'Buchung storniert.');
      await loadData(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Stornierung fehlgeschlagen.');
    } finally {
      setActionCourseId(null);
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
      {notice && <section className="panel success-panel">{notice}</section>}

      <div className="mywellness-layout">
        <AgentStatusCard status={status} />
        <div className="mywellness-left-column">
          <AgentControlPanel status={status} courses={courses} loading={loading} onStart={startAgent} onStop={stopAgent} onRefresh={loadData} />
        </div>
        <div className="mywellness-right-column">
          <CurrentBookingsList bookings={bookings} />
        </div>
        <UpcomingCoursesPanel
          courses={upcomingCourses}
          filter={courseFilter}
          loading={loading}
          actionCourseId={actionCourseId}
          onFilterChange={setCourseFilter}
          onRefresh={() => loadData()}
          onBook={bookCourse}
          onCancel={cancelCourse}
        />
        <AgentLogsPanel logs={logs} />
      </div>
    </div>
  );
}
