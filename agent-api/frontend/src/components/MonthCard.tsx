import { ArrowRight } from 'lucide-react';
import type { MonthSummary } from '../types/invoice';
import { currency, monthNames } from '../lib/format';

export function MonthCard({ month, onOpen }: { month: MonthSummary; onOpen: () => void }) {
  const status = month.needs_review_count > 0 ? 'warning' : month.invoice_count > 0 ? 'ready' : 'idle';
  return (
    <button className={`month-card ${status}`} onClick={onOpen}>
      <div className="card-topline">
        <span>{String(month.month).padStart(2, '0')}</span>
        <ArrowRight size={16} />
      </div>
      <strong>{monthNames[month.month - 1]}</strong>
      <div className="metric-row">
        <span>Ausgaben</span>
        <b>{currency(month.expense_total)}</b>
      </div>
      <div className="metric-row">
        <span>Belege</span>
        <b>{month.invoice_count}</b>
      </div>
      <div className="metric-row warn">
        <span>Offen</span>
        <b>{month.needs_review_count}</b>
      </div>
    </button>
  );
}
