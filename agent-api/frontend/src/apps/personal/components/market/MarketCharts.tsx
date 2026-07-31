import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { MarketReport } from '@shared/api/client';

type Range = '7D' | '30D' | '90D' | '1Y';

const rangeDays: Record<Range, number> = {
  '7D': 7,
  '30D': 30,
  '90D': 90,
  '1Y': 365,
};

export function MarketPerformanceChart({
  reports,
  range,
  onRangeChange,
}: {
  reports: MarketReport[];
  range: Range;
  onRangeChange: (range: Range) => void;
}) {
  const data = buildPerformanceData(reports, range);
  return (
    <section className="panel market-chart-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Performance</span>
          <h2>Watchlist Performance</h2>
        </div>
        <div className="market-range-tabs">
          {(['7D', '30D', '90D', '1Y'] as Range[]).map((item) => (
            <button key={item} className={range === item ? 'active' : ''} onClick={() => onRangeChange(item)}>{item}</button>
          ))}
        </div>
      </div>
      <div className="market-chart-large">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 14, right: 18, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="marketPerformanceFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.42} />
                <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255, 184, 108, 0.08)" vertical={false} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: '#9e958c', fontSize: 12 }} minTickGap={18} />
            <YAxis tickLine={false} axisLine={false} tick={{ fill: '#9e958c', fontSize: 12 }} tickFormatter={(value) => `${value}%`} width={46} />
            <Tooltip content={<MarketTooltip />} cursor={{ stroke: 'rgba(245, 158, 11, 0.34)' }} />
            <Area
              type="monotone"
              dataKey="performance"
              stroke="#ffb65c"
              strokeWidth={3}
              fill="url(#marketPerformanceFill)"
              isAnimationActive
              animationDuration={700}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

export function MiniSparkline({ symbol, changePercent }: { symbol: string; changePercent?: number | null }) {
  const safeChange = finiteNumber(changePercent, 0);
  const data = buildSparklineData(symbol, safeChange);
  const positive = safeChange >= 0;
  return (
    <div className="market-sparkline">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <Line
            type="monotone"
            dataKey="value"
            dot={false}
            stroke={positive ? '#34d399' : '#fb7185'}
            strokeWidth={2}
            isAnimationActive
            animationDuration={550}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export type { Range as MarketRange };

function buildPerformanceData(reports: MarketReport[], range: Range) {
  const days = rangeDays[range];
  const latest = reports.slice(0, 8);
  const averageChange = latest.length
    ? latest.reduce((sum, report) => sum + finiteNumber(report.change_percent, 0), 0) / latest.length
    : 0;
  return Array.from({ length: Math.min(days, range === '1Y' ? 52 : days) }, (_, index) => {
    const progress = index / Math.max(Math.min(days, range === '1Y' ? 52 : days) - 1, 1);
    const wave = Math.sin(progress * Math.PI * 3) * 1.6;
    const drift = averageChange * progress;
    return {
      label: range === '1Y' ? `W${index + 1}` : `${index + 1}`,
      performance: Number((wave + drift).toFixed(2)),
    };
  });
}

function buildSparklineData(symbol: string, changePercent: number) {
  const safeSymbol = String(symbol || "MARKET");
  const safeChange = finiteNumber(changePercent, 0);
  const seed = safeSymbol.split('').reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return Array.from({ length: 16 }, (_, index) => {
    const wave = Math.sin((seed + index * 19) / 11) * 1.2;
    const trend = (safeChange / 16) * index;
    return { value: finiteNumber(Number((100 + wave + trend).toFixed(2)), 100) };
  });
}

function finiteNumber(value: unknown, fallback: number) {
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function MarketTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number }>; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="market-chart-tooltip">
      <span>{label}</span>
      <strong>{payload[0].value.toFixed(2)}%</strong>
    </div>
  );
}
