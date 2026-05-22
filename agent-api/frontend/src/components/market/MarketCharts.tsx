import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { MarketReport, MarketSignal, MarketSummary } from '../../api/client';

type Range = '7D' | '30D' | '90D' | '1Y';

const signalColors: Record<MarketSignal, string> = {
  bullish: '#34d399',
  neutral: '#4d8dff',
  bearish: '#fb7185',
  watch: '#fbbf24',
};

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
                <stop offset="5%" stopColor="#4d8dff" stopOpacity={0.42} />
                <stop offset="95%" stopColor="#4d8dff" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(190, 208, 235, 0.08)" vertical={false} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: '#7f8da8', fontSize: 12 }} minTickGap={18} />
            <YAxis tickLine={false} axisLine={false} tick={{ fill: '#7f8da8', fontSize: 12 }} tickFormatter={(value) => `${value}%`} width={46} />
            <Tooltip content={<MarketTooltip />} cursor={{ stroke: 'rgba(77, 141, 255, 0.34)' }} />
            <Area
              type="monotone"
              dataKey="performance"
              stroke="#6da2ff"
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

export function MarketSentimentDonut({ summary }: { summary: MarketSummary | null }) {
  const data = (['bullish', 'neutral', 'bearish', 'watch'] as MarketSignal[]).map((signal) => ({
    name: signal,
    value: summary?.signals[signal] ?? 0,
  }));
  const total = data.reduce((sum, item) => sum + item.value, 0);
  return (
    <section className="panel market-donut-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Sentiment</span>
          <h2>Signale</h2>
        </div>
      </div>
      <div className="market-donut-wrap">
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius={62}
              outerRadius={88}
              paddingAngle={4}
              stroke="rgba(7, 17, 31, 0.9)"
              strokeWidth={3}
              isAnimationActive
              animationDuration={650}
            >
              {data.map((entry) => <Cell key={entry.name} fill={signalColors[entry.name]} />)}
            </Pie>
            <Tooltip content={<DonutTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="market-donut-center">
          <strong>{total}</strong>
          <span>Reports</span>
        </div>
      </div>
      <div className="market-donut-legend">
        {data.map((item) => (
          <div key={item.name}>
            <i style={{ background: signalColors[item.name] }} />
            <span>{item.name}</span>
            <b>{item.value}</b>
          </div>
        ))}
      </div>
    </section>
  );
}

export function MiniSparkline({ symbol, changePercent }: { symbol: string; changePercent?: number | null }) {
  const data = buildSparklineData(symbol, changePercent ?? 0);
  const positive = (changePercent ?? 0) >= 0;
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
    ? latest.reduce((sum, report) => sum + (report.change_percent ?? 0), 0) / latest.length
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
  const seed = symbol.split('').reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return Array.from({ length: 16 }, (_, index) => {
    const wave = Math.sin((seed + index * 19) / 11) * 1.2;
    const trend = (changePercent / 16) * index;
    return { value: Number((100 + wave + trend).toFixed(2)) };
  });
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

function DonutTooltip({ active, payload }: { active?: boolean; payload?: Array<{ name: string; value: number }> }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="market-chart-tooltip">
      <span>{payload[0].name}</span>
      <strong>{payload[0].value}</strong>
    </div>
  );
}
