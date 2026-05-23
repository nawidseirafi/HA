import { CalendarCheck, Search } from 'lucide-react';

interface Props {
  loading: boolean;
  onPrepare: () => void;
  onBook: () => void;
}

export function WellnessActions({ loading, onPrepare, onBook }: Props) {
  return (
    <section className="panel wellness-actions-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Aktionen</span>
          <h2>Manuell ausführen</h2>
        </div>
      </div>
      <div className="button-row">
        <button className="button primary" type="button" onClick={onPrepare} disabled={loading}>
          <Search size={18} />
          Prepare jetzt starten
        </button>
        <button className="button secondary" type="button" onClick={onBook} disabled={loading}>
          <CalendarCheck size={18} />
          Booking jetzt starten
        </button>
      </div>
    </section>
  );
}
