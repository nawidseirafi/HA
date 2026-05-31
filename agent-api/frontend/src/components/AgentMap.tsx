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
import {
  Bot,
  BrainCircuit,
  CalendarCheck,
  Database,
  Dumbbell,
  FileText,
  Heart,
  Home,
  HousePlug,
  LineChart,
  Mail,
  Settings2,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import type { AgentManifest, AgentStatus, KnownDashboardRoute, OrchestratorMapData } from '../api/client';
import type { Route } from '../App';
import { AgentNode } from './AgentNode';
import type { AgentMapNodeData, AgentMapServiceDetail, AgentMapStatus } from '../types/agentMap';

type AgentMapStatusPayload = Partial<AgentStatus> & {
  status?: string;
  current_status?: string;
  error?: string | null;
  last_run?: string;
  next_action?: string;
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

const manifestIconMap: Record<string, LucideIcon> = {
  Bot,
  CalendarCheck,
  Database,
  Dumbbell,
  FileText,
  Heart,
  Hearth: Heart,
  Home,
  HousePlug,
  LineChart,
  Mail,
  Settings2,
  ShieldCheck,
  Sparkles,
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
    const knownAgents = ['invoices', 'mywellness', 'market', 'vacation'];
    const manifestById = new Map(agents.map((agent) => [agent.id, agent]));
    const agentIds = [
      ...knownAgents.filter((id) => manifestById.has(id) || statuses[id]),
      ...agents.map((agent) => agent.id).filter((id) => !knownAgents.includes(id)),
    ];
    const agentNodes = agentIds.map((id, index) => {
      const manifest = manifestById.get(id);
      const status = statusFromAgent(id, manifest, statuses[id]);
      return agentNode(id, {
        label: manifest?.name || titleFromId(id),
        description: manifest?.description || 'Automatisierte Aufgabe.',
        icon: iconForAgent(manifest) ?? Bot,
        status,
        route: routeForAgent(manifest),
        position: agentPosition(index, agentIds.length),
        lastRun: formatLastRun(statuses[id]),
        nextAction: formatNextAction(statuses[id], id),
      });
    });
    const hasVacationAgent = agentIds.includes('vacation');

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
      ...(!hasVacationAgent ? [agentNode('household', {
        label: 'Household Service',
        description: 'Bündelt Haushaltslogik wie Abfall, Reminder und Wohnungsstatus.',
        icon: Home,
        status: statusFromLive(statuses.vacation || statuses.household, 'ok'),
        position: { x: 890, y: 220 },
        lastRun: 'Fallback aktiv',
        nextAction: 'Home Assistant synchronisieren',
        kind: 'service',
      })] : []),
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
      ...agentIds.map((id) => link('orchestrator', id, isActive(id, nodes), isRunning(id, statuses))),
      ...agentIds
        .filter((id) => ['invoices', 'mywellness', 'market', 'vacation'].includes(id))
        .map((id) => link(id, 'database', isActive(id, nodes), isRunning(id, statuses))),
      ...(!hasVacationAgent ? [link('orchestrator', 'household', true, false), link('household', 'database', true, false)] : []),
      ...agentIds
        .filter((id) => ['mywellness', 'vacation'].includes(id))
        .map((id) => link(id, 'homeassistant', isActive(id, nodes), isRunning(id, statuses))),
      ...(!hasVacationAgent ? [link('household', 'homeassistant', true, false)] : []),
      ...agentIds
        .filter((id) => ['invoices', 'mywellness', 'market'].includes(id))
        .map((id) => link(id, 'openai', isActive(id, nodes), isRunning(id, statuses))),
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
  const fallback = agent?.enabled === false ? 'disabled' : statusFromManifest(agent);
  if (live) return statusFromLive(live, fallback);
  if (agent?.enabled === false) return 'disabled';
  if (agent?.status?.toLowerCase().includes('paused')) return 'paused';
  return fallback;
}

function statusFromManifest(agent?: AgentManifest): AgentMapStatus {
  const raw = String(agent?.status || '').toLowerCase();
  if (raw.includes('error') || raw.includes('fehler')) return 'error';
  if (raw.includes('running') || raw.includes('läuft') || raw.includes('laeuft')) return 'running';
  if (raw.includes('paused') || raw.includes('pause') || raw.includes('idle') || raw.includes('draft')) return 'paused';
  if (raw.includes('disabled') || raw.includes('aus')) return 'disabled';
  return 'active';
}

function statusFromLive(live: AgentMapStatusPayload | undefined, fallback: AgentMapStatus): AgentMapStatus {
  const raw = String(live?.status || live?.current_status || live?.last_status || '').toLowerCase();
  if (live?.last_error || live?.error || raw.includes('error') || raw.includes('fehler')) return 'error';
  if (live?.is_running || raw.includes('running') || raw.includes('läuft') || raw.includes('laeuft')) return 'running';
  if (live?.enabled === false) return 'disabled';
  if (raw.includes('paused') || raw.includes('pause') || raw.includes('idle') || raw.includes('draft')) return 'paused';
  if (raw.includes('disabled') || raw.includes('aus')) return 'disabled';
  if (raw.includes('active') || raw === 'ok') return 'active';
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
  return formatDate(status?.last_run || status?.last_successful_run || status?.last_finished_at || status?.last_started_at) || 'noch keine Live-Daten';
}

function formatNextAction(status: AgentMapStatusPayload | undefined, agentId: string) {
  if (status?.next_action) return formatDate(status.next_action) || status.next_action;
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

export function statusesFromOrchestratorMap(map: OrchestratorMapData): Partial<Record<string, AgentMapStatusPayload>> {
  return Object.fromEntries(map.nodes.map((node) => [node.id, {
    status: node.status,
    current_status: node.status,
    is_running: node.status === 'running',
    enabled: node.status !== 'disabled',
    last_run: node.last_run,
    next_action: node.next_action,
  }]));
}

export function agentStatusLabel(status: AgentMapStatus) {
  if (status === 'running') return 'Läuft';
  if (status === 'paused') return 'Pausiert';
  if (status === 'error') return 'Fehler';
  if (status === 'disabled') return 'Aus';
  return 'Aktiv';
}

export function statusForAgentDisplay(agent: AgentManifest, live?: AgentMapStatusPayload): AgentMapStatus {
  return statusFromAgent(agent.id, agent, live);
}

function agentPosition(index: number, count: number) {
  if (count <= 3) return { x: 20 + index * 290, y: 220 };
  return { x: -110 + index * 270, y: 220 };
}

function iconForAgent(agent?: AgentManifest) {
  if (!agent) return null;
  return manifestIconMap[agent.icon] ?? null;
}

function titleFromId(id: string) {
  return id
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}
