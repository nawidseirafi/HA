import { seniorProfile } from '../data/mockSeniorCareData';

const activityBars = [22, 42, 68, 52, 82, 63, 38, 20, 52, 34];

export function DashboardPage() {
  return (
    <section className="sc-page sc-simple-dashboard" aria-label="Sentero Tagesstatus">
      <header className="sc-simple-hero">
        <p className="sc-simple-date">Heute, 10:24</p>
        <p className="sc-simple-person"><span aria-hidden="true" /> {seniorProfile.firstName} · Zuhause</p>
        <h2>Alles in Ordnung.</h2>
        <p className="sc-simple-copy">Der Morgen verlief ruhig und im gewohnten Rhythmus.</p>
      </header>

      <article className="sc-simple-day-card" aria-label="Tagesverlauf">
        <div className="sc-simple-day-head">
          <strong>Tagesverlauf</strong>
          <span>Ruhig</span>
        </div>
        <div className="sc-simple-bars" aria-hidden="true">
          {activityBars.map((height, index) => (
            <i key={`${height}-${index}`} style={{ height: `${height}%` }} />
          ))}
        </div>
      </article>

      <section className="sc-simple-facts" aria-label="Wichtige Tagespunkte">
        <Fact label="Aufgestanden" value="07:12" />
        <Fact label="In der Küche" value="07:48" />
        <Fact label="Letzte Bewegung" value="vor 4 Min." highlight />
      </section>
    </section>
  );
}

function Fact({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="sc-simple-fact">
      <span>{label}</span>
      <strong className={highlight ? 'highlight' : ''}>{value}</strong>
    </div>
  );
}
