import { HeartPulse, Moon, Pill, ShieldCheck } from 'lucide-react';

export function SeniorPage() {
  return (
    <section className="seniorcare-page">
      <p className="eyebrow">Senior</p>
      <h2>Persoenlicher Status</h2>
      <p className="seniorcare-page-lead">Alltag, Wohlbefinden und wichtige Erinnerungen auf einen Blick.</p>
      <div className="seniorcare-card-grid">
        <article className="seniorcare-card">
          <span><ShieldCheck size={18} /> Status</span>
          <h3>Alles normal</h3>
          <p>Keine Auffaelligkeiten im aktuellen Tagesverlauf.</p>
        </article>
        <article className="seniorcare-card">
          <span><HeartPulse size={18} /> Aktivitaet</span>
          <h3>Regelmaessig aktiv</h3>
          <p>Bewegung wurde in mehreren Wohnbereichen erkannt.</p>
        </article>
        <article className="seniorcare-card">
          <span><Pill size={18} /> Erinnerung</span>
          <h3>20:00 Medikamente</h3>
          <p>Naechste geplante Erinnerung fuer den Abend.</p>
        </article>
        <article className="seniorcare-card">
          <span><Moon size={18} /> Ruhephase</span>
          <h3>Noch nicht begonnen</h3>
          <p>Die Nachtruhe wird spaeter gesondert bewertet.</p>
        </article>
      </div>
    </section>
  );
}
