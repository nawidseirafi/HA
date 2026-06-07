import type { AgentManifest } from '@shared/api/client';
import { SeniorCarePlaceholderPage } from '../components/SeniorCarePlaceholderPage';

export function DashboardPage({ agents }: { agents: AgentManifest[] }) {
  return (
    <SeniorCarePlaceholderPage
      eyebrow="Dashboard"
      title="Tagesueberblick"
      description="Spaeter zeigt diese Seite Tagesstatus, letzte Aktivitaeten und offene Betreuungshinweise."
      items={agents.map((agent) => agent.name)}
    />
  );
}
