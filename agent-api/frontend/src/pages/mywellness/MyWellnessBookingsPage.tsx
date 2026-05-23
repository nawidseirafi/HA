import { useCallback, useEffect, useState } from 'react';
import { Settings } from 'lucide-react';
import type { Route } from '../../App';
import { api, type AgentStatus, type Course, type MyWellnessSettingsPayload } from '../../api/client';
import { WellnessBookingsList } from '../../components/mywellness/WellnessBookingsList';
import { WellnessSettingsDrawer } from '../../components/mywellness/WellnessSettingsDrawer';

type BookingFilter = 'active' | 'past' | 'cancelled';

export function MyWellnessBookingsPage({ navigate: _navigate }: { navigate: (route: Route) => void }) {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [bookings, setBookings] = useState<Course[]>([]);
  const [filter, setFilter] = useState<BookingFilter>('active');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [nextStatus, nextBookings] = await Promise.all([api.mywellnessStatus(), api.mywellnessBookings()]);
      setStatus(nextStatus);
      setBookings(nextBookings);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Buchungen konnten nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveSettings = async (payload: MyWellnessSettingsPayload) => {
    setStatus(await api.updateMywellnessSettings(payload));
    setDrawerOpen(false);
    await load();
  };

  return (
    <div className="page-stack wellness-app">
      <header className="wellness-hero-header compact">
        <div>
          <span className="eyebrow">MyWellness</span>
          <h1>Buchungen</h1>
          <p>Deine kommenden und vergangenen Kurse an einem Ort.</p>
        </div>
        <button className="icon-button" type="button" onClick={() => setDrawerOpen(true)} aria-label="Einstellungen öffnen"><Settings size={19} /></button>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      <WellnessBookingsList bookings={bookings} filter={filter} onFilterChange={setFilter} />
      <WellnessSettingsDrawer open={drawerOpen} status={status} loading={loading} onClose={() => setDrawerOpen(false)} onSave={saveSettings} />
    </div>
  );
}
