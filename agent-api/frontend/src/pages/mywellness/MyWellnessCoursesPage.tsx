import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Settings } from 'lucide-react';
import type { Route } from '../../App';
import { api, type AgentStatus, type Course, type MyWellnessSettingsPayload } from '../../api/client';
import { WellnessCourseGrid } from '../../components/mywellness/WellnessCourseGrid';
import { WellnessDaySelector, type WellnessDay } from '../../components/mywellness/WellnessDaySelector';
import { WellnessSettingsDrawer } from '../../components/mywellness/WellnessSettingsDrawer';

export function MyWellnessCoursesPage({ navigate: _navigate }: { navigate: (route: Route) => void }) {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [day, setDay] = useState<WellnessDay>('today');
  const [actionCourseId, setActionCourseId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const [nextStatus, nextCourses] = await Promise.all([api.mywellnessStatus(), api.mywellnessUpcomingCourses()]);
      setStatus(nextStatus);
      setCourses(nextCourses);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Kurse konnten nicht geladen werden.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

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

  const saveSettings = async (payload: MyWellnessSettingsPayload) => {
    setStatus(await api.updateMywellnessSettings(payload));
    setDrawerOpen(false);
    await load(true);
  };

  return (
    <div className="page-stack wellness-app">
      <header className="wellness-hero-header compact">
        <div>
          <span className="eyebrow">MyWellness</span>
          <h1>Kurse</h1>
          <p>Finde verfügbare Sessions und buche direkt deinen Platz.</p>
        </div>
        <div className="button-row">
          <button className="icon-button" type="button" onClick={() => load()} disabled={loading} aria-label="Kurse aktualisieren"><RefreshCw size={19} /></button>
          <button className="icon-button" type="button" onClick={() => setDrawerOpen(true)} aria-label="Einstellungen öffnen"><Settings size={19} /></button>
        </div>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      {notice && <section className="panel success-panel">{notice}</section>}
      <WellnessDaySelector value={day} courses={courses} onChange={setDay} />
      <WellnessCourseGrid courses={courses} day={day} actionCourseId={actionCourseId} onBook={bookCourse} onCancel={cancelCourse} />
      <WellnessSettingsDrawer open={drawerOpen} status={status} loading={loading} onClose={() => setDrawerOpen(false)} onSave={saveSettings} />
    </div>
  );
}
