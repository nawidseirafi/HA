import type { Invoice } from '../types/invoice';
import { api } from '../api/client';

export function PdfPreview({ invoice }: { invoice: Invoice }) {
  const src = api.fileUrl(invoice.id);
  const isImage = /\.(png|jpg|jpeg|tif|tiff|webp)$/i.test(invoice.stored_path || invoice.archive_path || invoice.source_path || '');
  return (
    <div className="preview-pane">
      {isImage ? <img src={src} alt={invoice.original_filename || 'Beleg'} /> : <iframe src={src} title="Belegvorschau" />}
    </div>
  );
}
