import { Bot, CalendarCheck, Dumbbell, FileText, Home, LineChart, Mail, Settings2 } from 'lucide-react';
import type { Route } from '../App';

interface Props {
  navigate: (route: Route) => void;
}

const plannedAgents = [
  { name: 'Mailbox Agent', text: 'Postfachregeln, Anhänge und Benachrichtigungen.', icon: Mail },
  { name: 'Vacation Agent', text: 'Abwesenheiten und Kalender-Automation.', icon: CalendarCheck },
  { name: 'Home Agent', text: 'Home-Assistant-Aktionen und Routinen.', icon: Home },
  { name: 'System Agent', text: 'Jobs, Logs und Wartung.', icon: Settings2 },
];

export function AgentsPage({ navigate }: Props) {
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Agent Console</span>
          <h1>Agenten</h1>
        </div>
      </header>

      <section className="agent-grid">
        <button className="agent-card active-agent" onClick={() => navigate({ name: 'invoiceDashboard' })}>
          <div className="agent-icon"><FileText size={24} /></div>
          <div>
            <span className="eyebrow">Aktiv</span>
            <h2>Rechnungs-Agent</h2>
            <p>Belege hochladen, mit KI analysieren, prüfen und exportieren.</p>
          </div>
        </button>

        <button className="agent-card active-agent" onClick={() => navigate({ name: 'mywellness' })}>
          <div className="agent-icon"><Dumbbell size={24} /></div>
          <div>
            <span className="eyebrow">Aktiv</span>
            <h2>MyWellness-Agent</h2>
            <p>Kurse finden, Buchungen prüfen und den Agenten manuell steuern.</p>
          </div>
        </button>

        <button className="agent-card active-agent" onClick={() => navigate({ name: 'marketDashboard' })}>
          <div className="agent-icon"><LineChart size={24} /></div>
          <div>
            <span className="eyebrow">Aktiv</span>
            <h2>MarketAgent</h2>
            <p>Watchlist beobachten, Marktberichte erzeugen und Signale einschätzen. Keine Finanzberatung.</p>
          </div>
        </button>

        {plannedAgents.map((agent) => {
          const Icon = agent.icon;
          return (
            <button className="agent-card planned-agent" key={agent.name} disabled>
              <div className="agent-icon"><Icon size={24} /></div>
              <div>
                <span className="eyebrow">Vorbereitet</span>
                <h2>{agent.name}</h2>
                <p>{agent.text}</p>
              </div>
            </button>
          );
        })}
      </section>

      <section className="panel agent-note">
        <Bot size={20} />
        <span>Die Konsole ist jetzt so strukturiert, dass weitere Agenten eigene Bereiche bekommen können.</span>
      </section>
    </div>
  );
}
