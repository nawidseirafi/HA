import type { MyWellnessCourse } from '@shared/api/client';
import { CourseList } from './CourseList';

interface Props {
  courses: MyWellnessCourse[];
}

export function AvailableCoursesList({ courses }: Props) {
  return (
    <CourseList
      title="Gefundene Kurse"
      eyebrow="Kurse"
      courses={courses}
      emptyText="Keine Kurse gefunden oder noch keine Kursdaten geladen."
    />
  );
}
