import type { Invoice, MonthSummary, Summary, YearSummary } from '../types/invoice';

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    let detail = '';
    try {
      const data = JSON.parse(text) as { detail?: string };
      detail = data.detail || '';
    } catch {
      detail = '';
    }
    throw new Error(detail || text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  summary: () => request<Summary>('/api/invoices/summary'),
  years: async () => (await request<{ years: YearSummary[] }>('/api/invoices/years')).years,
  year: (year: number) => request<{ year: number; months: MonthSummary[] }>(`/api/invoices/years/${year}`),
  month: (year: number, month: number, params: URLSearchParams) =>
    request<{ year: number; month: number; invoices: Invoice[] }>(`/api/invoices/years/${year}/months/${month}?${params}`),
  invoice: (id: number) => request<Invoice>(`/api/invoices/${id}`),
  updateInvoice: (id: number, payload: Partial<Invoice>) =>
    request<Invoice>(`/api/invoices/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  markReviewed: (id: number) => request<Invoice>(`/api/invoices/${id}/mark-reviewed`, { method: 'POST' }),
  reanalyze: (id: number) => request(`/api/invoices/${id}/reanalyze`, { method: 'POST' }),
  deleteInvoice: (id: number) => request(`/api/invoices/${id}`, { method: 'DELETE' }),
  runAgent: () => request('/api/invoices/run', { method: 'POST' }),
  upload: async (file: File) => {
    const data = new FormData();
    data.append('file', file);
    const response = await fetch(`${API_BASE}/api/invoices/upload`, { method: 'POST', body: data });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  },
  fileUrl: (id: number) => `${API_BASE}/api/invoices/${id}/file`,
  exportUrl: (scope: 'year' | 'month', year: number, month: number | null, type: 'excel' | 'pdf' | 'zip') =>
    scope === 'year'
      ? `${API_BASE}/api/exports/year/${year}/${type}`
      : `${API_BASE}/api/exports/month/${year}/${month}/${type}`,
};
