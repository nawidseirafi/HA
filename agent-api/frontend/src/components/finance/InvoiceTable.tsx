import { Eye, FileSearch, Trash2 } from 'lucide-react';
import type { Invoice } from '../../types/invoice';
import { currency, shortDate } from '../../lib/format';

interface Props {
  invoices: Invoice[];
  onOpen: (invoice: Invoice) => void;
  onPreview: (invoice: Invoice) => void;
  onDelete: (invoice: Invoice) => void;
}

export function InvoiceTable({ invoices, onOpen, onPreview, onDelete }: Props) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Datum</th>
            <th>Anbieter/Händler</th>
            <th>Kategorie</th>
            <th>Betrag</th>
            <th>Status</th>
            <th>Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((invoice) => (
            <tr key={invoice.id} onDoubleClick={() => onOpen(invoice)}>
              <td data-label="Datum">{shortDate(invoice.invoice_date)}</td>
              <td data-label="Anbieter">
                <button className="table-link" onClick={() => onOpen(invoice)}>
                  {invoice.vendor}
                </button>
              </td>
              <td data-label="Kategorie">{invoice.category}</td>
              <td data-label="Betrag">{currency(invoice.gross_amount ?? invoice.amount, invoice.currency)}</td>
              <td data-label="Status"><span className={`status status-${invoice.review_status}`}>{statusLabel(invoice.review_status)}</span></td>
              <td data-label="Aktionen">
                <div className="icon-actions">
                  <button title="Detail öffnen" onClick={() => onOpen(invoice)}><Eye size={16} /></button>
                  <button title="PDF anzeigen" onClick={() => onPreview(invoice)}><FileSearch size={16} /></button>
                  <button title="Löschen" onClick={() => onDelete(invoice)}><Trash2 size={16} /></button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function statusLabel(status: Invoice['review_status']) {
  return {
    reviewed: 'Verarbeitet',
    exported: 'Verarbeitet',
    needs_review: 'In Prüfung',
    review: 'In Prüfung',
    error: 'Fehler',
    new: 'Neu',
    archived: 'Verarbeitet',
  }[status] ?? status;
}
