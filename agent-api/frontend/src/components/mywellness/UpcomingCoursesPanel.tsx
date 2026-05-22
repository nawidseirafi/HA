import { RefreshCw } from 'lucide-react';
import type { Course } from '../../api/client';
import { CourseCard } from './CourseCard';
import { CourseFilters, type CourseFilter } from './CourseFilters';
import { courseDayKey, parseCourseDate } from './courseFormat';

interface Props {
  courses: Course[];
  filter: CourseFilter;
  loading: boolean;
  actionCourseId: string | null;
  onFilterChange: (filter: CourseFilter) => void;
  onRefresh: () => void;
  onBook: (course: Course) => void;
  onCancel: (course: Course) => void;
}

export function UpcomingCoursesPanel({
  courses,
  filter,
  loading,
  actionCourseId,
  onFilterChange,
  onRefresh,
  onBook,
  onCancel,
}: Props) {
  const visibleCourses = courses
    .filter((course) => courseDayKey(course.startTime) === filter)
    .sort((left, right) => {
      const a = parseCourseDate(left.startTime)?.getTime() ?? 0;
      const b = parseCourseDate(right.startTime)?.getTime() ?? 0;
      return a - b;
    });

  return (
    <section className="panel upcoming-courses-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Verfügbare Kurse</span>
          <h2>Heute bis übermorgen</h2>
        </div>
        <button className="icon-button" type="button" onClick={onRefresh} disabled={loading} aria-label="Kurse aktualisieren">
          <RefreshCw size={18} />
        </button>
      </div>
      <CourseFilters value={filter} onChange={onFilterChange} />
      <div className="upcoming-course-grid">
        {visibleCourses.length === 0 && <p>Keine Kurse gefunden.</p>}
        {visibleCourses.map((course) => (
          <CourseCard
            course={course}
            key={`${course.id}-${course.startTime}`}
            busy={actionCourseId === course.id}
            onBook={onBook}
            onCancel={onCancel}
          />
        ))}
      </div>
    </section>
  );
}
