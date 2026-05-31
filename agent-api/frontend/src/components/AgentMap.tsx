import { useCallback, useMemo, useState, type MouseEvent } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Edge,
  type Node,
  type NodeTypes,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Bot, BrainCircuit, Database, FileText, Home, HousePlug, LineChart, Sparkles } from 'lucide-react';
import type { AgentManifest, AgentStatus, KnownDashboardRoute } from '../api/client';
import type { Route } from '../App';
import { AgentNode } from './AgentNode';
import type { AgentMapNodeData, AgentMapServiceDetail, AgentMapStatus } from '../types/agentMap';

type AgentMapStatusPayload = Partial<AgentStatus> & {
  status?: string;
  current_status?: string;
  error?: string | null;
};

interface Props {
  agents: AgentManifest[];
  statuses?: Partial<Record<string, AgentMapStatusPayload>>;
  navigate: (route: Route) => void;
  chrome?: boolean;
  interactive?: boolean;
}

const nodeTypes: NodeTypes = { agentNode: AgentNode };

const dashboardRouteMap: Record<KnownDashboardRoute, Route> = {
  invoiceDashboard: { name: 'invoiceDashboard' },
  mywellnessDashboard: { name: 'mywellnessDashboard' },
  marketDashboard: { name: 'marketDashboard' },
};

const fallbackAgentInfo: Record<string, Pick<AgentMapNodeData, 'label' | 'description' | 'icon' | 'status'>> = {
  invoices: {
    label: 'Invoice Agent',
    description: 'Importiert, analysiert und archiviert Rechnungen und Belege.',
    icon: FileText,
    status: 'ok',
  },
  mywellness: {
    label: 'MyWellness Agent',
    description: 'Überwacht Kurse, Buchungen und Gesundheitsdaten.',
    icon: Bot,
    status: 'running',
  },
  market: {
    label: 'Market Agent',
    description: 'Erstellt Marktanalysen, Reports und Signale.',
    icon: LineChart,
    status: 'paused',
  },
};

export function AgentMap({ agents, statuses = {}, navigate, chrome = true, interactive = true }: Props) {
  const [selectedService, setSelectedService] = useState<AgentMapServiceDetail | null>(null);
  const { nodes, edges } = useAgentMapElements(agents, statuses);

  const onNodeClick = useCallback((_: MouseEvent, node: Node<AgentMapNodeData>) => {
    if (!interactive) return;
    if (node.data.route) {
      navigate(node.data.route);
      return;
    }

    setSelectedService({
      id: node.data.id,
      label: node.data.label,
      status: node.data.status,
      description: node.data.description,
      lastRun: node.data.lastRun,
      nextAction: node.data.nextAction,
    });
  }, [interactive, navigate]);

  return (
    <section className={`agent-map-panel ${!chrome ? 'agent-map-panel-map-only' : ''}`}>
      {chrome && <div className="section-title agent-map-title">
        <div>
          <span className="eyebrow">Agent Map</span>
          <h2>Systemübersicht</h2>
        </div>
        <span className="agent-map-hint">Zoom und Drag aktiv</span>
      </div>}

      <div className="agent-map-shell">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          fitView
          fitViewOptions={{ padding: 0.18 }}
          minZoom={0.45}
          maxZoom={1.6}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={interactive}
          panOnDrag={interactive}
          zoomOnScroll={interactive}
          zoomOnPinch={interactive}
          zoomOnDoubleClick={interactive}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="rgba(153, 168, 195, 0.16)" gap={24} size={1} />
          {chrome && <Controls showInteractive={false} />}
          {chrome && <MiniMap
            pannable
            zoomable
            nodeStrokeWidth={3}
            maskColor="rgba(7, 17, 31, 0.64)"
            nodeColor={(node) => statusColor((node.data as AgentMapNodeData).status)}
          />}
        </ReactFlow>

        {chrome && <aside className="agent-map-detail">
          {selectedService ? (
            <>
              <span className={`agent-map-badge status-${selectedService.status}`}>{selectedService.status}</span>
              <h3>{selectedService.label}</h3>
              <p>{selectedService.description}</p>
              <dl>
                <div>
                  <dt>Letzter Lauf</dt>
                  <dd>{selectedService.lastRun}</dd>
                </div>
                <div>
                  <dt>Nächste Aktion</dt>
                  <dd>{selectedService.nextAction}</dd>
                </div>
              </dl>
            </>
          ) : (
            <>
              <span className="agent-map-badge status-active">ready</span>
              <h3>Node auswählen</h3>
              <p>Agenten öffnen ihr Dashboard. Services zeigen hier ihre Systemdetails.</p>
            </>
          )}
        </aside>}
      </div>
    </section>
  );
}

function useAgentMapElements(agents: AgentManifest[], statuses: Partial<Record<string, AgentMapStatusPayload>>) {
  return useMemo(() => {
    const knownAgents = ['invoices', 'mywellness', 'market'];
    const manifestById = new Map(agents.map((agent) => [agent.id, agent]));
    const agentNodes = knownAgents.map((id, index) => {
      const manifest = manifestById.get(id);
      const fallback = fallbackAgentInfo[id];
      const status = statusFromAgent(id, manifest, statuses[id]);
      return agentNode(id, {
        label: fallback.label,
        description: manifest?.description || fallback.description,
        icon: fallback.icon,
        status,
        route: routeForAgent(manifest),
        position: { x: 20 + index * 290, y: 220 },
        lastRun: formatLastRun(statuses[id]),
        nextAction: formatNextAction(statuses[id], id),
      });
    });

    const nodes: Node<AgentMapNodeData>[] = [
      agentNode('orchestrator', {
        label: 'Orchestrator',
        description: 'Koordiniert Agenten, Services und wiederkehrende Aktionen.',
        icon: BrainCircuit,
        status: 'active',
        position: { x: 310, y: 20 },
        lastRun: 'kontinuierlich aktiv',
        nextAction: 'Agenten koordinieren',
        kind: 'orchestrator',
      }),
      ...agentNodes,
      agentNode('household', {
        label: 'Household Service',
        description: 'Bündelt Haushaltslogik wie Abfall, Reminder und Wohnungsstatus.',
        icon: Home,
        status: statusFromLive(statuses.vacation || statuses.household, 'ok'),
        position: { x: 890, y: 220 },
        lastRun: 'Fallback aktiv',
        nextAction: 'Home Assistant synchronisieren',
        kind: 'service',
      }),
      agentNode('database', {
        label: 'SQLite / Database',
        description: 'Persistiert Agentenstatus, Belege, Kurse und Marktberichte.',
        icon: Database,
        status: 'ok',
        position: { x: 310, y: 430 },
        lastRun: 'laufend verfügbar',
        nextAction: 'Schreibzugriffe entgegennehmen',
        kind: 'database',
      }),
      agentNode('homeassistant', {
        label: 'Home Assistant',
        description: 'Externe Smart-Home-Integration für Räume, Geräte und Sensordaten.',
        icon: HousePlug,
        status: 'ok',
        position: { x: 760, y: 430 },
        lastRun: 'Fallback aktiv',
        nextAction: 'Entitäten lesen',
        kind: 'external',
      }),
      agentNode('openai', {
        label: 'OpenAI',
        description: 'KI-Auswertung für Belege, Wellness-Kontext und Marktberichte.',
        icon: Sparkles,
        status: 'ok',
        position: { x: -150, y: 430 },
        lastRun: 'bei Bedarf',
        nextAction: 'Analyse ausführen',
        kind: 'external',
      }),
    ];

    const edges: Edge[] = [
      link('orchestrator', 'invoices', isActive('invoices', nodes), isRunning('invoices', statuses)),
      link('orchestrator', 'mywellness', isActive('mywellness', nodes), isRunning('mywellness', statuses)),
      link('orchestrator', 'market', isActive('market', nodes), isRunning('market', statuses)),
      link('orchestrator', 'household', true, false),
      link('invoices', 'database', isActive('invoices', nodes), isRunning('invoices', statuses)),
      link('mywellness', 'database', isActive('mywellness', nodes), isRunning('mywellness', statuses)),
      link('market', 'database', isActive('market', nodes), isRunning('market', statuses)),
      link('household', 'database', true, false),
      link('mywellness', 'homeassistant', isActive('mywellness', nodes), isRunning('mywellness', statuses)),
      link('household', 'homeassistant', true, false),
      link('invoices', 'openai', isActive('invoices', nodes), isRunning('invoices', statuses)),
      link('mywellness', 'openai', isActive('mywellness', nodes), isRunning('mywellness', statuses)),
      link('market', 'openai', isActive('market', nodes), isRunning('market', statuses)),
    ];

    return { nodes, edges };
  }, [agents, statuses]);
}

function agentNode(
  id: string,
  data: Omit<AgentMapNodeData, 'id' | 'kind'> & { kind?: AgentMapNodeData['kind']; position: { x: number; y: number } },
): Node<AgentMapNodeData> {
  const { position, ...nodeData } = data;
  return {
    id,
    type: 'agentNode',
    position,
    data: { kind: 'agent', ...nodeData, id },
  };
}

function link(source: string, target: string, active: boolean, running: boolean): Edge {
  return {
    id: `${source}-${target}`,
    source,
    target,
    animated: active,
    className: active ? `agent-map-edge active${running ? ' running' : ''}` : 'agent-map-edge',
    style: { strokeWidth: running ? 2.4 : active ? 2 : 1.6 },
  };
}

function routeForAgent(agent?: AgentManifest): Route | undefined {
  const routeName = agent?.dashboard_route as KnownDashboardRoute | null | undefined;
  return routeName ? dashboardRouteMap[routeName] : undefined;
}

function statusFromAgent(id: string, agent?: AgentManifest, live?: AgentMapStatusPayload): AgentMapStatus {
  const fallback = fallbackAgentInfo[id]?.status ?? 'ok';
  if (live) return statusFromLive(live, fallback);
  if (agent?.enabled === false) return 'disabled';
  if (agent?.status?.toLowerCase().includes('paused')) return 'paused';
  return fallback;
}

function statusFromLive(live: AgentMapStatusPayload | undefined, fallback: AgentMapStatus): AgentMapStatus {
  const raw = String(live?.status || live?.current_status || live?.last_status || '').toLowerCase();
  if (live?.last_error || live?.error || raw.includes('error') || raw.includes('fehler')) return 'error';
  if (live?.is_running || raw.includes('running') || raw.includes('läuft') || raw.includes('laeuft')) return 'running';
  if (live?.enabled === false) return 'disabled';
  if (raw.includes('paused') || raw.includes('pause') || raw.includes('idle') || raw.includes('draft')) return 'paused';
  if (raw.includes('disabled') || raw.includes('aus')) return 'disabled';
  if (raw.includes('active') || raw === 'ok') return 'ok';
  return fallback;
}

function isRunning(id: string, statuses: Partial<Record<string, AgentMapStatusPayload>>) {
  return Boolean(statuses[id]?.is_running);
}

function isActive(id: string, nodes: Node<AgentMapNodeData>[]) {
  const status = nodes.find((node) => node.id === id)?.data.status;
  return status === 'active' || status === 'ok' || status === 'running';
}

function formatLastRun(status?: AgentMapStatusPayload) {
  return formatDate(status?.last_successful_run || status?.last_finished_at || status?.last_started_at) || 'noch keine Live-Daten';
}

function formatNextAction(status: AgentMapStatusPayload | undefined, agentId: string) {
  if (status?.next_scheduled_action === 'prepare') return 'Kurse vorbereiten';
  if (status?.next_scheduled_action === 'book') return 'Kurse buchen';
  if (status?.next_scheduled_run) return formatDate(status.next_scheduled_run) || 'geplant';
  if (agentId === 'invoices') return 'Belege importieren';
  if (agentId === 'market') return 'Watchlist analysieren';
  return 'Bereit';
}

function formatDate(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function statusColor(status: AgentMapStatus) {
  if (status === 'active' || status === 'ok') return '#34d399';
  if (status === 'running') return '#4d8dff';
  if (status === 'paused') return '#f59e0b';
  if (status === 'error') return '#fb7185';
  return '#6b7280';
}
