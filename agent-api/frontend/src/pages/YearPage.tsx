import { useEffect, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { api } from '../api/client';
import { ExportButtons } from '../components/ExportButtons';
import { MonthCard } from '../components/MonthCard';
import type { Route } from '../App';
import type { MonthSummary } from '../types/invoice';

export function YearPage({ year, navigate }: { year: number; navigate: (route: Route) => void }) {
  const [months, setMonths] = useState<MonthSummary[]>([]);
  useEffect(() => { api.year(year).then((data) => setMonths(data.months)); }, [year]);
  const fullYear = Array.from({ length: 12 }, (_, index) => {
    const monthNumber = index + 1;
    return months.find((entry) => entry.month === monthNumber) ?? {
      year,
      month: monthNumber,
      income_total: 0,
      expense_total: 0,
      invoice_count: 0,
      needs_review_count: 0,
    };
  });
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Jahr</span>
          <h1>{year}</h1>
          <p>Monatskarten mit Einnahmen, Ausgaben, Saldo und offenen Prüfungen.</p>
        </div>
        <div className="button-row">
          <button className="button ghost" onClick={() => navigate({ name: 'years' })}><ArrowLeft size={16} /> Zurück</button>
          <ExportButtons year={year} />
        </div>
      </header>
      <section className="month-grid">
        {fullYear.map((month) => (
          <MonthCard key={month.month} month={month} onOpen={() => navigate({ name: 'month', year, month: month.month })} />
        ))}
      </section>
    </div>
  );
}
