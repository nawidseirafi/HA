import type { Invoice, MonthSummary, Summary, YearSummary } from '../types/invoice';

const API_BASE = import.meta.env.VITE_API_BASE ?? '';
const TOKEN_KEY = 'robotersteve.agent-api.token';
const SESSION_TOKEN_KEY = 'robotersteve.agent-api.session-token';

export type AuthResponse = {
  access_token: string;
  token_type: 'bearer';
  expires_at: number;
  user: { username: string };
};

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(SESSION_TOKEN_KEY);
}

export function setAuthToken(token: string, remember: boolean) {
  clearAuthToken();
  const storage = remember ? localStorage : sessionStorage;
  storage.setItem(remember ? TOKEN_KEY : SESSION_TOKEN_KEY, token);
}

export function clearAuthToken() {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(SESSION_TOKEN_KEY);
}

export type AgentStatus = {
  enabled: boolean;
  prepare_enabled?: boolean;
  booking_enabled?: boolean;
  prepare_time?: string;
  booking_time?: string;
  days?: number;
  desired_courses?: string[];
  is_running: boolean;
  current_status: string;
  last_status?: string;
  last_successful_run: string | null;
  last_prepare_run?: string | null;
  last_booking_run?: string | null;
  next_scheduled_run: string | null;
  last_error: string | null;
  last_started_at?: string | null;
  last_finished_at?: string | null;
  last_mode?: 'prepare' | 'book';
};

export type MyWellnessSettingsPayload = {
  enabled?: boolean;
  prepare_enabled?: boolean;
  booking_enabled?: boolean;
  prepare_time?: string;
  booking_time?: string;
  days?: number;
  desired_courses?: string[];
};

export type MyWellnessLog = {
  id: number;
  action_type: string;
  status: string;
  message: string;
  duration_seconds?: number | null;
  created_at: string;
};

export type CourseStatus = 'available' | 'booked' | 'full' | 'waitlist';

export type Course = {
  id: string;
  title: string;
  studio: string;
  trainer?: string | null;
  startTime: string | null;
  endTime?: string | null;
  availableSlots?: number | null;
  waitingList?: boolean | null;
  booked: boolean;
  bookable: boolean;
  cancellable: boolean;
  status: CourseStatus;
  category?: string | null;
  name?: string;
  starts_at?: string | null;
  ends_at?: string | null;
  location?: string | null;
  booking_status?: string;
  is_desired?: boolean;
  is_participant?: boolean;
};

export type MyWellnessCourse = Course;

export type PathSetting = {
  path: string;
  exists: boolean;
};

export type SettingsInfo = {
  api: {
    title: string;
    version: string;
    host: string;
    port: number;
    config_file: string;
  };
  auth: {
    mode: string;
    enabled: boolean;
    username_env: string;
    password_configured: boolean;
    jwt_secret_configured: boolean;
    token_ttl_seconds: number;
    token_ttl_days: number;
  };
  frontend: {
    dev_server: string;
    production_dist: string;
    production_dist_exists: boolean;
  };
  storage: {
    uploads: PathSetting;
    status_file: PathSetting;
    log_file: PathSetting;
  };
  agents: {
    invoices: {
      enabled: boolean;
      upload_dir: PathSetting;
      database: PathSetting;
      email_enabled: boolean;
      portal_import_enabled: boolean;
      ai_extraction_enabled: boolean;
      poll_interval_seconds?: number;
    };
    mywellness: {
      enabled: boolean;
      database: PathSetting;
      days: number;
      schedule: string[];
      desired_courses: string[];
      token_configured: boolean;
      user_id_configured: boolean;
      facility_id_configured: boolean;
    };
    vacation: {
      enabled: boolean;
    };
    market?: {
      enabled: boolean;
      database: PathSetting;
      price_provider: string;
      news_provider: string;
      trading_enabled: boolean;
      disclaimer: string;
    };
  };
  integrations: {
    llm: {
      provider: string;
      model: string;
      api_key_configured: boolean;
    };
    home_assistant: {
      configured: boolean;
      notifications_enabled: boolean;
      notify_service: string;
      persistent_notifications: boolean;
    };
  };
  security: {
    secrets_visible: boolean;
    note: string;
  };
};

export type MarketSignal = 'bullish' | 'neutral' | 'bearish' | 'watch';

export type MarketWatchlistItem = {
  id: number;
  symbol: string;
  name: string;
  asset_type: 'stock' | 'etf' | 'crypto' | 'index';
  exchange: string;
  currency: string;
  notes: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type MarketWatchlistPayload = Omit<MarketWatchlistItem, 'id' | 'created_at' | 'updated_at'>;

export type MarketReport = {
  id: number;
  symbol: string;
  report_date: string;
  signal: MarketSignal;
  confidence: number;
  price: number | null;
  change_percent: number | null;
  volume: number | null;
  summary: string;
  positive_factors: string[];
  negative_factors: string[];
  risk_factors: string[];
  news_summary: string;
  ai_raw_json: unknown;
  status: 'ok' | 'degraded' | 'error';
  error: string;
  quote_provider?: string;
  news_provider?: string;
  analysis_source?: 'llm' | 'heuristic' | 'error' | '';
  data_quality?: 'real' | 'partial' | 'error' | 'unknown';
  created_at: string;
  news?: MarketNews[];
  disclaimer?: string;
};

export type MarketNews = {
  id?: number;
  symbol: string;
  title: string;
  source: string;
  url: string;
  published_at: string | null;
  sentiment: string;
  summary: string;
  created_at?: string;
};

export type MarketSummary = {
  watchlist_count: number;
  enabled_count: number;
  signals: Record<MarketSignal, number>;
  top_gainers: MarketReport[];
  top_losers: MarketReport[];
  latest_reports: MarketReport[];
  disclaimer: string;
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
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
  login: (username: string, password: string) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  me: () => request<{ user: { username: string } }>('/api/auth/me'),
  settings: () => request<SettingsInfo>('/api/settings'),
  marketSummary: () => request<MarketSummary>('/api/market/summary'),
  marketWatchlist: async () => (await request<{ items: MarketWatchlistItem[]; disclaimer: string }>('/api/market/watchlist')).items,
  createMarketWatchlistItem: (payload: MarketWatchlistPayload) =>
    request<MarketWatchlistItem>('/api/market/watchlist', { method: 'POST', body: JSON.stringify(payload) }),
  updateMarketWatchlistItem: (id: number, payload: MarketWatchlistPayload) =>
    request<MarketWatchlistItem>(`/api/market/watchlist/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteMarketWatchlistItem: (id: number) => request<{ ok: boolean }>(`/api/market/watchlist/${id}`, { method: 'DELETE' }),
  runMarketAgent: () => request<{ status: string; reports: MarketReport[]; disclaimer: string }>('/api/market/run', { method: 'POST' }),
  analyzeMarketSymbol: (symbol: string) => request<MarketReport>(`/api/market/analyze/${encodeURIComponent(symbol)}`, { method: 'POST' }),
  marketReports: (params = new URLSearchParams()) =>
    request<{ reports: MarketReport[]; disclaimer: string }>(`/api/market/reports${params.toString() ? `?${params}` : ''}`),
  marketLatestReports: () => request<{ reports: MarketReport[]; disclaimer: string }>('/api/market/reports/latest'),
  marketSymbolReports: (symbol: string) =>
    request<{ reports: MarketReport[]; news: MarketNews[]; disclaimer: string }>(`/api/market/reports/${encodeURIComponent(symbol)}`),
  marketLatestSymbolReport: (symbol: string) =>
    request<{ report: MarketReport; news: MarketNews[]; disclaimer: string }>(`/api/market/reports/${encodeURIComponent(symbol)}/latest`),
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
  mywellnessStatus: () => request<AgentStatus>('/api/mywellness/status'),
  startMywellnessAgent: (mode: 'prepare' | 'book' = 'prepare') =>
    request<AgentStatus>('/api/agent/start', { method: 'POST', body: JSON.stringify({ mode }) }),
  stopMywellnessAgent: () => request<AgentStatus>('/api/agent/stop', { method: 'POST' }),
  enableMywellnessAgent: () => request<AgentStatus>('/api/mywellness/enable', { method: 'POST' }),
  disableMywellnessAgent: () => request<AgentStatus>('/api/mywellness/disable', { method: 'POST' }),
  toggleMywellnessAgent: () => request<AgentStatus>('/api/mywellness/toggle', { method: 'POST' }),
  updateMywellnessSettings: (payload: MyWellnessSettingsPayload) =>
    request<AgentStatus>('/api/mywellness/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  runMywellnessPrepare: (dryRun = false) =>
    request<{ result: unknown; status: AgentStatus }>('/api/mywellness/run/prepare', { method: 'POST', body: JSON.stringify({ dry_run: dryRun }) }),
  runMywellnessBook: (dryRun = false) =>
    request<{ result: unknown; status: AgentStatus }>('/api/mywellness/run/book', { method: 'POST', body: JSON.stringify({ dry_run: dryRun }) }),
  mywellnessCourses: async () => (await request<{ courses: MyWellnessCourse[]; error?: string }>('/api/mywellness/courses')).courses,
  mywellnessUpcomingCourses: async () => (await request<{ courses: Course[]; error?: string }>('/api/mywellness/courses/upcoming')).courses,
  mywellnessBookings: async () => (await request<{ bookings: Course[]; error?: string }>('/api/mywellness/bookings')).bookings,
  bookMywellnessCourse: (courseId: string) =>
    request<{ ok: boolean; message: string; course: Course }>('/api/mywellness/book', { method: 'POST', body: JSON.stringify({ courseId }) }),
  cancelMywellnessCourse: (courseId: string) =>
    request<{ ok: boolean; message: string; course: Course }>('/api/mywellness/cancel', { method: 'POST', body: JSON.stringify({ courseId }) }),
  mywellnessLogs: async () => request<{ items?: MyWellnessLog[]; logs: string[] }>('/api/mywellness/logs'),
  upload: async (file: File) => {
    const data = new FormData();
    data.append('file', file);
    const token = getAuthToken();
    const response = await fetch(`${API_BASE}/api/invoices/upload`, {
      method: 'POST',
      body: data,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  },
  fileUrl: (id: number) => `${API_BASE}/api/invoices/${id}/file`,
  exportUrl: (scope: 'year' | 'month', year: number, month: number | null, type: 'excel' | 'pdf' | 'zip') =>
    scope === 'year'
      ? `${API_BASE}/api/invoices/exports/year/${year}/${type}`
      : `${API_BASE}/api/invoices/exports/month/${year}/${month}/${type}`,
};
