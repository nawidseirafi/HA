import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Bell, CalendarClock, DoorOpen, HeartPulse, Home, PhoneCall, ShieldCheck, UserRoundCheck } from 'lucide-react';
import { api, type SeniorStatus } from '@shared/api/client';

export function DashboardPage() {
  const [seniorStatus, setSeniorStatus] = useState<SeniorStatus | null>(null);
  const [openNotifications, setOpenNotifications] = useState<number | null>(null);

  useEffect(() => {
    api.seniorStatus().then(setSeniorStatus).catch(() => setSeniorStatus(null));
    api.unreadMessageCount().then((result) => setOpenNotifications(result.unread_count)).catch(() => setOpenNotifications(null));
  }, []);

  const normal = seniorStatus?.enabled !== false && seniorStatus?.status !== 'error';

  return (
    <section className="seniorcare-page seniorcare-dashboard">
      <div className={`seniorcare-status-banner ${normal ? 'normal' : 'attention'}`}>
        <span><ShieldCheck size={30} /></span>
        <div>
          <p className="eyebrow">Senior Status</p>
          <h2>{normal ? 'Alles normal' : 'Aufmerksamkeit notwendig'}</h2>
          <p>{seniorStatus?.message || 'SeniorCare beobachtet Alltagssignale und Hinweise.'}</p>
        </div>
      </div>

      <div className="seniorcare-overview-grid">
        <SeniorMetric icon={<HeartPulse size={22} />} label="Letzte Aktivitaet" value="Heute 18:52" detail="Wohnbereich erkannt" />
        <SeniorMetric icon={<Home size={22} />} label="Heute aktiv" value="6 Raeume genutzt" detail="Normales Bewegungsmuster" />
        <SeniorMetric icon={<DoorOpen size={22} />} label="Letzte Tueroeffnung" value="17:30" detail="Eingangstuer" />
        <SeniorMetric icon={<CalendarClock size={22} />} label="Naechste Erinnerung" value="20:00 Medikamente" detail="Noch nicht bestaetigt" />
        <SeniorMetric icon={<UserRoundCheck size={22} />} label="Vertrauensperson" value="Max Mustermann" detail="Primärer Kontakt" />
        <SeniorMetric icon={<Bell size={22} />} label="Benachrichtigungen" value={`${openNotifications ?? 0} offen`} detail="Betreuungshinweise" />
      </div>

      <div className="seniorcare-two-column">
        <article className="seniorcare-panel">
          <p className="eyebrow">Tagesverlauf</p>
          <h3>Ruhiger Tag ohne Auffaelligkeiten</h3>
          <ul className="seniorcare-timeline">
            <li><span>08:14</span> Erste Bewegung im Wohnbereich</li>
            <li><span>12:05</span> Kueche genutzt</li>
            <li><span>17:30</span> Eingangstuer geoeffnet</li>
            <li><span>18:52</span> Letzte Aktivitaet erkannt</li>
          </ul>
        </article>
        <article className="seniorcare-panel seniorcare-contact-panel">
          <p className="eyebrow">Schnellkontakt</p>
          <h3>Max Mustermann</h3>
          <p>Primäre Vertrauensperson fuer Rueckfragen und Eskalationen.</p>
          <button type="button"><PhoneCall size={18} /> Kontakt anzeigen</button>
        </article>
      </div>
    </section>
  );
}

function SeniorMetric({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string; detail: string }) {
  return (
    <article className="seniorcare-metric-card">
      <span>{icon}</span>
      <small>{label}</small>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  );
}
