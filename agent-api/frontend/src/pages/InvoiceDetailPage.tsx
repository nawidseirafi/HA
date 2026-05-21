import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { InvoiceDetailPanel } from '../components/InvoiceDetailPanel';
import { PdfPreview } from '../components/PdfPreview';
import type { Route } from '../App';
import type { Invoice } from '../types/invoice';

export function InvoiceDetailPage({ id, navigate }: { id: number; navigate: (route: Route) => void }) {
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const load = () => api.invoice(id).then((data) => {
    setInvoice(data);
    setError('');
  }).catch((exc) => setError(String(exc)));
  useEffect(() => { load(); }, [id]);

  if (error) return <div className="panel error-panel">{error}</div>;
  if (!invoice) return <div className="panel">Lade Beleg...</div>;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Detail</span>
          <h1>{invoice.vendor}</h1>
        </div>
        <button className="button ghost" onClick={() => navigate({ name: 'month', year: invoice.year, month: invoice.month })}>Zurueck zum Monat</button>
      </header>
      <div className="detail-layout">
        <PdfPreview invoice={invoice} />
        <InvoiceDetailPanel
          invoice={invoice}
          onSave={async (payload) => {
            const updated = await api.updateInvoice(id, payload);
            setInvoice(updated);
            setNotice('Gespeichert.');
          }}
          onReanalyze={async () => {
            setError('');
            setNotice('KI-Analyse läuft...');
            try {
              const result = await api.reanalyze(id) as { invoice?: Invoice; message?: string };
              if (result.invoice) {
                setInvoice(result.invoice);
              } else {
                await load();
              }
              setNotice(result.message || 'KI-Analyse abgeschlossen.');
            } catch (exc) {
              setNotice('');
              setError(exc instanceof Error ? exc.message : String(exc));
            }
          }}
        />
      </div>
      {notice && <div className="toast">{notice}</div>}
    </div>
  );
}
