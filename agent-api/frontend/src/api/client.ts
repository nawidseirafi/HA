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
  is_running: boolean;
  current_status: string;
  last_successful_run: string | null;
  next_scheduled_run: string | null;
  last_error: string | null;
  last_started_at?: string | null;
  last_finished_at?: string | null;
  last_mode?: 'prepare' | 'book';
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
  mywellnessStatus: () => request<AgentStatus>('/api/agent/status'),
  startMywellnessAgent: (mode: 'prepare' | 'book' = 'prepare') =>
    request<AgentStatus>('/api/agent/start', { method: 'POST', body: JSON.stringify({ mode }) }),
  stopMywellnessAgent: () => request<AgentStatus>('/api/agent/stop', { method: 'POST' }),
  mywellnessCourses: async () => (await request<{ courses: MyWellnessCourse[]; error?: string }>('/api/mywellness/courses')).courses,
  mywellnessUpcomingCourses: async () => (await request<{ courses: Course[]; error?: string }>('/api/mywellness/courses/upcoming')).courses,
  mywellnessBookings: async () => (await request<{ bookings: Course[]; error?: string }>('/api/mywellness/bookings')).bookings,
  bookMywellnessCourse: (courseId: string) =>
    request<{ ok: boolean; message: string; course: Course }>('/api/mywellness/book', { method: 'POST', body: JSON.stringify({ courseId }) }),
  cancelMywellnessCourse: (courseId: string) =>
    request<{ ok: boolean; message: string; course: Course }>('/api/mywellness/cancel', { method: 'POST', body: JSON.stringify({ courseId }) }),
  mywellnessLogs: async () => (await request<{ logs: string[] }>('/api/mywellness/logs')).logs,
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
      ? `${API_BASE}/api/exports/year/${year}/${type}`
      : `${API_BASE}/api/exports/month/${year}/${month}/${type}`,
};
