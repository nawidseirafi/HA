import type { MarketReport } from '@shared/api/client';
import { MarketSignalBadge } from './MarketSignalBadge';

export function MarketReportCard({ report, onOpen }: { report: MarketReport; onOpen?: (symbol: string) => void }) {
  return (
    <article className="market-report-card">
      <div className="market-report-head">
        <button className="table-link" onClick={() => onOpen?.(report.symbol)}>{report.symbol}</button>
        <MarketSignalBadge signal={report.recommendation || report.signal} />
      </div>
      <div className="market-price-row">
        <strong>{formatPrice(report.price)}</strong>
        <span className={(report.change_percent ?? 0) >= 0 ? 'market-positive' : 'market-negative'}>
          {formatPercent(report.change_percent)}
        </span>
      </div>
      <p>{report.summary || report.error || 'Keine echten KI-/Marktdaten gefunden.'}</p>
      <div className="market-source-line">
        <span>{sourceLabel(report.analysis_source)}</span>
        <span>{report.quote_provider || 'quote ?'}</span>
        <span>{report.news_provider || 'news ?'}</span>
      </div>
      <small>Confidence {Math.round(report.confidence || 0)}% · Risiko {report.risk_level || 'medium'} · {new Date(report.created_at).toLocaleString('de-DE')}</small>
      <b>Keine Finanzberatung.</b>
    </article>
  );
}

export function sourceLabel(source: MarketReport['analysis_source']) {
  if (source === 'llm') return 'KI';
  if (source === 'heuristic') return 'Heuristik';
  if (source === 'error') return 'Fehler';
  return 'Unbekannt';
}

export function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 }).format(value);
}

export function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}
