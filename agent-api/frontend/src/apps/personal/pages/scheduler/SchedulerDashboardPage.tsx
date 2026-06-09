import { useEffect, useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { Activity, AlertTriangle, CalendarClock, CheckCircle2, ChevronDown, Clock3, PauseCircle, Play, RefreshCw, TimerReset } from 'lucide-react';
import { api, type SchedulerStatus, type SchedulerTask } from '@shared/api/client';

type Filter = 'all' | 'active' | 'paused' | 'error';
type SchedulerGroupStatus = 'active' | 'paused' | 'error' | 'disabled';
type SchedulerTaskGroup = {
  key: string;
  name: string;
  visibleTasks: SchedulerTask[];
  totalTasks: number;
  activeTasks: number;
  nextTask: SchedulerTask | null;
  lastTask: SchedulerTask | null;
  errorCount: number;
  status: SchedulerGroupStatus;
};

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'Alle' },
  { key: 'active', label: 'Aktiv' },
  { key: 'paused', label: 'Pausiert' },
  { key: 'error', label: 'Fehler' },
];

export function SchedulerDashboardPage() {
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [tasks, setTasks] = useState<SchedulerTask[]>([]);
  const [filter, setFilter] = useState<Filter>('all');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [editingTask, setEditingTask] = useState<SchedulerTask | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const load = async () => {
    setError('');
    try {
      const [nextStatus, taskResponse] = await Promise.all([
        api.schedulerStatus(),
        api.schedulerTasks('all'),
      ]);
      setStatus(nextStatus);
      setTasks(taskResponse.tasks);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scheduler konnte nicht geladen werden.');
    }
  };

  useEffect(() => {
    let mounted = true;
    const loadInitial = async () => {
      try {
        const [nextStatus, taskResponse] = await Promise.all([
          api.schedulerStatus(),
          api.schedulerTasks('all'),
        ]);
        if (!mounted) return;
        setStatus(nextStatus);
        setTasks(taskResponse.tasks);
      } catch (err) {
        if (mounted) setError(err instanceof Error ? err.message : 'Scheduler konnte nicht geladen werden.');
      }
    };
    loadInitial();
    const timer = window.setInterval(loadInitial, 15000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  const summary = status?.summary;
  const nextTask = summary?.next_task;
  const groups = useMemo(() => buildTaskGroups(tasks, filter), [tasks, filter]);

  const runScheduler = async () => {
    setBusy('scheduler:run');
    setMessage('');
    try {
      const result = await api.runScheduler();
      setMessage(`${result.executed} faellige Tasks ausgefuehrt.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scheduler Run fehlgeschlagen.');
    } finally {
      setBusy('');
    }
  };

  const runTask = async (task: SchedulerTask) => {
    setBusy(`${task.id}:run`);
    setMessage('');
    try {
      const result = await api.runSchedulerTask(task.id);
      setMessage(`${result.task.name} ausgefuehrt.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Task Run fehlgeschlagen.');
    } finally {
      setBusy('');
    }
  };

  const toggleTask = async (task: SchedulerTask) => {
    setBusy(`${task.id}:toggle`);
    setMessage('');
    try {
      const updated = task.enabled ? await api.disableSchedulerTask(task.id) : await api.enableSchedulerTask(task.id);
      setMessage(`${updated.name} ${updated.enabled ? 'aktiviert' : 'deaktiviert'}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Task konnte nicht aktualisiert werden.');
    } finally {
      setBusy('');
    }
  };

  const saveTaskSchedule = async (task: SchedulerTask, schedule: Record<string, unknown>) => {
    setBusy(`${task.id}:save`);
    setMessage('');
    setError('');
    try {
      const updated = await api.updateSchedulerTask(task.id, {
        schedule_type: task.schedule_type,
        schedule,
      });
      setMessage(`${updated.name} gespeichert. Scheduler ist jetzt Quelle der Wahrheit fuer diese Laufzeit.`);
      setEditingTask(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Zeitplan konnte nicht gespeichert werden.');
    } finally {
      setBusy('');
    }
  };

  const selectFilter = (nextFilter: Filter) => setFilter(nextFilter);

  const toggleGroup = (groupKey: string) => {
    setExpandedGroups((current) => ({ ...current, [groupKey]: !current[groupKey] }));
  };

  return (
    <div className="page-stack scheduler-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Scheduler Agent</span>
          <h1>Zeitsteuerung</h1>
          <p>Zentrale Planung fuer Agent-Runs, Service-Checks, wiederkehrende Aufgaben und Orchestrator-Nachrichten.</p>
        </div>
        <div className="page-actions">
          <button className="button secondary" type="button" onClick={() => load()} disabled={Boolean(busy)}>
            <RefreshCw size={18} /> Aktualisieren
          </button>
          <button className="button" type="button" onClick={runScheduler} disabled={busy === 'scheduler:run'}>
            {busy === 'scheduler:run' ? <Activity size={18} /> : <Play size={18} />} Faellige Tasks starten
          </button>
        </div>
      </header>

      {error && <section className="panel error-panel">{error}</section>}
      {message && <section className="panel agent-note"><CheckCircle2 size={20} /><span>{message}</span></section>}

      <section className="scheduler-summary-grid">
        <SummaryCard icon={<CalendarClock size={22} />} label="Aktive Tasks" value={String(summary?.active_tasks ?? 0)} detail={`${summary?.total_tasks ?? 0} gesamt`} tone="info" />
        <SummaryCard icon={<Clock3 size={22} />} label="Naechster Lauf" value={formatDateTime(summary?.next_run)} detail={nextTask ? displayTaskName(nextTask) : 'Keine Planung'} tone="success" />
        <SummaryCard icon={<TimerReset size={22} />} label="Heute ausgefuehrt" value={String(summary?.today_executed ?? 0)} detail={formatDateTime(status?.last_successful_run)} tone="neutral" />
        <SummaryCard icon={<AlertTriangle size={22} />} label="Fehler" value={String(summary?.errors ?? 0)} detail={status?.last_error ?? 'Keine Fehler'} tone={summary?.errors ? 'warning' : 'success'} />
      </section>

      <section className="panel scheduler-control-panel">
        <div>
          <span className="eyebrow">Status</span>
          <h2>{statusLabel(status)}</h2>
          <p>Der Scheduler besitzt keine Fachlogik. Er startet geplante Actions und schreibt Ausfuehrungsereignisse ins Message Center.</p>
        </div>
        <div className="scheduler-control-meta">
          <span>{status?.scheduler_running ? 'Loop aktiv' : 'Loop nicht aktiv'}</span>
          <span>{status?.enabled ? 'Enabled' : 'Disabled'}</span>
        </div>
      </section>

      <section className="scheduler-toolbar">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            className={`filter-chip ${filter === item.key ? 'active' : ''}`}
            type="button"
            onClick={() => selectFilter(item.key)}
          >
            {item.label}
          </button>
        ))}
      </section>

      <section className="scheduler-group-list">
        {groups.map((group) => {
          const expanded = Boolean(expandedGroups[group.key]);
          return (
            <article className={`scheduler-agent-group ${group.status}`} key={group.key}>
              <button className="scheduler-agent-group-head" type="button" onClick={() => toggleGroup(group.key)} aria-expanded={expanded}>
                <div className="scheduler-agent-title">
                  <span className="eyebrow">{group.totalTasks} Tasks gesamt</span>
                  <h2>{group.name}</h2>
                  <p>{group.activeTasks} aktive Tasks</p>
                </div>
                <div className="scheduler-agent-metrics">
                  <div>
                    <span>Naechster Lauf</span>
                    <strong>{formatDateTime(group.nextTask?.next_run)}</strong>
                    <small>{group.nextTask ? displayTaskName(group.nextTask) : 'Keine Planung'}</small>
                  </div>
                  <div>
                    <span>Letzter Lauf</span>
                    <strong>{formatDateTime(group.lastTask?.last_run)}</strong>
                    <small>{group.lastTask ? taskRunLabel(group.lastTask) : 'Noch kein Lauf'}</small>
                  </div>
                  <div>
                    <span>Fehler</span>
                    <strong>{group.errorCount}</strong>
                    <small>{groupStatusLabel(group.status)}</small>
                  </div>
                </div>
                <div className="scheduler-agent-state">
                  <span className={`scheduler-status-pill ${group.status}`}>{groupStatusLabel(group.status)}</span>
                  <ChevronDown className={expanded ? 'expanded' : ''} size={20} />
                </div>
              </button>

              {expanded && (
                <div className="scheduler-task-list">
                  {group.visibleTasks.map((task) => (
                    <div className={`scheduler-task-row ${task.status === 'error' ? 'error' : task.enabled ? 'active' : 'paused'}`} key={task.id}>
                      <div className="scheduler-task-row-main">
                        <TaskStatusIcon task={task} />
                        <div>
                          <strong>{displayTaskName(task)}</strong>
                          <span>{taskDescription(task)}</span>
                        </div>
                      </div>
                      <div className="scheduler-task-row-meta">
                        <span>{scheduleLabel(task)}</span>
                        <strong>{formatDateTime(task.next_run)}</strong>
                        <span>{formatDateTime(task.last_run)}</span>
                        <em>{task.status}</em>
                      </div>
                      <div className="scheduler-task-actions compact">
                        <button className="button secondary" type="button" onClick={() => runTask(task)} disabled={busy === `${task.id}:run`}>
                          {busy === `${task.id}:run` ? <Activity size={16} /> : <Play size={16} />} Jetzt starten
                        </button>
                        <button className="button secondary" type="button" onClick={() => toggleTask(task)} disabled={busy === `${task.id}:toggle`}>
                          {task.enabled ? <PauseCircle size={16} /> : <CheckCircle2 size={16} />} {task.enabled ? 'Deaktivieren' : 'Aktivieren'}
                        </button>
                        <button className="button secondary" type="button" onClick={() => setEditingTask(task)}>
                          Zeit bearbeiten
                        </button>
                      </div>
                      {task.last_error && <div className="scheduler-task-error">{task.last_error}</div>}
                    </div>
                  ))}
                </div>
              )}
            </article>
          );
        })}
        {!groups.length && <section className="panel empty-state">Keine Scheduler-Tasks fuer diesen Filter gefunden.</section>}
      </section>
      {editingTask && (
        <SchedulerEditDialog
          task={editingTask}
          busy={busy === `${editingTask.id}:save`}
          onClose={() => setEditingTask(null)}
          onSave={(schedule) => saveTaskSchedule(editingTask, schedule)}
        />
      )}
    </div>
  );
}

function SchedulerEditDialog({
  task,
  busy,
  onClose,
  onSave,
}: {
  task: SchedulerTask;
  busy: boolean;
  onClose: () => void;
  onSave: (schedule: Record<string, unknown>) => void;
}) {
  const [time, setTime] = useState(String(task.schedule?.time || '08:00').slice(0, 5));
  const [cron, setCron] = useState(String(task.schedule?.cron || '*/5 * * * *'));
  const [runAt, setRunAt] = useState(toDateTimeLocal(String(task.schedule?.run_at || task.next_run || '')));
  const isRecurring = task.schedule_type === 'recurring' || task.schedule_type === 'condition';
  const isCron = task.schedule_type === 'cron';
  const isOnce = task.schedule_type === 'once';

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (isCron) onSave({ ...task.schedule, cron });
    else if (isOnce) onSave({ ...task.schedule, run_at: fromDateTimeLocal(runAt) });
    else onSave({ ...task.schedule, time });
  };

  return (
    <div className="wellness-drawer-layer">
      <button className="wellness-drawer-backdrop" type="button" onClick={onClose} aria-label="Zeitplan schließen" />
      <aside className="wellness-settings-drawer scheduler-edit-drawer" role="dialog" aria-modal="true" aria-label="Scheduler Task bearbeiten">
        <header>
          <div>
            <span className="eyebrow">Scheduler</span>
            <h2>{displayTaskName(task)}</h2>
            <p>Diese Änderung wird im Scheduler gespeichert. Manifest-Defaults überschreiben sie nicht.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Schließen">×</button>
        </header>
        <form className="panel wellness-settings-panel" onSubmit={submit}>
          <section className="wellness-settings-section">
            <div className="wellness-settings-section-head">
              <span><Clock3 size={18} /></span>
              <div>
                <h3>{scheduleTypeLabel(task.schedule_type)}</h3>
                <p>{scheduleLabel(task)} · {task.target_agent || task.action_type} / {task.target_action || task.action_type}</p>
              </div>
            </div>
            {isRecurring && (
              <label className="wellness-field">
                <small>Uhrzeit</small>
                <input type="time" value={time} onChange={(event) => setTime(event.target.value)} required />
              </label>
            )}
            {isCron && (
              <label className="wellness-field">
                <small>Cron</small>
                <input value={cron} onChange={(event) => setCron(event.target.value)} placeholder="*/5 * * * *" required />
              </label>
            )}
            {isOnce && (
              <label className="wellness-field">
                <small>Einmaliger Lauf</small>
                <input type="datetime-local" value={runAt} onChange={(event) => setRunAt(event.target.value)} required />
              </label>
            )}
          </section>
          <div className="wellness-settings-footer">
            <button className="button primary" type="submit" disabled={busy}>
              {busy ? 'Speichere...' : 'Zeitplan speichern'}
            </button>
            <button className="button secondary" type="button" onClick={onClose}>Abbrechen</button>
          </div>
        </form>
      </aside>
    </div>
  );
}

function SummaryCard({ icon, label, value, detail, tone }: { icon: ReactNode; label: string; value: string; detail: string; tone: string }) {
  return (
    <article className={`wellness-stat-card scheduler-summary-card ${tone}`}>
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function buildTaskGroups(tasks: SchedulerTask[], filter: Filter): SchedulerTaskGroup[] {
  const grouped = new Map<string, SchedulerTask[]>();
  for (const task of tasks) {
    const key = groupKey(task);
    grouped.set(key, [...(grouped.get(key) ?? []), task]);
  }

  return Array.from(grouped.entries())
    .map(([key, groupTasks]) => {
      const sortedTasks = [...groupTasks].sort(compareTasks);
      const visibleTasks = sortedTasks.filter((task) => matchesFilter(task, filter));
      const nextTask = sortedTasks.filter((task) => task.next_run).sort(compareByDate('next_run', 'asc'))[0] ?? null;
      const lastTask = sortedTasks.filter((task) => task.last_run).sort(compareByDate('last_run', 'desc'))[0] ?? null;
      const activeTasks = sortedTasks.filter((task) => task.enabled && task.status !== 'disabled' && task.status !== 'paused').length;
      const errorCount = sortedTasks.reduce((total, task) => {
        const currentError = task.status === 'error' || task.last_error ? 1 : 0;
        return total + Math.max(currentError, Number(task.failure_count || 0));
      }, 0);
      const status = groupStatus(sortedTasks, errorCount);
      return {
        key,
        name: groupName(sortedTasks[0], key),
        visibleTasks,
        totalTasks: sortedTasks.length,
        activeTasks,
        nextTask,
        lastTask,
        errorCount,
        status,
      };
    })
    .filter((group) => group.visibleTasks.length > 0)
    .sort(compareGroups);
}

function matchesFilter(task: SchedulerTask, filter: Filter) {
  if (filter === 'all') return true;
  if (filter === 'error') return task.status === 'error' || Boolean(task.last_error);
  if (filter === 'paused') return !task.enabled || task.status === 'paused' || task.status === 'disabled';
  return task.enabled && task.status !== 'paused' && task.status !== 'disabled' && task.status !== 'error';
}

function groupStatus(tasks: SchedulerTask[], errorCount: number): SchedulerGroupStatus {
  if (errorCount > 0 || tasks.some((task) => task.status === 'error')) return 'error';
  if (tasks.every((task) => !task.enabled || task.status === 'disabled')) return 'disabled';
  if (tasks.every((task) => task.status === 'paused' || !task.enabled)) return 'paused';
  return 'active';
}

function compareGroups(a: SchedulerTaskGroup, b: SchedulerTaskGroup) {
  if (a.status === 'error' && b.status !== 'error') return -1;
  if (a.status !== 'error' && b.status === 'error') return 1;
  const nextDiff = dateValue(a.nextTask?.next_run) - dateValue(b.nextTask?.next_run);
  if (nextDiff !== 0) return nextDiff;
  return a.name.localeCompare(b.name, 'de');
}

function compareTasks(a: SchedulerTask, b: SchedulerTask) {
  const nextDiff = dateValue(a.next_run) - dateValue(b.next_run);
  if (nextDiff !== 0) return nextDiff;
  return a.name.localeCompare(b.name, 'de');
}

function compareByDate(field: 'next_run' | 'last_run', direction: 'asc' | 'desc') {
  return (a: SchedulerTask, b: SchedulerTask) => {
    const diff = dateValue(a[field]) - dateValue(b[field]);
    return direction === 'asc' ? diff : -diff;
  };
}

function dateValue(value?: string | null) {
  if (!value) return Number.MAX_SAFE_INTEGER;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? Number.MAX_SAFE_INTEGER : time;
}

function TaskStatusIcon({ task }: { task: SchedulerTask }) {
  if (task.status === 'error') return <AlertTriangle className="scheduler-task-icon warning" size={22} />;
  if (!task.enabled) return <PauseCircle className="scheduler-task-icon muted" size={22} />;
  return <CheckCircle2 className="scheduler-task-icon success" size={22} />;
}

function statusLabel(status: SchedulerStatus | null) {
  if (!status) return 'Unbekannt';
  if (status.current_status === 'running') return 'Running';
  if (status.current_status === 'disabled') return 'Disabled';
  if (status.current_status === 'error') return 'Error';
  return 'Active';
}

function targetLabel(task: SchedulerTask) {
  const agent = task.target_agent || task.action_type;
  const action = task.target_action || task.action_type;
  return `${agent}${action ? ` / ${action}` : ''}`;
}

function groupKey(task: SchedulerTask) {
  return normalizeAgentKey(deriveAgentId(task));
}

function groupName(task: SchedulerTask | undefined, key: string) {
  if (!task) return titleCase(key);
  const raw = deriveAgentId(task);
  const known: Record<string, string> = {
    invoices: 'Invoice',
    invoice: 'Invoice',
    market: 'Market',
    mywellness: 'MyWellness',
    wellness: 'MyWellness',
    household: 'Household',
    infrastructure: 'Infrastructure',
    vacation: 'Vacation',
    scheduler: 'Scheduler',
  };
  return known[normalizeAgentKey(raw)] ?? titleCase(raw);
}

function deriveAgentId(task: SchedulerTask) {
  if (task.target_agent) return task.target_agent;
  if (task.action_type === 'infrastructure_check') return 'infrastructure';
  if (task.action_type === 'household_check') return 'household';
  if (task.action_type === 'execute_action' && task.target_action) return task.target_action;
  if (task.source) return task.source;
  return task.action_type || task.target_action || 'unknown';
}

function normalizeAgentKey(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '');
}

function titleCase(value: string) {
  return value
    .replace(/[_-]+/g, ' ')
    .trim()
    .split(/\s+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ') || 'Unbekannt';
}

function groupStatusLabel(status: SchedulerGroupStatus) {
  if (status === 'active') return 'active';
  if (status === 'paused') return 'paused';
  if (status === 'error') return 'error';
  return 'disabled';
}

function taskRunLabel(task: SchedulerTask) {
  if (task.status === 'error') return 'Fehler';
  if (task.last_error) return 'Fehler';
  if (task.last_run) return 'Erfolgreich';
  return task.status;
}

function taskDescription(task: SchedulerTask) {
  const base = task.description || targetLabel(task);
  return `${base} Zeitplan: ${scheduleLabel(task)}.`;
}

function displayTaskName(task: SchedulerTask) {
  return task.name.replace(/\s+\d{1,2}:\d{2}\s*$/, '');
}

function scheduleLabel(task: SchedulerTask) {
  if (task.schedule_type === 'cron') return cronLabel(String(task.schedule?.cron || ''));
  if (task.schedule_type === 'recurring' || task.schedule_type === 'condition') {
    const time = normalizeTime(String(task.schedule?.time || ''));
    return time ? `Täglich um ${time}` : 'Wiederkehrend';
  }
  if (task.schedule_type === 'once') {
    const runAt = formatDateTime(String(task.schedule?.run_at || task.next_run || ''));
    return runAt === 'Nicht geplant' ? 'Einmalig' : `Einmalig am ${runAt}`;
  }
  return scheduleTypeLabel(task.schedule_type);
}

function cronLabel(expression: string) {
  const parts = expression.trim().split(/\s+/);
  if (parts.length !== 5) return expression || 'Cron';
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  if (hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    const minuteStep = parseStep(minute);
    if (minuteStep) return `Alle ${minuteStep} Minuten`;
    if (minute === '*') return 'Jede Minute';
  }
  if (dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    const normalized = normalizeTime(`${hour}:${minute}`);
    if (normalized) return `Täglich um ${normalized}`;
  }
  if (dayOfMonth === '*' && month === '*' && dayOfWeek !== '*') {
    const normalized = normalizeTime(`${hour}:${minute}`);
    if (normalized) return `Wöchentlich um ${normalized}`;
  }
  return `Cron ${expression}`;
}

function parseStep(value: string) {
  if (!value.startsWith('*/')) return 0;
  const parsed = Number(value.slice(2));
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 0;
}

function normalizeTime(value: string) {
  const match = value.trim().match(/^(\d{1,2}):(\d{1,2})/);
  if (!match) return '';
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) return '';
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

function scheduleTypeLabel(type: SchedulerTask['schedule_type']) {
  if (type === 'once') return 'Einmalig';
  if (type === 'recurring') return 'Wiederkehrend';
  if (type === 'cron') return 'Cron';
  if (type === 'condition') return 'Bedingt';
  return type;
}

function formatDateTime(value?: string | null) {
  if (!value) return 'Nicht geplant';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Nicht geplant';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function toDateTimeLocal(value: string) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fromDateTimeLocal(value: string) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}
