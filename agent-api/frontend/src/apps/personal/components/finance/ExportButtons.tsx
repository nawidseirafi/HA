import { useState } from 'react';
import { Download } from 'lucide-react';
import { api } from '@shared/api/client';

interface Props {
  year: number;
  month?: number;
  compact?: boolean;
}

export function ExportButtons({ year, month, compact = false }: Props) {
  const scope = month ? 'month' : 'year';
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');

  const exportFile = async (type: 'excel' | 'pdf' | 'zip') => {
    const key = `${scope}-${type}`;
    setBusy(key);
    setError('');
    try {
      const { blob, filename } = await api.downloadExport(scope, year, month ?? null, type);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export fehlgeschlagen.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={compact ? 'export-compact' : 'export-actions'}>
      <button className="button secondary" type="button" onClick={() => exportFile('excel')} disabled={busy !== null}>
        <Download size={16} /> {busy === `${scope}-excel` ? 'Exportiere...' : compact ? 'Monats-Excel' : 'Excel'}
      </button>
      <button className="button secondary" type="button" onClick={() => exportFile('pdf')} disabled={busy !== null}>
        <Download size={16} /> {busy === `${scope}-pdf` ? 'Exportiere...' : compact ? 'Monats-PDF' : 'PDF'}
      </button>
      {!compact && (
        <>
          <button className="button secondary" type="button" onClick={() => exportFile('zip')} disabled={busy !== null}>
            <Download size={16} /> {busy === `${scope}-zip` ? 'Exportiere...' : 'ZIP'}
          </button>
          <button className="button ghost" disabled>DATEV</button>
          <button className="button ghost" disabled>ELSTER später verfügbar</button>
        </>
      )}
      {error && <span className="inline-error">{error}</span>}
    </div>
  );
}
