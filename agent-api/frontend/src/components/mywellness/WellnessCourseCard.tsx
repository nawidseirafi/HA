import { MapPin, Sparkles, UserRound, Users } from 'lucide-react';
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
  available: 'Verfügbar',
  booked: 'Gebucht',
  full: 'Voll',
  waitlist: 'Warteliste',
};

function category(course: Course) {
  const title = `${course.title} ${course.category ?? ''}`.toLowerCase();
  if (/yoga|mobility|stretch/.test(title)) return 'Mobility';
  if (/cycling|bike|spinning/.test(title)) return 'Cycling';
  if (/aqua|wasser/.test(title)) return 'Aqua';
  if (/power|strength|functional|workout/.test(title)) return 'Strength';
  return 'Class';
}

function badges(course: Course) {
  const result = [];
  if (course.is_desired) result.push('Empfohlen');
  if ((course.availableSlots ?? 99) <= 2 && course.status === 'available') result.push('Fast ausgebucht');
  if (course.waitingList) result.push('Warteliste');
  return result;
}

export function WellnessCourseCard({ course, busy, onBook, onCancel }: Props) {
  return (
    <article className={`wellness-course-card ${course.status}`}>
      <div className="wellness-course-top">
        <span className={`booking-pill ${course.status}`}>{statusLabel[course.status] ?? course.status}</span>
        <small>{category(course)}</small>
      </div>
      <div className="wellness-course-title">
        <h3>{course.title}</h3>
        <strong>{formatCourseDate(course.startTime ?? course.starts_at)}</strong>
      </div>
      <div className="wellness-course-meta">
        <span><Users size={14} /> {course.availableSlots ?? '-'} frei</span>
        {course.trainer && <span><UserRound size={14} /> {course.trainer}</span>}
        <span><MapPin size={14} /> {course.studio || course.location || 'Studio'}</span>
      </div>
      {badges(course).length > 0 && (
        <div className="wellness-course-badges">
          {badges(course).map((badge) => <span key={badge}><Sparkles size={12} /> {badge}</span>)}
        </div>
      )}
      <BookingActionButton course={course} busy={busy} onBook={onBook} onCancel={onCancel} />
    </article>
  );
}
