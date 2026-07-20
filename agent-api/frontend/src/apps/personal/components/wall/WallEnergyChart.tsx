import {
    Area,
    AreaChart,
    CartesianGrid,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';

type EnergyPowerPoint = { timestamp: string; value: number };

const ENERGY_HISTORY_WINDOW_MS = 60 * 60 * 1000;

export default function WallEnergyChart({history}: { history: EnergyPowerPoint[] }) {
    const chart = energyChartData(history);
    return (
        <div className="wall-energy-sparkline">
            {chart.data.length >= 2 ? (
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chart.data} margin={{top: 14, right: 10, bottom: 4, left: 0}}>
                        <defs>
                            <linearGradient id="wallEnergyPowerGradient" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="var(--state-active)" stopOpacity={0.15}/>
                                <stop offset="100%" stopColor="var(--state-active)" stopOpacity={0}/>
                            </linearGradient>
                        </defs>
                        <CartesianGrid
                            vertical={false}
                            stroke="color-mix(in srgb, var(--muted-foreground) 18%, transparent)"
                            strokeWidth={1}
                        />
                        <XAxis
                            dataKey="at"
                            type="number"
                            domain={[chart.start, chart.end]}
                            ticks={chart.ticks}
                            axisLine={false}
                            tickLine={false}
                            tickFormatter={formatEnergyChartTime}
                            tick={{fill: 'var(--muted-foreground)', fontSize: 11}}
                            minTickGap={28}
                        />
                        <YAxis
                            domain={[chart.domain.min, chart.domain.max]}
                            axisLine={false}
                            tickLine={false}
                            tickFormatter={formatEnergyChartWatts}
                            tick={{fill: 'var(--muted-foreground)', fontSize: 11}}
                            width={48}
                        />
                        <Tooltip
                            content={<EnergyChartTooltip/>}
                            cursor={{
                                stroke: 'color-mix(in srgb, var(--state-active) 34%, transparent)',
                                strokeWidth: 1,
                            }}
                        />
                        <Area
                            type="monotone"
                            dataKey="value"
                            stroke="var(--state-active)"
                            strokeWidth={2}
                            fill="url(#wallEnergyPowerGradient)"
                            dot={(props) => renderEnergyLastDot(props, chart.lastIndex)}
                            activeDot={{r: 5, stroke: 'var(--card)', strokeWidth: 2, fill: 'var(--state-active)'}}
                            isAnimationActive={false}
                        />
                    </AreaChart>
                </ResponsiveContainer>
            ) : (
                <span>Daten momentan nicht verfügbar.</span>
            )}
        </div>
    );
}

function EnergyChartTooltip({active, payload, label}: { active?: boolean; payload?: Array<{ value?: number }>; label?: number }) {
    const value = payload?.[0]?.value;
    if (!active || typeof value !== 'number') return null;
    return (
        <div className="wall-energy-tooltip">
            <strong>{formatWatts(value)}</strong>
            <span>{typeof label === 'number' ? formatEnergyChartTime(label) : ''}</span>
        </div>
    );
}

function energyChartData(history: EnergyPowerPoint[]) {
    const now = Date.now();
    const historyStart = now - ENERGY_HISTORY_WINDOW_MS;
    const points = history
        .map((point) => ({at: Date.parse(point.timestamp), value: point.value}))
        .filter((point) => Number.isFinite(point.at) && Number.isFinite(point.value) && point.at >= historyStart && point.at <= now)
        .sort((a, b) => a.at - b.at);
    const domain = energyTimeDomain(points, now);
    if (points.length < 2) {
        return {
            data: points,
            domain: {min: 0, max: 500},
            start: domain.start,
            end: domain.end,
            ticks: energyChartTicks(domain.start, domain.end),
            lastIndex: Math.max(0, points.length - 1),
        };
    }
    const data = smoothEnergyPoints(points);
    const valueDomain = stableEnergyDomain(data.map((point) => point.value));
    return {
        data,
        domain: valueDomain,
        start: domain.start,
        end: domain.end,
        ticks: energyChartTicks(domain.start, domain.end),
        lastIndex: Math.max(0, data.length - 1),
    };
}

function energyTimeDomain(points: Array<{ at: number; value: number }>, now: number) {
    if (!points.length) return {start: now - 10 * 60 * 1000, end: now};
    const first = points[0].at;
    const span = Math.max(1, now - first);
    if (span >= ENERGY_HISTORY_WINDOW_MS * 0.82) {
        return {start: now - ENERGY_HISTORY_WINDOW_MS, end: now};
    }
    const padding = Math.min(5 * 60 * 1000, Math.max(60 * 1000, span * 0.18));
    return {
        start: Math.max(now - ENERGY_HISTORY_WINDOW_MS, first - padding),
        end: now,
    };
}

function stableEnergyDomain(values: number[]) {
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const maxAbs = Math.max(500, Math.abs(minValue), Math.abs(maxValue)) * 1.15;
    const step = maxAbs > 8000 ? 2000 : maxAbs > 4000 ? 1000 : maxAbs > 1500 ? 500 : maxAbs > 700 ? 250 : 100;
    const max = Math.ceil(maxAbs / step) * step;
    const min = minValue < 0 ? -Math.ceil(Math.abs(minValue) * 1.15 / step) * step : 0;
    return {min, max};
}

function smoothEnergyPoints(points: Array<{ at: number; value: number }>) {
    return points.map((point, index) => {
        const previous = points[index - 1]?.value;
        const next = points[index + 1]?.value;
        const values = [previous, point.value, next].filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
        return {...point, value: values.reduce((sum, value) => sum + value, 0) / values.length};
    });
}

function energyChartTicks(start: number, end: number) {
    const span = Math.max(1, end - start);
    const step = span > 45 * 60 * 1000 ? 15 * 60 * 1000 : span > 20 * 60 * 1000 ? 5 * 60 * 1000 : 2 * 60 * 1000;
    const ticks: number[] = [];
    for (let tick = Math.ceil(start / step) * step; tick < end; tick += step) {
        ticks.push(tick);
    }
    return [start, ...ticks.slice(0, 5), end];
}

function formatEnergyChartTime(value: number) {
    return new Date(value).toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'});
}

function formatEnergyChartWatts(value: number) {
    if (Math.abs(value) >= 1000) return `${(value / 1000).toLocaleString('de-DE', {maximumFractionDigits: 1})} kW`;
    return `${Math.round(value)} W`;
}

function formatWatts(value: number | null | undefined) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '-';
    return `${Math.abs(Math.round(value)).toLocaleString('de-DE')} W`;
}

function renderEnergyLastDot(props: { cx?: number; cy?: number; index?: number }, lastIndex: number) {
    const {cx, cy, index} = props;
    if (index !== lastIndex || typeof cx !== 'number' || typeof cy !== 'number') return <g/>;
    return <circle cx={cx} cy={cy} r={4} fill="var(--state-active)" stroke="var(--card)" strokeWidth={2}/>;
}
