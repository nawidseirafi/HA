import { Timeline } from '../components/Timeline';
import { historyTimeline } from '../data/mockSeniorCareData';

export function HistoryPage() {
  return (
    <section className="sc-page">
      <div className="sc-hero-copy">
        <p className="sc-kicker">Verlauf</p>
        <h1>Die letzten Tage.</h1>
        <p>Ein ruhiger Rueckblick auf wichtige Momente, ohne Unruhe und ohne technische Details.</p>
      </div>
      <Timeline items={historyTimeline} />
    </section>
  );
}
