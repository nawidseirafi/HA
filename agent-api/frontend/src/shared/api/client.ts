import type { Contract, ContractAnalysis, ContractReminder, FinanceSummary, Invoice, MonthSummary, Summary, YearSummary } from '@shared/types/invoice';

const RAW_API_BASE = import.meta.env.VITE_API_BASE ?? '';
const API_BASE = normalizeApiBase(RAW_API_BASE);
const TOKEN_KEY = 'robotersteve.agent-api.token';
const SESSION_TOKEN_KEY = 'robotersteve.agent-api.session-token';
export const AUTH_EXPIRED_EVENT = 'robotersteve:auth-expired';

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

export function notifyAuthExpired() {
  clearAuthToken();
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
}

export function handleUnauthorizedResponse(response: Response) {
  if (response.status !== 401) return false;
  notifyAuthExpired();
  return true;
}

export type AgentStatus = {
  enabled: boolean;
  prepare_enabled?: boolean;
  booking_enabled?: boolean;
  health_sync_enabled?: boolean;
  prepare_time?: string;
  booking_time?: string;
  health_sync_time?: string;
  days?: number;
  desired_courses?: string[];
  is_running: boolean;
  current_status: string;
  last_status?: string;
  last_successful_run: string | null;
  last_prepare_run?: string | null;
  last_booking_run?: string | null;
  last_health_sync_run?: string | null;
  next_scheduled_run: string | null;
  next_scheduled_action?: 'prepare' | 'book' | 'health_sync' | null;
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
  health_sync_enabled?: boolean;
  prepare_time?: string;
  booking_time?: string;
  health_sync_time?: string;
  days?: number;
  desired_courses?: string[];
};

export type AgentManifest = {
  id: string;
  name: string;
  description: string;
  icon: string;
  enabled: boolean;
  status: string;
  dashboard_route?: string | null;
  api_prefix: string;
  settings: Record<string, unknown>;
};

export type AgentsResponse = {
  agents: AgentManifest[];
};

export type ProductInfo = {
  id: string;
  name: string;
  description: string;
  frontend_app: string;
};
export type SystemVersion = {
  product: string;
  app_version?: string;
  version: string;
  build: string;
  commit: string;
  docker_version?: string;
  docker_compose_version?: string;
  ollama_version?: string;
  homeassistant_version?: string;
  os_version?: string;
  channel?: string;
  previous_version?: string | null;
  updated_at?: string | null;
};

export type UpdateLatest = {
  latest_version: string;
  download_url: string;
  mandatory: boolean;
  release_notes: string[] | string;
  channel: string;
  layers: string[];
};

export type UpdateStep = {
  key: string;
  label: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'completed' | 'error' | string;
  detail?: string;
};

export type UpdateStatus = {
  product?: string;
  current_version?: string;
  latest_version?: string | null;
  status?: string;
  last_checked?: string | null;
  release_notes?: string[] | string;
  steps?: UpdateStep[];
  dev_mode?: boolean;
  state?: string;
  current_step?: number;
  progress?: number;
  message?: string;
  version?: SystemVersion;
  channel?: 'stable' | 'beta' | 'dev' | string;
  layers?: string[];
  execution_mode?: string;
  update_server_url?: string;
  last_check?: string | null;
  latest?: UpdateLatest | null;
  update_available: boolean;
  install: {
    status: string;
    layer?: string;
    target_version?: string;
    steps: UpdateStep[];
    started_at?: string;
    finished_at?: string;
  };
  rollback: {
    status?: string;
    available?: boolean;
    previous_version?: string | null;
    target_version?: string;
    steps?: UpdateStep[];
  };
  last_error?: string | null;
  backup?: { path: string; created_at: string } | null;
};

export type UpdateCheckResult = {
  ok: boolean;
  offline: boolean;
  product?: string;
  current?: SystemVersion;
  current_version?: string;
  channel?: string;
  latest?: UpdateLatest | null;
  available?: boolean;
  update_available: boolean;
  latest_version?: string;
  release_notes?: string[] | string;
  checked_at?: string;
  last_checked?: string;
  status?: string;
  message: string;
  error?: string;
};

export type KnownDashboardRoute = 'invoiceDashboard' | 'mywellnessDashboard' | 'marketDashboard' | 'vacationDashboard' | 'schedulerDashboard';

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
      registry_enabled?: boolean | null;
      api_prefix?: string;
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
      registry_enabled?: boolean | null;
      api_prefix?: string;
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
      registry_enabled?: boolean | null;
      api_prefix?: string;
      database: PathSetting;
      mode_entity?: string;
      dry_run_default?: boolean;
    };
    market?: {
      enabled: boolean;
      registry_enabled?: boolean | null;
      api_prefix?: string;
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
      url_configured?: boolean;
      notifications_enabled: boolean;
      notify_service: string;
      persistent_notifications: boolean;
    };
    household?: {
      post_entity: string;
      waste_source: string;
      vacation_source: string;
      infrastructure_source: string;
    };
    infrastructure?: {
      source: string;
      direct_fritzbox_api: boolean;
      auto_discovery: boolean;
      entities: Record<string, string>;
    };
  };
  security: {
    secrets_visible: boolean;
    note: string;
  };
};

export type MarketSignal = 'buy' | 'hold' | 'sell' | 'watch';

export type MarketWatchlistItem = {
  id: number;
  input_name?: string;
  symbol: string;
  name: string;
  resolved_name?: string;
  isin?: string;
  wkn?: string;
  asset_type: 'stock' | 'etf' | 'fund' | 'etc' | 'crypto' | 'index';
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
  recommendation?: MarketSignal;
  confidence: number;
  risk_level?: 'low' | 'medium' | 'high';
  price: number | null;
  change_percent: number | null;
  volume: number | null;
  summary: string;
  reasoning?: string;
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
  asset_type?: 'stock' | 'etf' | 'fund' | 'etc' | 'crypto' | 'index';
  report_type?: 'watchlist' | 'discovery';
  performance_json?: Record<string, number | null>;
  technical_json?: Record<string, unknown>;
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

export type MarketSignalHistoryItem = {
  id: number;
  symbol: string;
  signal: MarketSignal;
  confidence: number;
  summary: string;
  report_id?: number | null;
  created_at: string;
};

export type MarketSummary = {
  agent?: {
    enabled: boolean;
    current_status?: string;
    status?: string;
    last_error?: string | null;
  };
  watchlist_count: number;
  enabled_count: number;
  signals: Record<MarketSignal, number>;
  top_gainers: MarketReport[];
  top_losers: MarketReport[];
  latest_reports: MarketReport[];
  discovery_reports?: MarketReport[];
  disclaimer: string;
};

export type MessageSeverity = 'info' | 'warning' | 'critical';

export type MessageCenterItem = {
  id: number;
  source: string;
  category: string;
  severity: MessageSeverity;
  title: string;
  message: string;
  payload?: Record<string, unknown>;
  read: boolean;
  created_at: string;
  read_at?: string | null;
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

export type WallCover = WallEntity & {
  position?: number | null;
  supported_features?: number | null;
};

export type WallFan = WallEntity & {
  percentage?: number | null;
  percentage_step?: number | null;
  preset_mode?: string | null;
  preset_modes?: string[];
  oscillating?: boolean | null;
  direction?: string | null;
  supported_features?: number | null;
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

export type WallTemperatureSensor = WallEntity & {
  temperature?: number | null;
  humidity?: number | null;
};

export type WallWeather = WallEntity & {
  temperature?: number | null;
  humidity?: number | null;
};

export type WasteItem = {
  type: string;
  date?: string | null;
  date_de?: string | null;
  days_until?: number | null;
  label: string;
  icon: string;
  color: string;
};

export type WasteStatus = {
  ok: boolean;
  updated_at: string;
  next: WasteItem | null;
  items: WasteItem[];
  context: {
    vacation_mode?: boolean | null;
    mailbox_has_mail?: boolean | null;
  };
  reminders: Array<{
    priority: 'high' | 'medium' | 'low';
    message: string;
    reason: string;
  }>;
  source_entity: string;
  stale?: boolean;
  error?: string;
  raw?: unknown;
};

export type HouseholdReminder = {
  priority: 'critical' | 'high' | 'medium' | 'low' | string;
  message: string;
  reason: string;
  source?: string;
};

export type CalendarEventSummary = {
  title: string;
  start: string;
  end?: string | null;
  location?: string | null;
  source?: string;
};

export type CalendarSummary = {
  ok?: boolean;
  updated_at?: string;
  today_count: number;
  next_event: CalendarEventSummary | null;
  upcoming: CalendarEventSummary[];
  source?: string;
  error?: string;
};

export type HouseholdStatus = {
  ok: boolean;
  updated_at: string;
  home_assistant?: { configured: boolean };
  waste: WasteStatus;
  post: {
    ok: boolean;
    entity_id: string;
    has_mail: boolean | null;
    entity: WallEntity | null;
    error?: string;
  };
  vacation: Record<string, unknown> & {
    ok?: boolean;
    available?: boolean;
    vacation_mode?: boolean | null;
    error?: string;
  };
  infrastructure: InfrastructureSummary;
  calendar?: CalendarSummary;
  reminders: HouseholdReminder[];
};

export type HouseholdSummary = Pick<HouseholdStatus, 'ok' | 'updated_at' | 'waste' | 'post' | 'vacation' | 'reminders'> & {
  infrastructure: InfrastructureSummary;
  calendar?: CalendarSummary;
  counts: {
    reminders: number;
    high_priority: number;
    waste_items: number;
    calendar_events_today?: number;
  };
  state: {
    mailbox_has_mail?: boolean | null;
    vacation_mode?: boolean | null;
    next_waste?: WasteItem | null;
    next_calendar_event?: CalendarEventSummary | null;
    infrastructure_status?: InfrastructureStatus;
  };
};

export type InfrastructureStatus = 'ok' | 'down' | 'unstable' | 'warning' | 'critical' | 'unknown';
export type InfrastructureOnlineStatus = 'online' | 'offline' | 'unstable' | 'unknown';

export type InfrastructureCheck = {
  key: 'internet_status' | 'fritzbox_status' | 'connected_devices' | 'wifi_status' | string;
  configured: boolean;
  discovered?: boolean;
  entity_id: string;
  status: InfrastructureStatus;
  value: string | number | boolean | null;
  label: string;
  unit?: string | null;
  attributes?: Record<string, unknown>;
  error?: string;
};

export type InfrastructureSummary = {
  ok: boolean;
  updated_at: string;
  status: InfrastructureStatus;
  title?: string;
  subtitle?: string;
  label: string;
  detail: string;
  router: string;
  connected_devices: number | null;
  outages_24h?: number;
  outage_duration_24h_seconds?: number;
  last_outage?: Record<string, unknown> | null;
  wifi: InfrastructureStatus;
  checks: Record<string, InfrastructureCheck>;
};

export type InfrastructureFullStatus = {
  ok: boolean;
  updated_at: string;
  internet?: {
    status: InfrastructureOnlineStatus;
    source: string;
    updated_at: string;
  };
  fritzbox?: {
    status: 'online' | 'offline' | 'unknown';
    model?: string | null;
    uptime?: string | number | null;
    external_ip?: string | number | null;
  };
  wifi?: {
    status: 'online' | 'offline' | 'unknown';
  };
  traffic?: {
    upload?: string | null;
    download?: string | null;
  };
  connected_devices?: number | null;
  home_assistant: { configured: boolean };
  configured_entities: Record<string, string>;
  checks: Record<string, InfrastructureCheck>;
  summary: Omit<InfrastructureSummary, 'ok' | 'updated_at' | 'checks'>;
};

export type WallDashboardData = {
  updated_at: string;
  home_assistant: { configured: boolean; entity_count: number };
  weather: WallWeather | null;
  post?: WallEntity | null;
  waste?: WasteStatus | null;
  calendar?: CalendarSummary | null;
  lights: WallLight[];
  light_groups: WallLightGroup[];
  covers?: WallCover[];
  sensors?: WallEntity[];
  switches: WallEntity[];
  fans?: WallFan[];
  media_players?: WallEntity[];
  climate: WallClimate[];
  temperature_sensors: WallTemperatureSensor[];
  climate_summary?: {
    house_temp?: number | null;
    house_humidity?: number | null;
    basement_temp?: number | null;
    basement_humidity?: number | null;
  };
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
  agents: Record<string, Record<string, unknown> | undefined> & {
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
    vacation?: {
      status?: string;
      current_status?: string;
      vacation_mode?: boolean | { active?: boolean | null; source?: string; updated_at?: string | null } | null;
      vacation_mode_active?: boolean | null;
      history_active?: boolean;
      open_reminders?: number;
      ai_analysis?: VacationAIAnalysis | null;
      error?: string;
    };
  };
  household?: HouseholdSummary;
};

export type VacationReminder = {
  id: number;
  reminder_type?: string | null;
  title?: string | null;
  message?: string | null;
  status?: string | null;
  severity?: string | null;
  due_at?: string | null;
  created_at: string;
};

export type VacationEvent = {
  id: number;
  event_type: string;
  severity: string;
  message: string;
  payload?: Record<string, unknown>;
  created_at: string;
};

export type VacationPeriod = {
  id: number;
  start_date?: string | null;
  end_date?: string | null;
  source?: string | null;
  active: number | boolean;
  payload?: Record<string, unknown>;
  created_at: string;
};

export type PresenceProfile = {
  id: number;
  room?: string | null;
  weekday?: number | null;
  avg_on_time?: string | null;
  avg_off_time?: string | null;
  confidence?: number | null;
  updated_at: string;
};

export type VacationStatus = {
  agent?: {
    enabled: boolean;
    status: string;
    last_run?: string | null;
    last_check?: string | null;
    last_error?: string | null;
    scheduler_running?: boolean;
    schedule_times?: string[];
    last_scheduled_run?: string | null;
  };
  vacation_mode?: {
    active?: boolean | null;
    source?: string;
    updated_at?: string | null;
    error?: string | null;
  };
  period?: {
    start_date?: string | null;
    end_date?: string | null;
    source?: string | null;
    title?: string | null;
    calendar_entity?: string | null;
    duration_days?: number | null;
  };
  summary?: {
    reminders: number;
    events: number;
    profiles: number;
  };
  ai_analysis?: VacationAIAnalysis | null;
  enabled: boolean;
  current_status: string;
  vacation_mode_active?: boolean | null;
  mode_entity?: string;
  calendar_entity?: string | null;
  calendar_source?: string | null;
  calendar_error?: string | null;
  calendar_candidates?: Array<{ entity_id: string; name?: string; score?: number; matched_events?: number }>;
  active_period?: VacationPeriod | null;
  history_active?: boolean;
  reminders?: VacationReminder[];
  open_reminders?: number;
  last_run?: Record<string, unknown> | null;
  last_error?: string | null;
  database_path?: string;
  log_path?: string;
};

export type VacationAIAnalysis = {
  id: number;
  summary: string;
  risk_level: 'low' | 'medium' | 'high';
  recommendations: string[];
  warnings: string[];
  travel_preparation_score: number;
  trigger?: string | null;
  fallback?: boolean;
  error?: string | null;
  created_at: string;
};

export type VacationHistory = {
  periods: VacationPeriod[];
  events: VacationEvent[];
  reminders: VacationReminder[];
  presence_profiles: PresenceProfile[];
  ai_analyses?: VacationAIAnalysis[];
};

export type VacationProfilesResponse = {
  status: string;
  analyzed_days: number;
  profile_count: number;
  confidence: number;
  profiles: PresenceProfile[];
};

export type OrchestratorMapStatus = 'active' | 'running' | 'paused' | 'error' | 'disabled';
export type AgentControlAction = 'status' | 'start' | 'stop' | 'enable' | 'disable' | 'toggle' | 'run';
export type SchedulerScheduleType = 'once' | 'recurring' | 'cron' | 'condition';
export type SchedulerTask = {
  id: number;
  name: string;
  description: string;
  enabled: boolean;
  schedule_type: SchedulerScheduleType;
  schedule: Record<string, unknown>;
  next_run: string | null;
  last_run: string | null;
  target_agent: string;
  target_action: string;
  action_type: string;
  action_payload: Record<string, unknown>;
  source?: string;
  default_key?: string | null;
  status: 'active' | 'disabled' | 'paused' | 'error' | string;
  failure_count: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};
export type SchedulerRun = {
  id: number;
  task_id: number | null;
  task_name: string;
  status: string;
  message: string;
  started_at: string;
  finished_at: string | null;
  payload: Record<string, unknown>;
};
export type SchedulerSummary = {
  active_tasks: number;
  total_tasks: number;
  next_run: string | null;
  next_task: SchedulerTask | null;
  today_executed: number;
  errors: number;
  updated_at: string;
};
export type SchedulerStatus = {
  enabled: boolean;
  is_running: boolean;
  current_status: string;
  status: string;
  last_error: string | null;
  last_successful_run: string | null;
  next_scheduled_run: string | null;
  scheduler_running: boolean;
  settings: Record<string, unknown>;
  summary: SchedulerSummary;
};
export type AgentControlInfo = {
  agent_id?: string;
  enabled?: boolean;
  supported: boolean;
  actions: AgentControlAction[];
};
export type AgentControlResult = {
  agent_id: string;
  action: AgentControlAction;
  ok: boolean;
  status: string;
  message: string;
  data: Record<string, unknown>;
};
export type OrchestratorMapNode = {
  id: string;
  label: string;
  subtitle: string;
  kind: 'orchestrator' | 'agent' | 'platform' | 'service';
  status: OrchestratorMapStatus;
  icon: string;
  enabled?: boolean;
  control?: AgentControlInfo;
  dashboard_route?: string | null;
  api_prefix?: string | null;
  last_run?: string;
  next_action?: string;
};
export type OrchestratorMapEdge = {
  id: string;
  from: string;
  to: string;
  kind: 'primary' | 'secondary';
  active: boolean;
  status: OrchestratorMapStatus;
};
export type OrchestratorMapData = {
  updated_at: string;
  summary: {
    active: number;
    paused: number;
    errors: number;
    last_activity: string;
    next_activity: string;
  };
  nodes: OrchestratorMapNode[];
  edges: OrchestratorMapEdge[];
};

function normalizeApiBase(value: string) {
  const trimmed = String(value || '').trim();
  if (!trimmed) return '';
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) return trimmed;
  if (trimmed.startsWith('//')) return `${window.location.protocol}${trimmed}`;
  if (trimmed.startsWith('/')) return trimmed;
  if (/^[a-z0-9.-]+(?::\d+)?(?:\/.*)?$/i.test(trimmed)) return `http://${trimmed}`;
  return trimmed;
}

function apiUrl(path: string) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  if (!API_BASE) return normalizedPath;
  try {
    return new URL(normalizedPath, API_BASE).toString();
  } catch {
    return normalizedPath;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...options,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers ?? {}),
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(message.toLowerCase().includes('string did not match')
      ? `API-Adresse konnte vom Browser nicht verarbeitet werden. Bitte VITE_API_BASE pruefen oder leer lassen, wenn Frontend und Backend auf demselben Port laufen. Aktuell: ${RAW_API_BASE || '(leer)'}`
      : message);
  }
  if (!response.ok) {
    if (path !== '/api/auth/login') {
      handleUnauthorizedResponse(response);
    }
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
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) {
    handleUnauthorizedResponse(response);
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
  product: () => request<ProductInfo>('/api/product'),
  systemVersion: () => request<SystemVersion>('/api/system/version'),
  updateStatus: () => request<UpdateStatus>('/api/system/update/status'),
  adminUpdateStatus: () => request<UpdateStatus>('/api/system/update/admin/status'),
  checkUpdates: () => request<UpdateCheckResult>('/api/system/update/check'),
  installUpdate: () => request<UpdateStatus>('/api/system/update/install', { method: 'POST', body: JSON.stringify({}) }),
  rollbackUpdate: () => request<UpdateStatus>('/api/system/update/rollback', { method: 'POST' }),  login: (username: string, password: string) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  me: () => request<{ user: { username: string } }>('/api/auth/me'),  settings: () => request<SettingsInfo>('/api/settings'),
  agents: async () => (await request<AgentsResponse>('/api/agents')).agents,
  orchestratorMap: () => request<OrchestratorMapData>('/api/orchestrator/map'),
  messages: (limit = 100) => request<{ messages: MessageCenterItem[] }>(`/api/messages?limit=${limit}`),
  unreadMessageCount: () => request<{ unread_count: number }>('/api/messages/unread-count'),
  markMessageRead: (id: number) => request<MessageCenterItem>(`/api/messages/${id}/read`, { method: 'POST' }),
  markAllMessagesRead: () => request<{ updated: number }>('/api/messages/read-all', { method: 'POST' }),
  deleteAllMessages: () => request<{ deleted: number }>('/api/messages', { method: 'DELETE' }),
  deleteMessage: (id: number) => request<{ ok: boolean }>(`/api/messages/${id}`, { method: 'DELETE' }),
  agentControl: (agentId: string) => request<AgentControlInfo>(`/api/orchestrator/agents/${agentId}/control`),
  executeAgentControl: (agentId: string, action: AgentControlAction, payload?: Record<string, unknown>) =>
    request<AgentControlResult>(`/api/orchestrator/agents/${agentId}/control/${action}`, {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
    }),
  wallDashboard: () => request<WallDashboardData>('/api/homeassistant/wall'),
  vacationStatus: () => request<VacationStatus>('/api/vacation/status'),
  enableVacationAgent: () => request<VacationStatus>('/api/vacation/enable', { method: 'POST' }),
  disableVacationAgent: () => request<VacationStatus>('/api/vacation/disable', { method: 'POST' }),
  toggleVacationAgent: () => request<VacationStatus>('/api/vacation/toggle', { method: 'POST' }),
  updateVacationSettings: (payload: { enabled?: boolean; calendar_entity?: string }) =>
    request<VacationStatus>('/api/vacation/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  vacationReminders: () => request<{ reminders: VacationReminder[] }>('/api/vacation/reminders'),
  vacationProfiles: (limit = 100) => request<VacationProfilesResponse>(`/api/vacation/profiles?limit=${limit}`),
  vacationHistory: (limit = 100) => request<VacationHistory>(`/api/vacation/history?limit=${limit}`),
  vacationAiLatest: () => request<{ analysis: VacationAIAnalysis | null }>('/api/vacation/ai/latest'),
  analyzeVacationAi: () => request<{ analysis: VacationAIAnalysis }>('/api/vacation/ai/analyze', { method: 'POST' }),
  enableVacationMode: () => request<{ ok: boolean; vacation_mode: VacationStatus['vacation_mode'] }>('/api/vacation/mode/enable', { method: 'POST' }),
  disableVacationMode: () => request<{ ok: boolean; vacation_mode: VacationStatus['vacation_mode'] }>('/api/vacation/mode/disable', { method: 'POST' }),
  toggleVacationMode: () => request<{ ok: boolean; vacation_mode: VacationStatus['vacation_mode'] }>('/api/vacation/mode/toggle', { method: 'POST' }),
  saveVacationPeriod: (payload?: { start_date?: string; end_date?: string }) =>
    request<{ ok: boolean; period: VacationPeriod; status: VacationStatus }>('/api/vacation/start', {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
    }),
  closeVacationPeriod: (payload?: { end_date?: string }) =>
    request<{ ok: boolean; ended_at: string; status: VacationStatus }>('/api/vacation/end', {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
    }),
  runVacationAgent: (payload?: Record<string, unknown>) =>
    request<AgentControlResult>('/api/orchestrator/agents/vacation/control/run', {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
    }),
  callHomeAssistantService: (payload: { domain: string; service: string; entity_id?: string | string[]; data?: Record<string, unknown> }) =>
    request<{ ok: boolean; result: unknown }>('/api/homeassistant/service', { method: 'POST', body: JSON.stringify(payload) }),
  marketSummary: () => request<MarketSummary>('/api/market/summary'),
  marketStatus: () => request<NonNullable<MarketSummary['agent']>>('/api/market/status'),
  enableMarketAgent: () => request<NonNullable<MarketSummary['agent']>>('/api/market/enable', { method: 'POST' }),
  disableMarketAgent: () => request<NonNullable<MarketSummary['agent']>>('/api/market/disable', { method: 'POST' }),
  toggleMarketAgent: () => request<NonNullable<MarketSummary['agent']>>('/api/market/toggle', { method: 'POST' }),
  marketWatchlist: async () => (await request<{ items: MarketWatchlistItem[]; disclaimer: string }>('/api/market/watchlist')).items,
  resolveMarketWatchlistInput: (q: string) =>
    request<{ asset: MarketWatchlistPayload; disclaimer: string }>(`/api/market/watchlist/resolve?q=${encodeURIComponent(q)}`),
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
    request<{ reports: MarketReport[]; news: MarketNews[]; signal_history?: MarketSignalHistoryItem[]; disclaimer: string }>(`/api/market/reports/${encodeURIComponent(symbol)}`),
  marketLatestSymbolReport: (symbol: string) =>
    request<{ report: MarketReport; news: MarketNews[]; disclaimer: string }>(`/api/market/reports/${encodeURIComponent(symbol)}/latest`),
  schedulerStatus: () => request<SchedulerStatus>('/api/scheduler/status'),
  schedulerSummary: () => request<SchedulerSummary>('/api/scheduler/summary'),
  schedulerTasks: (status = 'all') =>
    request<{ tasks: SchedulerTask[] }>(`/api/scheduler/tasks?status=${encodeURIComponent(status)}`),
  schedulerRuns: (limit = 50) => request<{ runs: SchedulerRun[] }>(`/api/scheduler/runs?limit=${limit}`),
  runScheduler: () => request<{ status: string; executed: number; runs: SchedulerRun[] }>('/api/scheduler/run', { method: 'POST' }),
  runSchedulerTask: (id: number) => request<SchedulerRun & { task: SchedulerTask }>(`/api/scheduler/tasks/${id}/run`, { method: 'POST' }),
  updateSchedulerTask: (id: number, payload: Partial<SchedulerTask>) =>
    request<SchedulerTask>(`/api/scheduler/tasks/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  enableSchedulerTask: (id: number) => request<SchedulerTask>(`/api/scheduler/tasks/${id}/enable`, { method: 'POST' }),
  disableSchedulerTask: (id: number) => request<SchedulerTask>(`/api/scheduler/tasks/${id}/disable`, { method: 'POST' }),  summary: () => request<Summary>('/api/invoices/summary'),
  financeSummary: () => request<FinanceSummary>('/api/invoices/finance/summary'),
  years: async () => (await request<{ years: YearSummary[] }>('/api/invoices/years')).years,
  year: (year: number) => request<{ year: number; months: MonthSummary[] }>(`/api/invoices/years/${year}`),
  month: (year: number, month: number, params: URLSearchParams) =>
    request<{ year: number; month: number; invoices: Invoice[] }>(`/api/invoices/years/${year}/months/${month}?${params}`),
  invoice: (id: number) => request<Invoice>(`/api/invoices/${id}`),
  updateInvoice: (id: number, payload: Partial<Invoice>) =>
    request<Invoice>(`/api/invoices/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  markReviewed: (id: number) => request<Invoice>(`/api/invoices/${id}/mark-reviewed`, { method: 'POST' }),
  reanalyze: (id: number) => request(`/api/invoices/${id}/reanalyze`, { method: 'POST' }),
  createContractFromInvoice: (id: number) => request<{ status: string; contract: Contract; invoice: Invoice }>(`/api/invoices/${id}/create-contract`, { method: 'POST' }),
  deleteInvoice: (id: number) => request(`/api/invoices/${id}`, { method: 'DELETE' }),
  contracts: (params = new URLSearchParams()) =>
    request<{ contracts: Contract[] }>(`/api/invoices/contracts${params.toString() ? `?${params}` : ''}`),
  contract: (id: number) => request<Contract>(`/api/invoices/contracts/${id}`),
  createContract: (payload: Partial<Contract>) =>
    request<Contract>('/api/invoices/contracts', { method: 'POST', body: JSON.stringify(payload) }),
  updateContract: (id: number, payload: Partial<Contract>) =>
    request<Contract>(`/api/invoices/contracts/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteContract: (id: number) => request<{ deleted: boolean; contract: Contract }>(`/api/invoices/contracts/${id}`, { method: 'DELETE' }),
  contractAnalysis: () => request<ContractAnalysis>('/api/invoices/contracts/analysis'),
  contractReminders: () => request<{ reminders: ContractReminder[] }>('/api/invoices/contracts/reminders'),
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
  wasteStatus: () => request<WasteStatus>('/api/waste/status'),
  wasteNext: () => request<{ ok: boolean; updated_at: string; next: WasteItem | null; source_entity: string; error?: string }>('/api/waste/next'),
  wasteReminders: () => request<Pick<WasteStatus, 'ok' | 'updated_at' | 'context' | 'reminders' | 'source_entity' | 'error'>>('/api/waste/reminders'),
  householdStatus: () => request<HouseholdStatus>('/api/household/status'),
  householdSummary: () => request<HouseholdSummary>('/api/household/summary'),
  householdReminders: () => request<Pick<HouseholdStatus, 'ok' | 'updated_at' | 'reminders'> & { context: Record<string, unknown> }>('/api/household/reminders'),
  infrastructureStatus: () => request<InfrastructureFullStatus>('/api/infrastructure/status'),
  infrastructureSummary: () => request<InfrastructureSummary>('/api/infrastructure/summary'),
  mywellnessCourses: async () => (await request<{ courses: MyWellnessCourse[]; error?: string }>('/api/mywellness/courses')).courses,
  mywellnessUpcomingCourses: async (refresh = false) =>
    (await request<{ courses: Course[]; error?: string }>(`/api/mywellness/courses/upcoming${refresh ? '?refresh=true' : ''}`)).courses,
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
  mywellnessLatestWithings: () => request<{ metrics: MyWellnessHealthMetrics | null }>('/api/mywellness/health/withings/latest'),  upload: async (file: File) => {
    const data = new FormData();
    data.append('file', file);
    const token = getAuthToken();
    const response = await fetch(apiUrl('/api/invoices/upload'), {
      method: 'POST',
      body: data,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    handleUnauthorizedResponse(response);
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  },
  uploadContractDocument: async (file: File) => {
    const data = new FormData();
    data.append('file', file);
    const token = getAuthToken();
    const response = await fetch(apiUrl('/api/invoices/upload/contract'), {
      method: 'POST',
      body: data,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    handleUnauthorizedResponse(response);
    if (!response.ok) throw new Error(await response.text());
    return response.json() as Promise<{ status: string; message: string; contract: Contract; invoice: Invoice }>;
  },
  uploadEbonContent: (payload: { content: string; filename?: string; source?: string }) =>
    request<{ status: string; type: string; filename: string; stored_filename: string; path: string }>('/api/invoices/upload/ebon', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
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
