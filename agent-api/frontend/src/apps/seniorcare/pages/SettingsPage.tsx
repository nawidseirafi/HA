import { UpdatePanel } from '@shared/components/system/UpdatePanel';
import { InsightCard } from '../components/Cards';

export function SettingsPage() {
  return (
    <section className="sc-page">
      <div className="sc-hero-copy">
        <p className="sc-kicker">Einstellungen</p>
        <h1>SeniorCare anpassen.</h1>
        <p>Nur das, was fuer Familie, Zuhause und Vertrauen wichtig ist.</p>
      </div>
      <div className="sc-card-stack">
        <InsightCard title="Senior Profil" text="Name, Tagesrhythmus und vertraute Routinen behutsam pflegen." />
        <InsightCard title="Benachrichtigungen" text="Festlegen, welche Hinweise wirklich wichtig sind." />
        <InsightCard title="Zuhause" text="Raeume und Gewohnheiten so beschreiben, wie Angehoerige sie verstehen." />
        <InsightCard title="Datenschutz" text="Daten sparsam nutzen und transparent halten." />
      </div>
      <UpdatePanel variant="seniorcare" />
    </section>
  );
}
