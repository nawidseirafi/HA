import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { ExportButtons } from '../components/ExportButtons';
import { InvoiceTable } from '../components/InvoiceTable';
import { PdfPreview } from '../components/PdfPreview';
import type { Route } from '../App';
import type { Invoice } from '../types/invoice';
import { monthNames } from '../lib/format';

export function MonthPage({ year, month, navigate }: { year: number; month: number; navigate: (route: Route) => void }) {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [preview, setPreview] = useState<Invoice | null>(null);
  const [filters, setFilters] = useState({ category: '', status: '', vendor: '', amountMin: '', amountMax: '', search: '' });

  const params = useMemo(() => {
    const value = new URLSearchParams();
    Object.entries(filters).forEach(([key, entry]) => entry && value.set(key, entry));
    return value;
  }, [filters]);

  const load = () => api.month(year, month, params).then((data) => setInvoices(data.invoices));
  useEffect(() => { load(); }, [year, month, params]);

  const remove = async (invoice: Invoice) => {
    if (!confirm(`Beleg ${invoice.vendor} löschen?`)) return;
    await api.deleteInvoice(invoice.id);
    await load();
  };

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">{year}</span>
          <h1>{monthNames[month - 1]}</h1>
        </div>
        <div className="button-row">
          <button className="button ghost" onClick={() => navigate({ name: 'year', year })}>Zurueck zum Jahr</button>
          <ExportButtons year={year} month={month} />
        </div>
      </header>
      <section className="filters">
        {(['search', 'category', 'status', 'vendor', 'amountMin', 'amountMax'] as const).map((key) => (
          <input key={key} placeholder={labelFor(key)} value={filters[key]} onChange={(event) => setFilters((current) => ({ ...current, [key]: event.target.value }))} />
        ))}
      </section>
      <InvoiceTable invoices={invoices} onOpen={(invoice) => navigate({ name: 'invoice', id: invoice.id })} onPreview={setPreview} onDelete={remove} />
      {preview && (
        <div className="modal-backdrop" onClick={() => setPreview(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <PdfPreview invoice={preview} />
          </div>
        </div>
      )}
    </div>
  );
}

function labelFor(key: string) {
  return {
    search: 'Suche',
    category: 'Kategorie',
    status: 'Status',
    vendor: 'Anbieter',
    amountMin: 'Betrag von',
    amountMax: 'Betrag bis',
  }[key] ?? key;
}
