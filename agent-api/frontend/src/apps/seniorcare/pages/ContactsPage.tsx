import { PhoneCall, UserRoundCheck } from 'lucide-react';

export function ContactsPage() {
  return (
    <section className="seniorcare-page">
      <p className="eyebrow">Vertrauenspersonen</p>
      <h2>Kontakte fuer Betreuung</h2>
      <p className="seniorcare-page-lead">Personen, die bei Hinweisen oder Notfaellen informiert werden.</p>
      <div className="seniorcare-card-grid">
        <article className="seniorcare-card prominent">
          <span><UserRoundCheck size={18} /> Primär</span>
          <h3>Max Mustermann</h3>
          <p>Angehoeriger, immer zuerst informieren.</p>
          <button type="button"><PhoneCall size={18} /> Kontakt anzeigen</button>
        </article>
        <article className="seniorcare-card">
          <span>Backup</span>
          <h3>Pflegedienst</h3>
          <p>Wird informiert, falls die primaere Vertrauensperson nicht erreichbar ist.</p>
        </article>
      </div>
    </section>
  );
}
