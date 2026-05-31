import { useEffect, useState } from 'react';
import { Bot, CalendarCheck, Dumbbell, FileText, Heart, Home, LineChart, Mail, Settings2, ShieldCheck } from 'lucide-react';
import { api, type AgentManifest, type KnownDashboardRoute } from '../api/client';
import type { Route } from '../App';
import { AgentMap, agentStatusLabel, statusForAgentDisplay, statusesFromOrchestratorMap } from '../components/AgentMap';

interface Props {
  navigate: (route: Route) => void;
}

const iconMap = {
  Bot,
  CalendarCheck,
  Dumbbell,
  FileText,
  Heart,
  Hearth: Heart,
  Home,
  LineChart,
  Mail,
  Settings2,
  ShieldCheck,
};

const dashboardRouteMap: Record<KnownDashboardRoute, Route> = {
  invoiceDashboard: { name: 'invoiceDashboard' },
  mywellnessDashboard: { name: 'mywellnessDashboard' },
  marketDashboard: { name: 'marketDashboard' },
};

export function AgentsPage({ navigate }: Props) {
  const greeting = getGreeting();
  const [agents, setAgents] = useState<AgentManifest[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<ReturnType<typeof statusesFromOrchestratorMap>>({});
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    let refresh: number | null = null;

    api.agents()
      .then((nextAgents) => mounted && setAgents(nextAgents))
      .catch((err) => mounted && setError(err instanceof Error ? err.message : 'Agenten konnten nicht geladen werden.'));

    const loadStatuses = () => {
      api.orchestratorMap()
        .then((map) => mounted && setAgentStatuses(statusesFromOrchestratorMap(map)))
        .catch(() => undefined);
    };
    loadStatuses();
    refresh = window.setInterval(loadStatuses, 15000);

    return () => {
      mounted = false;
      if (refresh) window.clearInterval(refresh);
    };
  }, []);

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Agent Console</span>
          <h1>{greeting}, Nawid</h1>
          <p>Systemübersicht der lokalen Agenten. Wähle einen Agenten für Details oder nutze die Map zur Orientierung.</p>
        </div>
      </header>
      {error && <section className="panel error-panel">{error}</section>}

      <AgentMap navigate={navigate} />

      <section className="agent-grid">
        {agents.map((agent) => {
          const Icon = iconMap[agent.icon as keyof typeof iconMap] ?? Bot;
          const route = routeForAgent(agent);
          const status = statusForAgentDisplay(agent, agentStatuses[agent.id]);
          const cardState = status === 'disabled' ? 'planned-agent' : 'active-agent';
          return (
            <button
              className={`agent-card ${cardState}`}
              key={agent.id}
              disabled={!route}
              onClick={() => route && navigate(route)}
            >
              <div className="agent-icon"><Icon size={24} /></div>
              <div>
                <span className="eyebrow">{agentStatusLabel(status)}</span>
                <h2>{agent.name}</h2>
                <p>{agent.description || 'Agent per Manifest eingebunden.'}</p>
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
