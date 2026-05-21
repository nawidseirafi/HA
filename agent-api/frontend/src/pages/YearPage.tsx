import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { ExportButtons } from '../components/ExportButtons';
import { MonthCard } from '../components/MonthCard';
import type { Route } from '../App';
import type { MonthSummary } from '../types/invoice';

export function YearPage({ year, navigate }: { year: number; navigate: (route: Route) => void }) {
  const [months, setMonths] = useState<MonthSummary[]>([]);
  useEffect(() => { api.year(year).then((data) => setMonths(data.months)); }, [year]);
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Jahr</span>
          <h1>{year}</h1>
        </div>
        <ExportButtons year={year} />
      </header>
      <section className="month-grid">
        {months.map((month) => (
          <MonthCard key={month.month} month={month} onOpen={() => navigate({ name: 'month', year, month: month.month })} />
        ))}
      </section>
    </div>
  );
}
