import type { Course } from '@shared/api/client';

interface Props {
  course: Course;
  busy: boolean;
  onBook: (course: Course) => void;
  onCancel: (course: Course) => void;
}

export function BookingActionButton({ course, busy, onBook, onCancel }: Props) {
  if (course.booked) {
    return (
      <button className="button secondary" type="button" onClick={() => onCancel(course)} disabled={busy || !course.cancellable}>
        {busy ? 'Storniere...' : 'Stornieren'}
      </button>
    );
  }

  if (course.status === 'full') {
    return (
      <button className="button ghost" type="button" disabled>
        Ausgebucht
      </button>
    );
  }

  if (course.status === 'waitlist') {
    return (
      <button className="button" type="button" onClick={() => onBook(course)} disabled={busy || !course.bookable}>
        {busy ? 'Buche...' : 'Warteliste'}
      </button>
    );
  }

  return (
    <button className="button primary" type="button" onClick={() => onBook(course)} disabled={busy || !course.bookable}>
      {busy ? 'Buche...' : 'Buchen'}
    </button>
  );
}
