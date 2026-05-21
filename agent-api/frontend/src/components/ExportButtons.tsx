import { Download } from 'lucide-react';
import { api } from '../api/client';

interface Props {
  year: number;
  month?: number;
  compact?: boolean;
}

export function ExportButtons({ year, month, compact = false }: Props) {
  const scope = month ? 'month' : 'year';
  return (
    <div className={compact ? 'export-compact' : 'button-row'}>
      <a className="button secondary" href={api.exportUrl(scope, year, month ?? null, 'excel')}>
        <Download size={16} /> {compact ? 'Monats-Excel' : 'Excel'}
      </a>
      <a className="button secondary" href={api.exportUrl(scope, year, month ?? null, 'pdf')}>
        <Download size={16} /> {compact ? 'Monats-PDF' : 'PDF'}
      </a>
      {!compact && (
        <>
          <a className="button secondary" href={api.exportUrl(scope, year, month ?? null, 'zip')}>
            <Download size={16} /> ZIP
          </a>
          <button className="button ghost" disabled>DATEV</button>
          <button className="button ghost" disabled>ELSTER später verfügbar</button>
        </>
      )}
    </div>
  );
}
