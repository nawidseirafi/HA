import { TrustedContactCard } from '../components/Cards';
import { trustedContacts } from '../data/mockSeniorCareData';

export function ContactsPage() {
  return (
    <section className="sc-page">
      <div className="sc-hero-copy">
        <p className="sc-kicker">Kontakte</p>
        <h1>Vertrauenspersonen.</h1>
        <p>Menschen, die im richtigen Moment erreichbar sein sollen.</p>
      </div>
      <div className="sc-contact-list">
        {trustedContacts.map((contact) => <TrustedContactCard contact={contact} key={contact.id} />)}
      </div>
    </section>
  );
}
