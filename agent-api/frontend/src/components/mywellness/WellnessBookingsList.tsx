import { CalendarCheck, MapPin } from 'lucide-react';
import type { Course } from '../../api/client';
import { formatCourseDate, parseCourseDate } from './courseFormat';

type Filter = 'active' | 'past' | 'cancelled';

export function WellnessBookingsList({ bookings, filter, onFilterChange }: { bookings: Course[]; filter: Filter; onFilterChange: (filter: Filter) => void }) {
  const now = Date.now();
  const filtered = bookings.filter((booking) => {
    const date = parseCourseDate(booking.startTime ?? booking.starts_at)?.getTime() ?? now;
    if (filter === 'past') return date < now;
    if (filter === 'cancelled') return booking.status === 'available' && !booking.booked;
    return booking.booked || date >= now;
  });

  return (
    <section className="wellness-bookings-list">
      <div className="wellness-filter-row">
        {(['active', 'past', 'cancelled'] as Filter[]).map((item) => (
          <button className={filter === item ? 'active' : ''} type="button" onClick={() => onFilterChange(item)} key={item}>
            {item === 'active' ? 'Aktiv' : item === 'past' ? 'Vergangen' : 'Storniert'}
          </button>
        ))}
      </div>
      <div className="wellness-booking-timeline">
        {filtered.length === 0 && <div className="wellness-empty-state">Keine Buchungen in dieser Ansicht.</div>}
        {filtered.map((booking) => (
          <article className="wellness-booking-card" key={`${booking.id}-${booking.startTime ?? booking.starts_at}`}>
            <span><CalendarCheck size={17} /></span>
            <div>
              <strong>{booking.title}</strong>
              <small>{formatCourseDate(booking.startTime ?? booking.starts_at)}</small>
              <small><MapPin size={13} /> {booking.studio || booking.location || 'Studio'}</small>
            </div>
            <b className={`booking-pill ${booking.status}`}>{booking.status}</b>
          </article>
        ))}
      </div>
    </section>
  );
}
