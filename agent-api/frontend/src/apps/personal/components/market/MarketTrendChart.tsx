import type { MarketReport } from '@shared/api/client';

export function MarketTrendChart({ reports }: { reports: MarketReport[] }) {
  const values = reports.slice(0, 12).reverse();
  const max = Math.max(...values.map((item) => Math.abs(item.change_percent ?? 0)), 1);
  return (
    <div className="market-trend-chart">
      {values.map((report) => {
        const value = report.change_percent ?? 0;
        return (
          <div className="market-trend-item" key={report.id}>
            <span>{value.toFixed(1)}%</span>
            <div className="market-trend-track">
              <i
                className={value >= 0 ? 'up' : 'down'}
                style={{ height: `${Math.max(Math.abs(value) / max * 100, 8)}%` }}
              />
            </div>
            <small>{new Date(report.created_at).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}</small>
          </div>
        );
      })}
    </div>
  );
}
