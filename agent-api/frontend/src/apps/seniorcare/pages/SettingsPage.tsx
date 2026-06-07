import { Bell, Home, ShieldCheck } from 'lucide-react';

export function SettingsPage() {
  return (
    <section className="seniorcare-page">
      <p className="eyebrow">Einstellungen</p>
      <h2>SeniorCare einrichten</h2>
      <p className="seniorcare-page-lead">Nur produktrelevante Einstellungen fuer Betreuung und Alltagssignale.</p>
      <div className="seniorcare-card-grid">
        <article className="seniorcare-card">
          <span><Home size={18} /> Zuhause</span>
          <h3>Home Assistant</h3>
          <p>Sensoren, Tueren und Aktivitaetssignale verbinden.</p>
        </article>
        <article className="seniorcare-card">
          <span><Bell size={18} /> Hinweise</span>
          <h3>Benachrichtigungen</h3>
          <p>Regeln und Eskalationen fuer Vertrauenspersonen festlegen.</p>
        </article>
        <article className="seniorcare-card">
          <span><ShieldCheck size={18} /> Sicherheit</span>
          <h3>Zugang</h3>
          <p>Benutzerzugang und sichere Anmeldung verwalten.</p>
        </article>
      </div>
    </section>
  );
}
