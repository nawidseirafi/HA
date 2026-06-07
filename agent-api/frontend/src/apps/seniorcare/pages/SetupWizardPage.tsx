import type { AgentManifest } from '@shared/api/client';
import { SeniorCarePlaceholderPage } from '../components/SeniorCarePlaceholderPage';

export function SetupWizardPage({ agents }: { agents: AgentManifest[] }) {
  return (
    <SeniorCarePlaceholderPage
      eyebrow="Setup Wizard"
      title="SeniorCare Einrichtung"
      description="Hier entsteht der gefuehrte Einrichtungsprozess fuer Home Assistant, Sensoren, Kontakte und Benachrichtigungen."
      items={agents.map((agent) => `${agent.name}: ${agent.status}`)}
    />
  );
}
