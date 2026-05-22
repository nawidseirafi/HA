import { Activity, AlertTriangle, Eye, ListChecks, TrendingDown, TrendingUp } from 'lucide-react';
import type { MarketSummary } from '../../api/client';

export function MarketSummaryCards({ summary }: { summary: MarketSummary | null }) {
  return (
    <section className="kpi-grid market-kpis">
      <MarketKpi icon={ListChecks} label="Watchlist" value={summary?.watchlist_count ?? 0} note={`${summary?.enabled_count ?? 0} aktiv`} tone="blue" />
      <MarketKpi icon={TrendingUp} label="Bullish" value={summary?.signals.bullish ?? 0} note="positive Einschaetzung" tone="green" />
      <MarketKpi icon={TrendingDown} label="Bearish" value={summary?.signals.bearish ?? 0} note="negative Einschaetzung" tone="red" />
      <MarketKpi icon={Eye} label="Watch" value={summary?.signals.watch ?? 0} note="weiter beobachten" tone="yellow" />
      <MarketKpi icon={Activity} label="Neutral" value={summary?.signals.neutral ?? 0} note="keine klare Tendenz" tone="blue" />
      <MarketKpi icon={AlertTriangle} label="Disclaimer" value="Keine" note="Finanzberatung" tone="yellow" />
    </section>
  );
}

function MarketKpi({ icon: Icon, label, value, note, tone }: { icon: typeof Activity; label: string; value: string | number; note: string; tone: 'blue' | 'green' | 'yellow' | 'red' }) {
  return (
    <div className={`kpi-card ${tone}`}>
      <div className="kpi-icon"><Icon size={22} /></div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
