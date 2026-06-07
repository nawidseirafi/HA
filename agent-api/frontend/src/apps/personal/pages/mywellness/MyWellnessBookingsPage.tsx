import { useCallback, useEffect, useState } from 'react';
import type { Route } from '../../App';
import { api, type Course } from '@shared/api/client';
import { WellnessBookingsList } from '../../components/mywellness/WellnessBookingsList';

type BookingFilter = 'active' | 'prepared' | 'past' | 'cancelled';

export function MyWellnessBookingsPage({ navigate: _navigate }: { navigate: (route: Route) => void }) {
  const [bookings, setBookings] = useState<Course[]>([]);
  const [prepared, setPrepared] = useState<Course[]>([]);
  const [filter, setFilter] = useState<BookingFilter>('active');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [nextBookings, nextPrepared] = await Promise.all([
        api.mywellnessBookings(),
        api.mywellnessCourses().catch(() => [] as Course[]),
      ]);
      setBookings(nextBookings);
      setPrepared(nextPrepared);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Buchungen konnten nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="page-stack wellness-app">
      <header className="wellness-hero-header compact">
        <div>
          <span className="eyebrow">MyWellness</span>
          <h1>Buchungen</h1>
          <p>Deine kommenden und vergangenen Kurse an einem Ort.</p>
        </div>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      <WellnessBookingsList bookings={bookings} prepared={prepared} filter={filter} onFilterChange={setFilter} />
    </div>
  );
}
