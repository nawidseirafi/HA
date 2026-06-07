import { ArrowRight, CalendarDays } from 'lucide-react';
import type { YearSummary } from '@shared/types/invoice';
import { currency } from '@shared/utils/format';

export function YearCard({ year, onOpen }: { year: YearSummary; onOpen: () => void }) {
  return (
    <button className="summary-card year-card clickable" onClick={onOpen}>
      <div className="card-topline">
        <span><CalendarDays size={16} /> Jahr</span>
        <ArrowRight size={18} />
      </div>
      <strong className="card-title">{year.year}</strong>
      <div className="metric-row">
        <span>Saldo</span>
        <b>{currency(year.total)}</b>
      </div>
      <div className="metric-row">
        <span>Einnahmen</span>
        <b>{currency(year.income_total)}</b>
      </div>
      <div className="metric-row">
        <span>Ausgaben</span>
        <b>{currency(year.expense_total)}</b>
      </div>
      <div className="metric-row">
        <span>Belege</span>
        <b>{year.invoice_count}</b>
      </div>
      <div className="metric-row warn">
        <span>Offen</span>
        <b>{year.needs_review_count}</b>
      </div>
      <div className="card-progress"><span style={{ width: `${Math.min(year.invoice_count * 8, 100)}%` }} /></div>
    </button>
  );
}
