import { Edit3, ExternalLink, Trash2 } from 'lucide-react';
import type { MarketWatchlistItem } from '../../api/client';

export function WatchlistTable({
  items,
  onEdit,
  onDelete,
  onOpen,
}: {
  items: MarketWatchlistItem[];
  onEdit: (item: MarketWatchlistItem) => void;
  onDelete: (item: MarketWatchlistItem) => void;
  onOpen: (symbol: string) => void;
}) {
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
              <th>ISIN</th>
              <th>WKN</th>
              <th>Typ</th>
              <th>Exchange</th>
              <th>Währung</th>
              <th>Aktiv</th>
              <th>Input</th>
              <th>Details</th>
              <th>Aktionen</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} onDoubleClick={() => onOpen(item.symbol)}>
                {(() => {
                  const symbol = String(item.symbol || '').toUpperCase();
                  return (
                    <>
                <td data-label="Symbol"><button className="table-link" onClick={() => onEdit(item)}>{symbol || '-'}</button></td>
                <td data-label="Name">{item.resolved_name || item.name}</td>
                <td data-label="ISIN">{item.isin || '-'}</td>
                <td data-label="WKN">{item.wkn || '-'}</td>
                <td data-label="Typ">{item.asset_type}</td>
                <td data-label="Exchange">{item.exchange || '-'}</td>
                <td data-label="Währung">{item.currency}</td>
                <td data-label="Aktiv">{item.enabled ? 'Ja' : 'Nein'}</td>
                 <td data-label="Aktionen">
                  <div className="icon-actions">
                    <button title="Details" onClick={() => onOpen(symbol)}><ExternalLink size={16} /></button>
                    <button title="Löschen" onClick={() => onDelete(item)}><Trash2 size={16} /></button>
                  </div>
                </td>
                    </>
                  );
                })()}
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={11}>Noch keine Watchlist-Einträge vorhanden.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
