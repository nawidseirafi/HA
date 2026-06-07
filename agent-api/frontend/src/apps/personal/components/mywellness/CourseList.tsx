import { CalendarDays, MapPin } from 'lucide-react';
import type { MyWellnessCourse } from '@shared/api/client';
import { formatCourseDate } from './courseFormat';

interface Props {
  title: string;
  eyebrow: string;
  courses: MyWellnessCourse[];
  emptyText: string;
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
          <article className="course-row" key={`${course.id}-${course.title ?? course.name}-${course.startTime ?? course.starts_at ?? ''}`}>
            <div>
              <h3>{course.title ?? course.name}</h3>
              <div className="course-meta">
                <span><CalendarDays size={15} /> {formatCourseDate(course.startTime ?? course.starts_at)}</span>
                <span><MapPin size={15} /> {course.studio || course.location || 'Kein Standort'}</span>
              </div>
            </div>
            <span className={`booking-pill ${course.status || course.booking_status || 'unknown'}`}>{course.status || course.booking_status || 'unbekannt'}</span>
          </article>
        ))}
      </div>
    </section>
  );
}
