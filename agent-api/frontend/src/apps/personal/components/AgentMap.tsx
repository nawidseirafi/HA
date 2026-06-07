import { useCallback, useEffect, useMemo, useState, type MouseEvent } from 'react';
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
  Bell,
  Bot,
  BrainCircuit,
  CalendarCheck,
  CalendarDays,
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
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { api, type AgentManifest, type KnownDashboardRoute, type OrchestratorMapData, type OrchestratorMapNode } from '@shared/api/client';
import type { Route } from '../App';
import { AgentNode } from './AgentNode';
import type { AgentMapNodeData, AgentMapServiceDetail, AgentMapStatus } from '@shared/types/agentMap';

interface Props {
  navigate: (route: Route) => void;
  chrome?: boolean;
  interactive?: boolean;
}

const nodeTypes: NodeTypes = { agentNode: AgentNode };

const dashboardRouteMap: Record<KnownDashboardRoute, Route> = {
  invoiceDashboard: { name: 'invoiceDashboard' },
  mywellnessDashboard: { name: 'mywellnessDashboard' },
  marketDashboard: { name: 'marketDashboard' },
  vacationDashboard: { name: 'vacationDashboard' },
  schedulerDashboard: { name: 'schedulerDashboard' },
};

const iconMap: Record<string, LucideIcon> = {
  Bot,
  BrainCircuit,
  CalendarCheck,
  CalendarDays,
  Bell,
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
  Zap,
};

export function AgentMap({ navigate, chrome = true, interactive = true }: Props) {
  const [selectedService, setSelectedService] = useState<AgentMapServiceDetail | null>(null);
  const [mapData, setMapData] = useState<OrchestratorMapData | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    const load = () => {
      api.orchestratorMap()
        .then((nextMap) => {
          if (!mounted) return;
          setMapData(nextMap);
          setError('');
        })
        .catch((err) => {
          if (!mounted) return;
          setError(err instanceof Error ? err.message : 'Agent Map konnte nicht geladen werden.');
        });
    };

    load();
    const refresh = window.setInterval(load, 15000);
    return () => {
      mounted = false;
      window.clearInterval(refresh);
    };
  }, []);

  const { nodes, edges } = useAgentMapElements(mapData);

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
        <span className="agent-map-hint">{error || 'Zoom und Drag aktiv'}</span>
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

function useAgentMapElements(mapData: OrchestratorMapData | null) {
  return useMemo(() => {
    if (!mapData) return { nodes: [], edges: [] as Edge[] };
    const nodes = mapData.nodes.map((mapNode, index) => agentNodeFromMap(mapNode, index));
    const edges = mapData.edges.map((edge) => ({
      id: edge.id,
      source: edge.from,
      target: edge.to,
      animated: edge.active,
      className: edge.active ? `agent-map-edge active${edge.status === 'running' ? ' running' : ''}` : 'agent-map-edge',
      style: { strokeWidth: edge.status === 'running' ? 2.4 : edge.active ? 2 : 1.6 },
    }));
    return { nodes, edges };
  }, [mapData]);
}

function agentNodeFromMap(mapNode: OrchestratorMapNode, index: number): Node<AgentMapNodeData> {
  return {
    id: mapNode.id,
    type: 'agentNode',
    position: positionForNode(mapNode, index),
    data: {
      id: mapNode.id,
      label: mapNode.label,
      description: mapNode.subtitle || 'Automatisierte Aufgabe.',
      icon: iconMap[mapNode.icon] ?? Zap,
      status: mapNode.status,
      route: routeForDashboard(mapNode.dashboard_route),
      lastRun: formatDate(mapNode.last_run) || 'noch keine Live-Daten',
      nextAction: formatDate(mapNode.next_action) || mapNode.next_action || 'Bereit',
      kind: nodeKind(mapNode),
    },
  };
}

function positionForNode(node: OrchestratorMapNode, index: number) {
  const fixed: Record<string, { x: number; y: number }> = {
    orchestrator: { x: 390, y: 20 },
    scheduler: { x: 180, y: 190 },
    messaging: { x: 600, y: 190 },
    market: { x: -150, y: 380 },
    invoices: { x: 120, y: 380 },
    vacation: { x: 390, y: 380 },
    household: { x: 660, y: 380 },
    mywellness: { x: 930, y: 380 },
    openai: { x: -120, y: 590 },
    database: { x: 330, y: 590 },
    homeassistant: { x: 780, y: 590 },
  };
  if (fixed[node.id]) return fixed[node.id];
  if (node.kind === 'agent') return { x: 20 + (index % 4) * 290, y: 220 + Math.floor(index / 4) * 140 };
  if (node.kind === 'service') return { x: -150 + (index % 3) * 460, y: 430 };
  return { x: 310, y: 20 };
}

function nodeKind(node: OrchestratorMapNode): AgentMapNodeData['kind'] {
  if (node.kind === 'orchestrator') return 'orchestrator';
  if (node.kind === 'platform' || ["scheduler", "messaging", "household"].includes(node.id)) return 'platform';
  if (node.kind === 'agent') return 'agent';
  if (node.id === 'database') return 'database';
  if (node.id === 'openai' || node.id === 'homeassistant') return 'external';
  return 'service';
}

function routeForDashboard(routeName?: string | null): Route | undefined {
  return routeName ? dashboardRouteMap[routeName as KnownDashboardRoute] : undefined;
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
  if (status === 'active') return '#34d399';
  if (status === 'running') return '#4d8dff';
  if (status === 'paused') return '#f59e0b';
  if (status === 'error') return '#fb7185';
  return '#6b7280';
}

export function statusesFromOrchestratorMap(map: OrchestratorMapData): Partial<Record<string, {
  status: AgentMapStatus;
  current_status: AgentMapStatus;
  is_running: boolean;
  enabled: boolean;
  last_run?: string;
  next_action?: string;
}>> {
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

export function statusForAgentDisplay(agent: AgentManifest, live?: { status?: string; current_status?: string; enabled?: boolean; is_running?: boolean; error?: string | null; last_error?: string | null }): AgentMapStatus {
  if (live) return normalizeStatus(live, agent.enabled);
  return normalizeStatus({ status: agent.status, enabled: agent.enabled }, agent.enabled);
}

function normalizeStatus(live: { status?: string; current_status?: string; enabled?: boolean; is_running?: boolean; error?: string | null; last_error?: string | null }, manifestEnabled = true): AgentMapStatus {
  const raw = String(live.status || live.current_status || '').toLowerCase();
  if (live.error || live.last_error || raw.includes('error') || raw.includes('fehler')) return 'error';
  if (live.is_running || raw.includes('running') || raw.includes('läuft') || raw.includes('laeuft')) return 'running';
  if (live.enabled === false || manifestEnabled === false || raw.includes('disabled') || raw === 'aus') return 'disabled';
  if (raw.includes('pause')) return 'paused';
  return 'active';
}
