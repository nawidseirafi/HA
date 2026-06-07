import { useEffect, useState } from 'react';
import { api } from '@shared/api/client';
import { YearCard } from '../../components/finance/YearCard';
import type { Route } from '../../App';
import type { YearSummary } from '@shared/types/invoice';

export function YearsPage({ navigate }: { navigate: (route: Route) => void }) {
  const [years, setYears] = useState<YearSummary[]>([]);
  useEffect(() => { api.years().then(setYears); }, []);
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Archiv</span>
          <h1>Jahre</h1>
          <p>Wähle ein Geschäftsjahr und öffne die Monatsübersicht.</p>
        </div>
      </header>
      <section className="card-grid">
        {years.map((year) => <YearCard key={year.year} year={year} onOpen={() => navigate({ name: 'year', year: year.year })} />)}
      </section>
    </div>
  );
}
