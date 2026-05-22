import { CalendarDays, MapPin } from 'lucide-react';
import type { MyWellnessCourse } from '../../api/client';

interface Props {
  title: string;
  eyebrow: string;
  courses: MyWellnessCourse[];
  emptyText: string;
}

function formatDate(value?: string | null) {
  if (!value) return '-';
  const date = parseCourseDate(value);
  if (Number.isNaN(date.getTime())) return value;
  const day = relativeDay(date);
  const time = new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' }).format(date);
  return time === '00:00' ? day : `${day}, ${time}`;
}

function parseCourseDate(value: string) {
  if (/^\d{8}$/.test(value)) {
    const year = Number(value.slice(0, 4));
    const month = Number(value.slice(4, 6)) - 1;
    const day = Number(value.slice(6, 8));
    return new Date(year, month, day);
  }
  return new Date(value);
}

function relativeDay(date: Date) {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const diffDays = Math.round((target - start) / 86400000);
  if (diffDays === 0) return 'heute';
  if (diffDays === 1) return 'morgen';
  if (diffDays === 2) return 'übermorgen';
  if (diffDays === -1) return 'gestern';
  return new Intl.DateTimeFormat('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit' }).format(date);
}

export function CourseList({ title, eyebrow, courses, emptyText }: Props) {
  return (
    <section className="panel course-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
        </div>
        <span className="count-pill">{courses.length}</span>
      </div>
      <div className="course-list">
        {courses.length === 0 && <p>{emptyText}</p>}
        {courses.map((course) => (
          <article className="course-row" key={`${course.id}-${course.name}-${course.starts_at ?? ''}`}>
            <div>
              <h3>{course.name}</h3>
              <div className="course-meta">
                <span><CalendarDays size={15} /> {formatDate(course.starts_at)}</span>
                <span><MapPin size={15} /> {course.location || 'Kein Standort'}</span>
              </div>
            </div>
            <span className={`booking-pill ${course.booking_status || 'unknown'}`}>{course.booking_status || 'unbekannt'}</span>
          </article>
        ))}
      </div>
    </section>
  );
}
