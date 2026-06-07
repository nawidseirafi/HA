import { PauseCircle, PlayCircle, RefreshCw } from 'lucide-react';
import type { AgentStatus, MyWellnessCourse } from '@shared/api/client';
import { formatCourseDate } from './courseFormat';

interface Props {
  status: AgentStatus | null;
  courses: MyWellnessCourse[];
  loading: boolean;
  onStart: () => void;
  onStop: () => void;
  onRefresh: () => void;
}

export function AgentControlPanel({ status, courses, loading, onStart, onStop, onRefresh }: Props) {
  return (
    <section className="panel control-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Steuerung</span>
          <h2>Agent Control</h2>
        </div>
      </div>
      <div className="button-row">
        <button className="button primary" type="button" onClick={onStart} disabled={loading || status?.is_running}>
          <PlayCircle size={18} />
          Starten
        </button>
        <button className="button secondary" type="button" onClick={onStop} disabled={loading || !status?.enabled}>
          <PauseCircle size={18} />
          Stoppen
        </button>
        <button className="button" type="button" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={18} />
          Aktualisieren
        </button>
      </div>
      <p>{status?.enabled === false ? 'Agent ist deaktiviert.' : 'Manueller Start aktualisiert Kursdaten im Prepare-Modus.'}</p>

      <div className="control-courses">
        <div className="section-title">
          <div>
            <span className="eyebrow">Kurse</span>
            <h2>Gefundene Kurse</h2>
          </div>
          <span className="count-pill">{courses.length}</span>
        </div>
        <div className="control-course-list">
          {courses.length === 0 && <p>Keine Kurse gefunden oder noch keine Kursdaten geladen.</p>}
          {courses.map((course) => (
            <div className="control-course-row" key={`${course.id}-${course.startTime ?? course.starts_at ?? ''}`}>
              <strong>{course.title ?? course.name}</strong>
              <span>{formatCourseDate(course.startTime ?? course.starts_at)}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
