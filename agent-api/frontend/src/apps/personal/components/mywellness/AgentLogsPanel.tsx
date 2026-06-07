import { Terminal } from 'lucide-react';

interface Props {
  logs: string[];
}

export function AgentLogsPanel({ logs }: Props) {
  return (
    <section className="panel logs-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Diagnose</span>
          <h2>Agent Logs</h2>
        </div>
        <Terminal size={18} />
      </div>
      <pre>{logs.length ? logs.join('\n') : 'Keine Logs vorhanden.'}</pre>
    </section>
  );
}
