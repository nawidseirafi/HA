import { Edit3, Play, Trash2 } from 'lucide-react';
import type { MarketReport, MarketWatchlistItem } from '../../api/client';
import { MiniSparkline } from './MarketCharts';
import { formatPercent } from './MarketReportCard';

export function WatchlistTable({
  items,
  latestReports,
  busySymbol,
  onEdit,
  onDelete,
  onAnalyze,
  onOpen,
}: {
  items: MarketWatchlistItem[];
  latestReports?: MarketReport[];
  busySymbol?: string;
  onEdit: (item: MarketWatchlistItem) => void;
  onDelete: (item: MarketWatchlistItem) => void;
  onAnalyze: (item: MarketWatchlistItem) => void;
  onOpen: (symbol: string) => void;
}) {
  const reportBySymbol = new Map((latestReports ?? []).map((report) => [report.symbol, report]));
  return (
    <div className="panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">MarketAgent</span>
          <h2>Watchlist</h2>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Name</th>
              <th>Typ</th>
              <th>Exchange</th>
              <th>Currency</th>
              <th>Trend</th>
              <th>%</th>
              <th>Aktiv</th>
              <th>Notizen</th>
              <th>Aktionen</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} onDoubleClick={() => onOpen(item.symbol)}>
                {(() => {
                  const report = reportBySymbol.get(item.symbol);
                  const change = report?.change_percent ?? null;
                  return (
                    <>
                <td data-label="Symbol"><button className="table-link" onClick={() => onOpen(item.symbol)}>{item.symbol}</button></td>
                <td data-label="Name">{item.name}</td>
                <td data-label="Typ">{item.asset_type}</td>
                <td data-label="Exchange">{item.exchange || '-'}</td>
                <td data-label="Currency">{item.currency}</td>
                <td data-label="Trend"><MiniSparkline symbol={item.symbol} changePercent={change} /></td>
                <td data-label="%"><span className={(change ?? 0) >= 0 ? 'market-positive' : 'market-negative'}>{formatPercent(change)}</span></td>
                <td data-label="Aktiv">{item.enabled ? 'Ja' : 'Nein'}</td>
                <td data-label="Notizen">{item.notes || '-'}</td>
                <td data-label="Aktionen">
                  <div className="icon-actions">
                    <button title="Analysieren" disabled={busySymbol === item.symbol} onClick={() => onAnalyze(item)}><Play size={16} /></button>
                    <button title="Bearbeiten" onClick={() => onEdit(item)}><Edit3 size={16} /></button>
                    <button title="Löschen" onClick={() => onDelete(item)}><Trash2 size={16} /></button>
                  </div>
                </td>
                    </>
                  );
                })()}
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={10}>Noch keine Watchlist-Einträge vorhanden.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
