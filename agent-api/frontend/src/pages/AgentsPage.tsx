import { useEffect, useState } from 'react';
import { Bot, CalendarCheck, Dumbbell, FileText, Home, LineChart, Mail, Settings2 } from 'lucide-react';
import { api, type AgentManifest, type KnownDashboardRoute } from '../api/client';
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

const iconMap = {
  Bot,
  CalendarCheck,
  Dumbbell,
  FileText,
  Home,
  LineChart,
  Mail,
  Settings2,
};

const dashboardRouteMap: Record<KnownDashboardRoute, Route> = {
  invoiceDashboard: { name: 'invoiceDashboard' },
  mywellnessDashboard: { name: 'mywellnessDashboard' },
  marketDashboard: { name: 'marketDashboard' },
};

export function AgentsPage({ navigate }: Props) {
  const greeting = getGreeting();
  const [agents, setAgents] = useState<AgentManifest[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    api.agents()
      .then(setAgents)
      .catch((err) => setError(err instanceof Error ? err.message : 'Agenten konnten nicht geladen werden.'));
  }, []);

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Agent Console</span>
          <h1>{greeting}, Nawid</h1>
          <p>Wähle einen Agenten oder prüfe den aktuellen Systembereich.</p>
        </div>
      </header>
      {error && <section className="panel error-panel">{error}</section>}

      <section className="agent-grid">
        {agents.map((agent) => {
          const Icon = iconMap[agent.icon as keyof typeof iconMap] ?? Bot;
          const route = routeForAgent(agent);
          return (
            <button
              className={`agent-card ${agent.enabled ? 'active-agent' : 'planned-agent'}`}
              key={agent.id}
              disabled={!route}
              onClick={() => route && navigate(route)}
            >
              <div className="agent-icon"><Icon size={24} /></div>
              <div>
                <span className="eyebrow">{agent.enabled ? 'Aktiv' : 'Installiert'}</span>
                <h2>{agent.name}</h2>
                <p>{agent.description || 'Agent per Manifest eingebunden.'}</p>
              </div>
            </button>
          );
        })}

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
        <span>Agenten werden aus Manifesten geladen. Neue Agenten koennen als Plugin-Ordner unter backend/agents ergänzt werden.</span>
      </section>
    </div>
  );
}

function routeForAgent(agent: AgentManifest): Route | null {
  const routeName = agent.dashboard_route as KnownDashboardRoute | null | undefined;
  return routeName ? dashboardRouteMap[routeName] ?? null : null;
}

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Guten Morgen';
  if (hour < 18) return 'Guten Tag';
  return 'Guten Abend';
}
