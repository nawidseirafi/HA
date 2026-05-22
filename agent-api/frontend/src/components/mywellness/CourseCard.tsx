import { CalendarDays, MapPin, UserRound, Users } from 'lucide-react';
import type { Course } from '../../api/client';
import { BookingActionButton } from './BookingActionButton';
import { formatCourseDate } from './courseFormat';

interface Props {
  course: Course;
  busy: boolean;
  onBook: (course: Course) => void;
  onCancel: (course: Course) => void;
}

const statusLabel: Record<Course['status'], string> = {
  available: 'verfügbar',
  booked: 'gebucht',
  full: 'voll',
  waitlist: 'Warteliste',
};

export function CourseCard({ course, busy, onBook, onCancel }: Props) {
  return (
    <article className="upcoming-course-card">
      <div className="course-card-main">
        <div>
          <span className={`booking-pill ${course.status}`}>{statusLabel[course.status] ?? course.status}</span>
          <h3>{course.title}</h3>
        </div>
        <div className="course-card-meta">
          <span><CalendarDays size={15} /> {formatCourseDate(course.startTime)}</span>
          <span><MapPin size={15} /> {course.studio || 'Kein Standort'}</span>
          {course.trainer && <span><UserRound size={15} /> {course.trainer}</span>}
          <span><Users size={15} /> {course.availableSlots ?? '-'} frei</span>
          {course.waitingList && <span>Warteliste aktiv</span>}
        </div>
      </div>
      <BookingActionButton course={course} busy={busy} onBook={onBook} onCancel={onCancel} />
    </article>
  );
}
