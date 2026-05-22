import { useEffect, useState } from 'react';
import type { Invoice } from '../types/invoice';
import { api, getAuthToken } from '../api/client';

export function PdfPreview({ invoice }: { invoice: Invoice }) {
  const [src, setSrc] = useState('');
  const [error, setError] = useState('');
  const isImage = /\.(png|jpg|jpeg|tif|tiff|webp)$/i.test(invoice.stored_path || invoice.archive_path || invoice.source_path || '');

  useEffect(() => {
    let objectUrl = '';
    const controller = new AbortController();

    async function loadFile() {
      setError('');
      setSrc('');
      try {
        const token = getAuthToken();
        const response = await fetch(api.fileUrl(invoice.id), {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          signal: controller.signal,
        });
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || `Datei konnte nicht geladen werden (${response.status}).`);
        }
        objectUrl = URL.createObjectURL(await response.blob());
        setSrc(objectUrl);
      } catch (exc) {
        if (!controller.signal.aborted) {
          setError(exc instanceof Error ? exc.message : 'Datei konnte nicht geladen werden.');
        }
      }
    }

    loadFile();

    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [invoice.id]);

  return (
    <div className="preview-pane">
      {error && <div className="panel error-panel">{error}</div>}
      {!error && !src && <div className="panel">Lade Vorschau...</div>}
      {!error && src && (isImage ? <img src={src} alt={invoice.original_filename || 'Beleg'} /> : <iframe src={src} title="Belegvorschau" />)}
    </div>
  );
}
