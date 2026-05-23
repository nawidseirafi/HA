import type { Course } from '../../api/client';
import { courseDayKey, parseCourseDate } from './courseFormat';
import { WellnessCourseCard } from './WellnessCourseCard';
import type { WellnessDay } from './WellnessDaySelector';

interface Props {
  courses: Course[];
  day: WellnessDay;
  actionCourseId: string | null;
  onBook: (course: Course) => void;
  onCancel: (course: Course) => void;
}

export function WellnessCourseGrid({ courses, day, actionCourseId, onBook, onCancel }: Props) {
  const visible = courses
    .filter((course) => courseDayKey(course.startTime ?? course.starts_at) === day)
    .sort((left, right) => {
      const a = parseCourseDate(left.startTime ?? left.starts_at)?.getTime() ?? 0;
      const b = parseCourseDate(right.startTime ?? right.starts_at)?.getTime() ?? 0;
      return a - b;
    });

  return (
    <section className="wellness-course-grid">
      {visible.length === 0 && <div className="wellness-empty-state">Keine Kurse für diesen Tag gefunden.</div>}
      {visible.map((course) => (
        <WellnessCourseCard
          course={course}
          busy={actionCourseId === course.id}
          onBook={onBook}
          onCancel={onCancel}
          key={`${course.id}-${course.startTime ?? course.starts_at}`}
        />
      ))}
    </section>
  );
}
