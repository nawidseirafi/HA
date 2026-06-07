import type { NodeProps } from 'reactflow';
import { Handle, Position } from 'reactflow';
import type { AgentMapNodeData } from '@shared/types/agentMap';

export function AgentNode({ data, selected }: NodeProps<AgentMapNodeData>) {
  const Icon = data.icon;

  return (
    <div
      className={`agent-map-node agent-map-node-${data.kind} status-${data.status}${selected ? ' selected' : ''}`}
      title={`${data.label}\nStatus: ${data.status}\nLetzter Lauf: ${data.lastRun}\nNächste Aktion: ${data.nextAction}\n${data.description}`}
    >
      <Handle className="agent-map-handle" type="target" position={Position.Top} />
      <Handle className="agent-map-handle" type="source" position={Position.Bottom} />
      <div className="agent-map-node-icon">
        <Icon size={22} />
      </div>
      <div className="agent-map-node-copy">
        <strong>{data.label}</strong>
        <span>{nodeKindLabel(data.kind)}</span>
      </div>
      <i className="agent-map-status-dot" aria-label={`Status ${data.status}`} />
    </div>
  );
}

function nodeKindLabel(kind: AgentMapNodeData['kind']) {
  if (kind === 'orchestrator') return 'Systemsteuerung';
  if (kind === 'agent') return 'Agent';
  if (kind === 'platform') return 'Platform Service';
  if (kind === 'database') return 'Datenhaltung';
  if (kind === 'external') return 'Externes System';
  return 'Service';
}
