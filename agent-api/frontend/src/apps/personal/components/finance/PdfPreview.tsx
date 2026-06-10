import { useEffect, useState } from 'react';
import type { Invoice } from '@shared/types/invoice';
import { api, getAuthToken, handleUnauthorizedResponse } from '@shared/api/client';

export function PdfPreview({ invoice }: { invoice: Invoice }) {
  const [src, setSrc] = useState('');
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const path = invoice.stored_path || invoice.archive_path || invoice.source_path || '';
  const isImage = /\.(png|jpg|jpeg|tif|tiff|webp)$/i.test(path);
  const isText = /\.(txt|csv|json)$/i.test(path) || invoice.document_type === 'ebon_qr';

  useEffect(() => {
    let objectUrl = '';
    const controller = new AbortController();

    async function loadFile() {
      setError('');
      setSrc('');
      setText('');
      try {
        const token = getAuthToken();
        const response = await fetch(api.fileUrl(invoice.id), {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          signal: controller.signal,
        });
        handleUnauthorizedResponse(response);
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || `Datei konnte nicht geladen werden (${response.status}).`);
        }
        if (isText) {
          setText(await response.text());
        } else {
          objectUrl = URL.createObjectURL(await response.blob());
          setSrc(objectUrl);
        }
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
  }, [invoice.id, isText]);

  return (
    <div className="preview-pane">
      {error && <div className="panel error-panel">{error}</div>}
      {!error && !src && !text && <div className="panel">Lade Vorschau...</div>}
      {!error && text && <TextReceiptPreview invoice={invoice} text={text} />}
      {!error && src && (isImage ? <img src={src} alt={invoice.original_filename || 'Beleg'} /> : <iframe src={src} title="Belegvorschau" />)}
    </div>
  );
}

function TextReceiptPreview({ invoice, text }: { invoice: Invoice; text: string }) {
  return (
    <div className="text-receipt-preview">
      <div className="text-receipt-header">
        <span className="eyebrow">E-Bon / Textbeleg</span>
        <h3>{invoice.vendor || 'Beleginhalt'}</h3>
        <p>Dieser Beleg wurde aus QR-Code- oder Textinhalt erstellt.</p>
      </div>
      <pre>{text}</pre>
    </div>
  );
}
