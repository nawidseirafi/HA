import { Play } from 'lucide-react';

export function MarketRunButton({ busy, onRun }: { busy: boolean; onRun: () => void }) {
  return (
    <button className="button primary" onClick={onRun} disabled={busy}>
      <Play size={16} /> {busy ? 'Analyse laeuft...' : 'Marktanalyse starten'}
    </button>
  );
}
