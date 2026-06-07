import type { ComponentType } from 'react';
import type { LucideProps } from 'lucide-react';
import type { Route } from '@personal/routes/routes';

export type AgentMapStatus = 'active' | 'running' | 'paused' | 'error' | 'disabled';

export type AgentMapNodeKind = 'orchestrator' | 'agent' | 'platform' | 'service' | 'external' | 'database';

export type AgentMapNodeData = {
  id: string;
  label: string;
  kind: AgentMapNodeKind;
  status: AgentMapStatus;
  description: string;
  lastRun: string;
  nextAction: string;
  icon: ComponentType<LucideProps>;
  route?: Route;
};

export type AgentMapServiceDetail = {
  id: string;
  label: string;
  status: AgentMapStatus;
  description: string;
  lastRun: string;
  nextAction: string;
};
