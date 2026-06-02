import { useEffect, useState } from 'react';
import { Bot, CalendarCheck, Dumbbell, FileText, Heart, Home, LineChart, Mail, Settings2, ShieldCheck } from 'lucide-react';
import { api, type AgentControlAction, type AgentManifest, type KnownDashboardRoute, type OrchestratorMapData } from '../api/client';
import type { Route } from '../App';
import { AgentMap, agentStatusLabel, statusForAgentDisplay, statusesFromOrchestratorMap } from '../components/AgentMap';

interface Props {
  navigate: (route: Route) => void;
  variant?: 'overview' | 'agents';
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
  vacationDashboard: { name: 'vacationDashboard' },
};

export function AgentsPage({ navigate, variant = 'overview' }: Props) {
  const greeting = getGreeting();
  const [agents, setAgents] = useState<AgentManifest[]>([]);
  const [mapData, setMapData] = useState<OrchestratorMapData | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<ReturnType<typeof statusesFromOrchestratorMap>>({});
  const [controlBusy, setControlBusy] = useState('');
  const [controlMessage, setControlMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    let refresh: number | null = null;

    api.agents()
      .then((nextAgents) => mounted && setAgents(nextAgents))
      .catch((err) => mounted && setError(err instanceof Error ? err.message : 'Agenten konnten nicht geladen werden.'));

    const loadStatuses = () => {
      api.orchestratorMap()
        .then((map) => {
          if (!mounted) return;
          setMapData(map);
          setAgentStatuses(statusesFromOrchestratorMap(map));
        })
        .catch(() => undefined);
    };
    loadStatuses();
    refresh = window.setInterval(loadStatuses, 15000);

    return () => {
      mounted = false;
      if (refresh) window.clearInterval(refresh);
    };
  }, []);

  const refreshMap = async () => {
    const map = await api.orchestratorMap();
    setMapData(map);
    setAgentStatuses(statusesFromOrchestratorMap(map));
  };

  const executeControl = async (agentId: string, action: AgentControlAction) => {
    setControlBusy(`${agentId}:${action}`);
    setControlMessage('');
    try {
      const result = await api.executeAgentControl(agentId, action);
      setControlMessage(result.message || `${agentId}: ${action} ausgefuehrt.`);
      await refreshMap();
    } catch (err) {
      setControlMessage(err instanceof Error ? err.message : `${agentId}: ${action} fehlgeschlagen.`);
    } finally {
      setControlBusy('');
    }
  };

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Agent Console</span>
          <h1>{variant === 'agents' ? 'Agenten' : `${greeting}, Nawid`}</h1>
          <p>
            {variant === 'agents'
              ? 'Alle lokalen Agenten mit Status, Dashboard-Zugriff und gemeinsamem Control-Vertrag.'
              : 'Systemübersicht der lokalen Agenten. Wähle einen Agenten für Details oder nutze die Map zur Orientierung.'}
          </p>
        </div>
      </header>
      {error && <section className="panel error-panel">{error}</section>}
      {controlMessage && <section className="panel agent-note"><Bot size={20} /><span>{controlMessage}</span></section>}

      {variant === 'overview' && <AgentMap navigate={navigate} />}

      <section className="agent-grid">
        {agents.map((agent) => {
          const Icon = iconMap[agent.icon as keyof typeof iconMap] ?? Bot;
          const route = routeForAgent(agent);
          const status = statusForAgentDisplay(agent, agentStatuses[agent.id]);
          const control = mapData?.nodes.find((node) => node.id === agent.id)?.control;
          const actions = control?.actions ?? [];
          const cardState = status === 'disabled' ? 'planned-agent' : 'active-agent';
          return (
            <article
              className={`agent-card ${cardState} ${route ? 'clickable' : ''}`}
              key={agent.id}
              role={route ? 'button' : undefined}
              tabIndex={route ? 0 : undefined}
              onClick={() => route && navigate(route)}
              onKeyDown={(event) => {
                if (!route || (event.key !== 'Enter' && event.key !== ' ')) return;
                event.preventDefault();
                navigate(route);
              }}
            >
              <div className="agent-icon"><Icon size={24} /></div>
              <div>
                <span className="eyebrow">{agentStatusLabel(status)}</span>
                <h2>{agent.name}</h2>
                <p>{agent.description || 'Agent per Manifest eingebunden.'}</p>
                <div className="agent-card-actions" onClick={(event) => event.stopPropagation()}>
                  {control?.supported && actionForRun(actions) && (
                    <button
                      className="button"
                      disabled={controlBusy === `${agent.id}:${actionForRun(actions)}`}
                      onClick={() => executeControl(agent.id, actionForRun(actions)!)}
                    >
                      {actionForRun(actions) === 'start' ? 'Start' : 'Run'}
                    </button>
                  )}
                  {control?.supported && actions.includes('stop') && (
                    <button
                      className="button secondary"
                      disabled={controlBusy === `${agent.id}:stop`}
                      onClick={() => executeControl(agent.id, 'stop')}
                    >
                      Stop
                    </button>
                  )}
                  {control?.supported && actions.includes(status === 'disabled' ? 'enable' : 'disable') && (
                    <button
                      className="button secondary"
                      disabled={controlBusy === `${agent.id}:${status === 'disabled' ? 'enable' : 'disable'}`}
                      onClick={() => executeControl(agent.id, status === 'disabled' ? 'enable' : 'disable')}
                    >
                      {status === 'disabled' ? 'Enable' : 'Disable'}
                    </button>
                  )}
                </div>
              </div>
            </article>
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

function actionForRun(actions: AgentControlAction[]) {
  if (actions.includes('start')) return 'start';
  if (actions.includes('run')) return 'run';
  return null;
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
