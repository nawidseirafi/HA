import { Eye, FileSearch, Trash2 } from 'lucide-react';
import type { Invoice } from '../types/invoice';
import { currency, shortDate } from '../lib/format';

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
            <th>Anbieter</th>
            <th>Kategorie</th>
            <th>Betrag Brutto</th>
            <th>Art</th>
            <th>MwSt</th>
            <th>Zahlungsart</th>
            <th>Status</th>
            <th>Quelle</th>
            <th>Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((invoice) => (
            <tr key={invoice.id} onDoubleClick={() => onOpen(invoice)}>
              <td>{shortDate(invoice.invoice_date)}</td>
              <td>
                <button className="table-link" onClick={() => onOpen(invoice)}>
                  {invoice.vendor}
                </button>
              </td>
              <td>{invoice.category}</td>
              <td>{currency(invoice.gross_amount ?? invoice.amount, invoice.currency)}</td>
              <td>{invoice.transaction_type === 'income' ? 'Einnahme' : 'Ausgabe'}</td>
              <td>{invoice.tax_amount ? currency(invoice.tax_amount, invoice.currency) : '-'}</td>
              <td>{invoice.payment_method || '-'}</td>
              <td><span className={`status status-${invoice.review_status}`}>{invoice.review_status}</span></td>
              <td>{invoice.source || invoice.original_filename || '-'}</td>
              <td>
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
