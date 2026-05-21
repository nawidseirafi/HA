import { Download } from 'lucide-react';
import { api } from '../api/client';

interface Props {
  year: number;
  month?: number;
}

export function ExportButtons({ year, month }: Props) {
  const scope = month ? 'month' : 'year';
  return (
    <div className="button-row">
      <a className="button secondary" href={api.exportUrl(scope, year, month ?? null, 'excel')}>
        <Download size={16} /> Excel
      </a>
      <a className="button secondary" href={api.exportUrl(scope, year, month ?? null, 'pdf')}>
        <Download size={16} /> PDF
      </a>
      <a className="button secondary" href={api.exportUrl(scope, year, month ?? null, 'zip')}>
        <Download size={16} /> ZIP
      </a>
      <button className="button ghost" disabled>DATEV</button>
      <button className="button ghost" disabled>ELSTER spaeter verfuegbar</button>
    </div>
  );
}
