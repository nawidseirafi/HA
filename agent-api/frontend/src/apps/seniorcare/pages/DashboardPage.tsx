import { seniorProfile } from '../data/mockSeniorCareData';

const activityBars = [28, 44, 66, 52, 80, 60, 38, 24, 52, 34];

export function DashboardPage() {
  return (
    <section className="sc-page sc-dashboard-page sc-dashboard-minimal">
      <section className="sc-minimal-hero" aria-label="Aktueller Zustand">
        <p className="sc-minimal-date">Heute, 10:24</p>
        <p className="sc-minimal-person"><span /> {seniorProfile.firstName} · Zuhause</p>
        <h1>Alles in Ordnung.</h1>
        <p>Der Morgen verlief ruhig und im gewohnten Rhythmus.</p>
      </section>

      <section className="sc-day-card" aria-label="Tagesverlauf">
        <div className="sc-day-card-head">
          <strong>Tagesverlauf</strong>
          <span>Ruhig</span>
        </div>
        <div className="sc-activity-bars" aria-hidden="true">
          {activityBars.map((height, index) => (
            <i key={`${height}-${index}`} style={{ height: `${height}%` }} />
          ))}
        </div>
      </section>

      <section className="sc-minimal-facts" aria-label="Kurzer Ueberblick">
        <DashboardFact label="Aufgestanden" value="07:12" />
        <DashboardFact label="In der Kueche" value="07:48" />
        <DashboardFact label="Letzte Bewegung" value="vor 4 Min." highlight />
      </section>
    </section>
  );
}

function DashboardFact({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="sc-minimal-fact">
      <span>{label}</span>
      <strong className={highlight ? 'highlight' : ''}>{value}</strong>
    </div>
  );
}
