import { AgentMap } from '../components/AgentMap';
import type { Route } from '../App';

interface Props {
  navigate: (route: Route) => void;
}

export function AgentMapPage({ navigate }: Props) {
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Agent Console</span>
          <h1>Agent Map</h1>
          <p>Architekturansicht der Agenten, Dienste, Datenbanken und externen Integrationen.</p>
        </div>
      </header>
      <AgentMap navigate={navigate} />
    </div>
  );
}
