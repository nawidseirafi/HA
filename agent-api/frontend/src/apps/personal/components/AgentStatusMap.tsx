import { Bell, Bot, CalendarCheck, CalendarDays, Database, Dumbbell, FileText, Heart, Home, HousePlug, LineChart, Mail, Settings2, ShieldCheck, Sparkles, Zap } from 'lucide-react';
import type { ComponentType } from 'react';
import { useEffect, useState } from 'react';
import type { LucideProps } from 'lucide-react';
import { api, type OrchestratorMapData, type OrchestratorMapNode, type WallDashboardData } from '@shared/api/client';

type StatusTone = 'active' | 'running' | 'paused' | 'error' | 'disabled';
type NodeKind = 'orchestrator' | 'agent' | 'platform' | 'service';

type MapNode = {
  id: string;
  label: string;
  eyebrow: string;
  status: StatusTone;
  kind: NodeKind;
  x: number;
  y: number;
  icon: ComponentType<LucideProps>;
  lastRun?: string;
  nextRun?: string;
};

type MapEdge = {
  id: string;
  from: string;
  to: string;
  active: boolean;
  tone: StatusTone;
  variant?: 'primary' | 'secondary';
};

const statusLabel: Record<StatusTone, string> = {
  active: 'Aktiv',
  running: 'Läuft',
  paused: 'Pausiert',
  error: 'Fehler',
  disabled: 'Aus',
};

const iconMap: Record<string, ComponentType<LucideProps>> = {
  Bot,
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

const platformNodeIds = new Set(['scheduler', 'messaging', 'household']);

export function AgentStatusMap({ data }: { data: WallDashboardData }) {
  const [orchestratorMap, setOrchestratorMap] = useState<OrchestratorMapData | null>(null);

  useEffect(() => {
    let mounted = true;
    api.orchestratorMap()
      .then((nextMap) => mounted && setOrchestratorMap(nextMap))
      .catch(() => undefined);
    return () => {
      mounted = false;
    };
  }, []);

  const fallbackAgents = buildAgentNodes(data);
  const nodes = orchestratorMap ? nodesFromOrchestratorMap(orchestratorMap.nodes) : buildNodes(data, fallbackAgents);
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const edges = orchestratorMap ? edgesFromOrchestratorMap(orchestratorMap.edges) : buildEdges(fallbackAgents);
  const summary = orchestratorMap ? {
    active: orchestratorMap.summary.active,
    paused: orchestratorMap.summary.paused,
    errors: orchestratorMap.summary.errors,
    lastRun: orchestratorMap.summary.last_activity,
    nextRun: orchestratorMap.summary.next_activity,
  } : buildSummary(fallbackAgents);

  return (
    <section className="agent-status-map" aria-label="Agenten Live-Systemübersicht">
      <div className="agent-status-summary">
        <div>
          <span>Agent Summary</span>
          <strong>{summary.active} Agenten aktiv</strong>
          <small>{summary.paused} pausiert · {summary.errors} Fehler</small>
        </div>
        <div>
          <span>Letzte Aktivität</span>
          <strong>{summary.lastRun}</strong>
        </div>
        <div>
          <span>Nächste Aktivität</span>
          <strong>{summary.nextRun}</strong>
        </div>
      </div>

      <div className="agent-status-map-canvas" aria-hidden="true">
        <div className="agent-status-map-stage">
          <svg className="agent-status-map-lines" viewBox="0 0 1280 760" role="presentation">
            {edges.map((edge) => {
              const from = nodeById.get(edge.from);
              const to = nodeById.get(edge.to);
              if (!from || !to) return null;
              const path = curvePath(from, to);
              return (
                <g key={edge.id} className={`agent-status-edge ${edge.variant ?? 'primary'} tone-${edge.tone} ${edge.active ? 'active' : ''}`}>
                  <path d={path} />
              </g>
              );
            })}
          </svg>

          {nodes.map((node) => {
            const Icon = node.icon;
            return (
              <article
                key={node.id}
                className={`agent-status-node ${node.kind} status-${node.status}`}
                style={{ left: node.x, top: node.y }}
              >
                <div className="agent-status-node-icon"><Icon size={22} /></div>
                <div className="agent-status-node-copy">
                  <strong>{node.label}</strong>
                  <span>{node.eyebrow}</span>
                </div>
                <i className="agent-status-dot" aria-label={`Status ${statusLabel[node.status]}`} />
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function buildNodes(data: WallDashboardData, agents: MapNode[]): MapNode[] {
  return [
    {
      id: 'orchestrator',
      label: 'RoboterSteve',
      eyebrow: 'Orchestrator',
      status: hasRunningAgent(agents) ? 'running' : 'active',
      kind: 'orchestrator',
      x: 640,
      y: 310,
      icon: Bot,
    },
    ...agents,
    {
      id: 'homeassistant',
      label: 'Home Assistant',
      eyebrow: data.home_assistant.configured ? 'Smart Home Bridge' : 'Nicht verbunden',
      status: data.home_assistant.configured ? 'active' : 'disabled',
      kind: 'service',
      x: 260,
      y: 520,
      icon: HousePlug,
    },
    {
      id: 'openai',
      label: 'OpenAI',
      eyebrow: 'Modelle & Verarbeitung',
      status: 'active',
      kind: 'service',
      x: 640,
      y: 520,
      icon: Sparkles,
    },
    {
      id: 'database',
      label: 'Database',
      eyebrow: 'Daten & Historie',
      status: 'active',
      kind: 'service',
      x: 1020,
      y: 520,
      icon: Database,
    },
  ];
}

function nodesFromOrchestratorMap(nodes: OrchestratorMapNode[]): MapNode[] {
  return nodes.map((node, index) => {
    const position = positionForNode(node, index);
    return {
      id: node.id,
      label: node.label,
      eyebrow: node.subtitle,
      status: node.status,
      kind: platformNodeIds.has(node.id) ? 'platform' : node.kind,
      x: position.x,
      y: position.y,
      icon: iconMap[node.icon] ?? Zap,
      lastRun: node.last_run,
      nextRun: node.next_action,
    };
  });
}

function positionForNode(node: OrchestratorMapNode, index: number) {
  const fixed: Record<string, { x: number; y: number }> = {
    orchestrator: { x: 640, y: 70 },
    scheduler: { x: 430, y: 265 },
    messaging: { x: 850, y: 265 },
    market: { x: 110, y: 470 },
    invoices: { x: 360, y: 470 },
    vacation: { x: 610, y: 470 },
    household: { x: 860, y: 470 },
    mywellness: { x: 1110, y: 470 },
    homeassistant: { x: 260, y: 660 },
    openai: { x: 640, y: 660 },
    database: { x: 1020, y: 660 },
  };
  if (fixed[node.id]) return fixed[node.id];
  if (node.kind === 'agent') return { x: 170 + (index % 4) * 310, y: 115 + Math.floor(index / 4) * 92 };
  if (node.kind === 'service') return { x: 260 + (index % 3) * 380, y: 520 };
  return { x: 640, y: 310 };
}

function buildAgentNodes(data: WallDashboardData): MapNode[] {
  const rawEntries = Object.entries(data.agents as Record<string, Record<string, unknown> | undefined>);
  const preferredOrder = ['invoices', 'mywellness', 'market', 'vacation'];
  const entries = [
    ...preferredOrder
      .filter((id) => rawEntries.some(([entryId]) => entryId === id))
      .map((id) => [id, rawEntries.find(([entryId]) => entryId === id)?.[1]] as [string, Record<string, unknown> | undefined]),
    ...rawEntries.filter(([id]) => !preferredOrder.includes(id)),
  ];
  const agentCount = Math.max(entries.length, 1);
  const preferredPositions = [
    { x: 170, y: 115 },
    { x: 485, y: 115 },
    { x: 795, y: 115 },
    { x: 1110, y: 115 },
    { x: 325, y: 205 },
    { x: 955, y: 205 },
  ];

  return entries.map(([id, raw], index) => {
    const fallbackAngle = -Math.PI / 2 + (index / agentCount) * Math.PI * 2;
    const fallback = {
      x: Math.round(640 + Math.cos(fallbackAngle) * 450),
      y: Math.round(210 + Math.sin(fallbackAngle) * 95),
    };
    const position = preferredPositions[index] ?? fallback;
    return {
      id,
      label: titleFromId(id),
      eyebrow: 'Automatisierte Aufgabe',
      status: statusFromRaw(id, raw),
      kind: 'agent',
      x: position.x,
      y: position.y,
      icon: Zap,
      lastRun: lastRunFromRaw(raw),
      nextRun: nextRunFromRaw(raw),
    };
  });
}

function buildEdges(agents: MapNode[]): MapEdge[] {
  const household = agents.find((agent) => agent.id === 'vacation');
  const aiAgents = agents.filter((agent) => ['invoices', 'mywellness', 'market'].includes(agent.id));
  const storageAgents = agents.filter((agent) => ['invoices', 'mywellness', 'market', 'vacation'].includes(agent.id));

  return [
    ...agents.map((agent) => ({
      id: `orchestrator-${agent.id}`,
      from: 'orchestrator',
      to: agent.id,
      active: isLiveStatus(agent.status),
      tone: agent.status,
      variant: 'primary' as const,
    })),
    ...storageAgents.map((agent) => ({
      id: `${agent.id}-database`,
      from: agent.id,
      to: 'database',
      active: isLiveStatus(agent.status),
      tone: agent.status,
      variant: 'secondary' as const,
    })),
    ...(household ? [{
      id: `${household.id}-homeassistant`,
      from: household.id,
      to: 'homeassistant',
      active: isLiveStatus(household.status),
      tone: household.status,
      variant: 'secondary' as const,
    }] : []),
    ...aiAgents.map((agent) => ({
      id: `${agent.id}-openai`,
      from: agent.id,
      to: 'openai',
      active: isLiveStatus(agent.status),
      tone: agent.status,
      variant: 'secondary' as const,
    })),
  ];
}

function edgesFromOrchestratorMap(edges: OrchestratorMapData['edges']): MapEdge[] {
  return edges.map((edge) => ({
    id: edge.id,
    from: edge.from,
    to: edge.to,
    active: edge.active,
    tone: edge.status,
    variant: edge.kind,
  }));
}

function isLiveStatus(status: StatusTone) {
  return status === 'active' || status === 'running';
}

function curvePath(from: MapNode, to: MapNode) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const vertical = Math.abs(dy) >= Math.abs(dx);
  const c1x = vertical ? from.x : from.x + dx * 0.45;
  const c1y = vertical ? from.y + dy * 0.42 : from.y + dy * 0.22;
  const c2x = vertical ? to.x : to.x - dx * 0.45;
  const c2y = vertical ? to.y - dy * 0.42 : to.y - dy * 0.22;
  return `M ${from.x} ${from.y} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${to.x} ${to.y}`;
}

function buildSummary(agents: MapNode[]) {
  const active = agents.filter((agent) => agent.status === 'active' || agent.status === 'running').length;
  const paused = agents.filter((agent) => agent.status === 'paused').length;
  const errors = agents.filter((agent) => agent.status === 'error').length;
  const last = agents
    .map((agent) => ({ label: agent.label, value: agent.lastRun, date: parseDate(agent.lastRun) }))
    .filter((item): item is { label: string; value: string; date: Date } => Boolean(item.value && item.date))
    .sort((a, b) => b.date.getTime() - a.date.getTime())[0];
  const next = agents
    .map((agent) => ({ label: agent.label, value: agent.nextRun, date: parseDate(agent.nextRun) }))
    .filter((item): item is { label: string; value: string; date: Date } => Boolean(item.value && item.date))
    .sort((a, b) => a.date.getTime() - b.date.getTime())[0];

  return {
    active,
    paused,
    errors,
    lastRun: last ? `${last.label} · ${formatWallTime(last.date)}` : 'Noch keine Live-Daten',
    nextRun: next ? `${next.label} · ${formatWallTime(next.date)}` : 'Nicht geplant',
  };
}

function statusFromRaw(id: string, raw?: Record<string, unknown>): StatusTone {
  const status = String(raw?.status ?? raw?.current_status ?? raw?.last_status ?? '').toLowerCase();
  const error = raw?.error || raw?.last_error;
  if (error || status.includes('error') || status.includes('fehler')) return 'error';
  if (raw?.is_running === true) return 'running';
  if (raw?.enabled === false) return 'paused';
  if (status.includes('running') || status.includes('läuft') || status.includes('laeuft')) return 'running';
  if (status.includes('paused') || status.includes('pause')) return 'paused';
  if (status.includes('disabled') || status.includes('aus')) return 'disabled';
  if (status === 'ok' || status.includes('idle')) return 'active';
  return 'active';
}

function hasRunningAgent(agents: MapNode[]) {
  return agents.some((agent) => agent.status === 'running');
}

function lastRunFromRaw(raw?: Record<string, unknown>) {
  return stringValue(raw?.last_successful_run) || stringValue(raw?.last_finished_at) || stringValue(raw?.last_started_at);
}

function nextRunFromRaw(raw?: Record<string, unknown>) {
  const direct = stringValue(raw?.next_scheduled_run);
  if (direct) return direct;
  const schedule = Array.isArray(raw?.schedule) ? raw?.schedule : [];
  return typeof schedule[0] === 'string' ? schedule[0] : '';
}

function stringValue(value: unknown) {
  return typeof value === 'string' && value.trim() ? value : '';
}

function parseDate(value?: string) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatWallTime(date: Date) {
  return new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' }).format(date);
}

function titleFromId(id: string) {
  return id
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}
