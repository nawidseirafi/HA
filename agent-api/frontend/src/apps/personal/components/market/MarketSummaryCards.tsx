import { Activity, BarChart3, ListChecks, TrendingDown, TrendingUp } from 'lucide-react';
import type { MarketReport, MarketSummary, MarketWatchlistItem } from '@shared/api/client';

export function MarketSummaryCards({
  summary,
  reports = [],
  watchlistItems,
}: {
  summary: MarketSummary | null;
  reports?: MarketReport[];
  watchlistItems?: MarketWatchlistItem[];
}) {
  const mood = marketMood(reports);
  const watchlistCount = watchlistItems ? watchlistItems.length : summary?.watchlist_count ?? 0;
  const enabledCount = watchlistItems ? watchlistItems.filter((item) => item.enabled).length : summary?.enabled_count ?? 0;
  return (
    <section className="kpi-grid market-kpis">
      <MarketKpi icon={BarChart3} label="Mood" value={mood.label} note={`${mood.confidence}% Confidence`} tone={mood.tone} />
      <MarketKpi icon={ListChecks} label="Watchlist" value={watchlistCount} note={`${enabledCount} aktiv`} tone="blue" />
      <MarketKpi icon={TrendingUp} label="Buy" value={summary?.signals.buy ?? 0} note="positive Signale" tone="green" />
      <MarketKpi icon={Activity} label="Hold" value={summary?.signals.hold ?? 0} note="keine Aktion noetig" tone="blue" />
      <MarketKpi icon={TrendingDown} label="Sell" value={summary?.signals.sell ?? 0} note="Risikosignale" tone="red" />
    </section>
  );
}

function marketMood(reports: MarketReport[]) {
  const values = reports.map((report) => Number(report.confidence || 0)).filter(Number.isFinite);
  const confidence = values.length ? Math.round(values.reduce((sum, value) => sum + value, 0) / values.length) : 0;
  const score = reports.reduce((sum, report) => {
    const signal = report.recommendation || report.signal;
    if (signal === 'buy') return sum + 1;
    if (signal === 'sell') return sum - 1;
    return sum;
  }, 0);
  if (score > 0) return { label: 'Bullish', confidence, tone: 'green' as const };
  if (score < 0) return { label: 'Bearish', confidence, tone: 'red' as const };
  return { label: 'Neutral', confidence, tone: 'yellow' as const };
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
