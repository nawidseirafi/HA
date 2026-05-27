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
  next_scheduled_action?: 'prepare' | 'book' | null;
  last_error: string | null;
  last_started_at?: string | null;
  last_finished_at?: string | null;
  last_mode?: 'prepare' | 'book';
  schedule?: string[];
  updated_at?: string | null;
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

export type MyWellnessHealthSettings = {
  id?: number;
  enabled: boolean;
  profile_birth_date?: string;
  profile_supplements?: string;
  profile_notes?: string;
  ha_entity_steps?: string;
  ha_entity_active_calories?: string;
  ha_entity_resting_heart_rate?: string;
  ha_entity_hrv?: string;
  ha_entity_sleep_hours?: string;
  ha_entity_weight?: string;
  ha_entity_blood_pressure_systolic?: string;
  ha_entity_blood_pressure_diastolic?: string;
  ha_entity_withings_weight?: string;
  ha_entity_withings_bmi?: string;
  ha_entity_withings_fat_mass?: string;
  ha_entity_withings_muscle_mass?: string;
  ha_entity_withings_body_water?: string;
  ha_entity_withings_heart_rate?: string;
  ha_entity_withings_systolic_blood_pressure?: string;
  ha_entity_withings_diastolic_blood_pressure?: string;
  ha_entity_withings_sleep_score?: string;
  ha_entity_withings_sleep_duration?: string;
  ha_entity_withings_deep_sleep?: string;
  ha_entity_withings_light_sleep?: string;
  ha_entity_withings_rem_sleep?: string;
  updated_at?: string;
};

export type MyWellnessHealthMetrics = {
  id: number;
  metric_date: string;
  source: string;
  steps?: number | null;
  active_calories?: number | null;
  resting_heart_rate?: number | null;
  hrv?: number | null;
  sleep_hours?: number | null;
  weight?: number | null;
  blood_pressure_systolic?: number | null;
  blood_pressure_diastolic?: number | null;
  bmi?: number | null;
  fat_mass?: number | null;
  muscle_mass?: number | null;
  body_water?: number | null;
  sleep_score?: number | null;
  deep_sleep_hours?: number | null;
  light_sleep_hours?: number | null;
  rem_sleep_hours?: number | null;
  raw_json?: unknown;
  created_at: string;
  updated_at: string;
};

export type MyWellnessRecoveryReport = {
  id: number;
  report_date: string;
  recovery_score: number;
  stress_score: number;
  training_readiness: number;
  recovery_state: 'low' | 'medium' | 'high';
  stress_level: 'low' | 'medium' | 'high';
  should_train_today: boolean;
  recommended_workout_type?: string | null;
  summary?: string | null;
  recommendation?: string | null;
  warnings?: string[];
  ai_raw_json?: unknown;
  created_at: string;
};

export type MyWellnessHealthStatus = {
  enabled: boolean;
  ha_configured: boolean;
  settings: MyWellnessHealthSettings;
  latest_metrics: MyWellnessHealthMetrics | null;
  latest_report: MyWellnessRecoveryReport | null;
};

export type WithingsEntityCandidate = {
  entity_id: string;
  name?: string;
  state?: string | number | null;
  unit?: string | null;
  device_class?: string | null;
  suggested_metric?: keyof MyWellnessHealthSettings | '';
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
  source?: 'prepare' | 'live' | string;
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
    log_file: PathSetting;
  };
  agents: {
    invoices: {
      enabled: boolean;
      upload_dir: PathSetting;
      database: PathSetting;
      schedule: string[];
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

export type WallEntity = {
  entity_id: string;
  name: string;
  state: string;
  area: string;
  device_class?: string | null;
  unit?: string | null;
};

export type WallLight = WallEntity & {
  on: boolean;
  brightness_pct?: number | null;
  supported_color_modes?: string[];
};

export type WallLightGroup = {
  area: string;
  total: number;
  on: number;
  items: WallLight[];
  rooms: WallLightRoom[];
};

export type WallLightRoom = {
  area: string;
  total: number;
  on: number;
  items: WallLight[];
};

export type WallClimate = WallEntity & {
  current_temperature?: number | null;
  target_temperature?: number | null;
  humidity?: number | null;
  hvac_action?: string | null;
};

export type WallDashboardData = {
  updated_at: string;
  home_assistant: { configured: boolean; entity_count: number };
  weather: WallEntity | null;
  lights: WallLight[];
  light_groups: WallLightGroup[];
  switches: WallEntity[];
  climate: WallClimate[];
  security: {
    openings_total: number;
    openings_open: number;
    openings: WallEntity[];
    problems: WallEntity[];
  };
  health: {
    battery_total: number;
    batteries: Array<WallEntity & { level?: number | null }>;
    low_batteries: Array<WallEntity & { level?: number | null }>;
    unavailable: WallEntity[];
  };
  agents: {
    invoices: {
      status: string;
      total?: number;
      needs_review?: number;
      errors?: number;
      enabled?: boolean;
      is_running?: boolean;
      next_scheduled_run?: string | null;
      schedule?: string[];
      last_status?: string;
      error?: string;
    };
    mywellness: Partial<AgentStatus> & { status?: string; error?: string };
    market: { status: string; watchlist_count?: number; enabled_count?: number; signals?: Record<string, number>; error?: string };
  };
};

function apiUrl(path: string) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  if (!API_BASE) return normalizedPath;
  try {
    return new URL(normalizedPath, API_BASE).toString();
  } catch {
    throw new Error(`API-Adresse ist ungueltig: ${API_BASE}`);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers ?? {}),
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(message === 'The string did not match the expected pattern.'
      ? 'API-Adresse konnte vom Browser nicht verarbeitet werden. Bitte VITE_API_BASE pruefen oder leer lassen, wenn Frontend und Backend auf demselben Port laufen.'
      : message + 'hallo');
  }
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

async function download(path: string): Promise<{ blob: Blob; filename: string }> {
  const token = getAuthToken();
  const response = await fetch(apiUrl(path), {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Download failed: ${response.status}`);
  }
  const disposition = response.headers.get('content-disposition') || '';
  const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] || path.split('/').filter(Boolean).pop() || 'export',
  };
}

export const api = {
  login: (username: string, password: string) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  me: () => request<{ user: { username: string } }>('/api/auth/me'),
  settings: () => request<SettingsInfo>('/api/settings'),
  wallDashboard: () => request<WallDashboardData>('/api/homeassistant/wall'),
  callHomeAssistantService: (payload: { domain: string; service: string; entity_id?: string | string[]; data?: Record<string, unknown> }) =>
    request<{ ok: boolean; result: unknown }>('/api/homeassistant/service', { method: 'POST', body: JSON.stringify(payload) }),
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
  runAgent: () => request<{ status: string; command: string; cwd: string; stdout: string; stderr: string }>('/api/invoices/run', { method: 'POST' }),
  invoiceAgentStatus: () => request<AgentStatus>('/api/invoices/agent/status'),
  enableInvoiceAgent: () => request<AgentStatus>('/api/invoices/agent/enable', { method: 'POST' }),
  disableInvoiceAgent: () => request<AgentStatus>('/api/invoices/agent/disable', { method: 'POST' }),
  toggleInvoiceAgent: () => request<AgentStatus>('/api/invoices/agent/toggle', { method: 'POST' }),
  updateInvoiceAgentSettings: (payload: { enabled?: boolean; schedule?: string[] }) =>
    request<AgentStatus>('/api/invoices/agent/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  cleanupArchive: (apply = false) =>
    request<{
      applied: boolean;
      archive_files: number;
      db_references: number;
      unreferenced: number;
      missing: number;
      moved: number;
      backup_dir: string | null;
      unreferenced_examples: string[];
      missing_examples: string[];
    }>(`/api/invoices/cleanup-archive?apply=${apply ? 'true' : 'false'}`, { method: 'POST' }),
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
  mywellnessHealthStatus: () => request<MyWellnessHealthStatus>('/api/mywellness/health/status'),
  mywellnessHealthMetrics: async () =>
    (await request<{ metrics: MyWellnessHealthMetrics[] }>('/api/mywellness/health/metrics')).metrics,
  importMywellnessHealthFromHa: () =>
    request<{ metrics: MyWellnessHealthMetrics; errors: string[] }>('/api/mywellness/health/import-from-ha', { method: 'POST' }),
  analyzeMywellnessHealth: () =>
    request<{ report: MyWellnessRecoveryReport; metrics: MyWellnessHealthMetrics }>('/api/mywellness/health/analyze', { method: 'POST' }),
  mywellnessLatestHealthReport: () => request<{ report: MyWellnessRecoveryReport | null }>('/api/mywellness/health/latest-report'),
  mywellnessHealthReports: async () =>
    (await request<{ reports: MyWellnessRecoveryReport[] }>('/api/mywellness/health/reports')).reports,
  updateMywellnessHealthSettings: (payload: Partial<MyWellnessHealthSettings>) =>
    request<MyWellnessHealthSettings>('/api/mywellness/health/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  mywellnessWithingsEntities: () => request<{ entities: Record<string, string>; configured: boolean }>('/api/mywellness/health/withings/entities'),
  discoverMywellnessWithingsEntities: () =>
    request<{ candidates: WithingsEntityCandidate[]; error?: string }>('/api/mywellness/health/withings/discover', { method: 'POST' }),
  importMywellnessWithings: () =>
    request<{ metrics: MyWellnessHealthMetrics; missing: string[]; mapping_source?: string }>('/api/mywellness/health/withings/import', { method: 'POST' }),
  mywellnessLatestWithings: () => request<{ metrics: MyWellnessHealthMetrics | null }>('/api/mywellness/health/withings/latest'),
  upload: async (file: File) => {
    const data = new FormData();
    data.append('file', file);
    const token = getAuthToken();
    const response = await fetch(apiUrl('/api/invoices/upload'), {
      method: 'POST',
      body: data,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  },
  fileUrl: (id: number) => apiUrl(`/api/invoices/${id}/file`),
  exportUrl: (scope: 'year' | 'month', year: number, month: number | null, type: 'excel' | 'pdf' | 'zip') =>
    scope === 'year'
      ? apiUrl(`/api/invoices/exports/year/${year}/${type}`)
      : apiUrl(`/api/invoices/exports/month/${year}/${month}/${type}`),
  downloadExport: (scope: 'year' | 'month', year: number, month: number | null, type: 'excel' | 'pdf' | 'zip') =>
    download(scope === 'year'
      ? `/api/invoices/exports/year/${year}/${type}`
      : `/api/invoices/exports/month/${year}/${month}/${type}`),
};
