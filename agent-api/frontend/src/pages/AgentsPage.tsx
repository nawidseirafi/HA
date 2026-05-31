import { useEffect, useState } from 'react';
import { Bot, CalendarCheck, Dumbbell, FileText, Home, LineChart, Mail, Settings2, ShieldCheck } from 'lucide-react';
import { api, type AgentManifest, type AgentStatus, type KnownDashboardRoute } from '../api/client';
import type { Route } from '../App';
import { AgentMap } from '../components/AgentMap';

interface Props {
  navigate: (route: Route) => void;
}

const iconMap = {
  Bot,
  CalendarCheck,
  Dumbbell,
  FileText,
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
  const [agentStatuses, setAgentStatuses] = useState<Partial<Record<string, AgentStatus>>>({});
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;

    api.agents()
      .then((nextAgents) => mounted && setAgents(nextAgents))
      .catch((err) => mounted && setError(err instanceof Error ? err.message : 'Agenten konnten nicht geladen werden.'));

    api.mywellnessStatus()
      .then((status) => mounted && setAgentStatuses((current) => ({ ...current, mywellness: status })))
      .catch(() => undefined);

    api.invoiceAgentStatus()
      .then((status) => mounted && setAgentStatuses((current) => ({ ...current, invoices: status })))
      .catch(() => undefined);

    return () => {
      mounted = false;
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

      <AgentMap agents={agents} statuses={agentStatuses} navigate={navigate} />

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
