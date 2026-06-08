import { RoomMap } from '../components/RoomCards';
import { rooms, seniorProfile } from '../data/mockSeniorCareData';

export function RoomsPage() {
  return (
    <section className="sc-page">
      <div className="sc-hero-copy">
        <p className="sc-kicker">Raeume</p>
        <h1>Das Zuhause im Blick.</h1>
        <p>{seniorProfile.firstName} haelt sich gerade im Wohnzimmer auf. Alles wirkt ruhig.</p>
      </div>
      <RoomMap rooms={rooms} />
    </section>
  );
}
