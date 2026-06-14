import { useEffect, useMemo, useRef, useState } from 'react';
import { api, type SeniorCandidate, type SeniorCandidates, type SeniorSetupStatus } from '@shared/api/client';
import { MatterPairingStep } from './MatterPairingStep';

const STEPS = ['Willkommen', 'Profil', 'Zuhause', 'Raeume', 'Sensoren', 'Kontakt', 'Hinweise', 'Fertig'];
const ROOM_OPTIONS = [
  { key: 'living_room', label: 'Wohnzimmer' },
  { key: 'kitchen', label: 'Kueche' },
  { key: 'bathroom', label: 'Bad' },
  { key: 'bedroom', label: 'Schlafzimmer' },
  { key: 'hallway', label: 'Flur' },
  { key: 'entrance', label: 'Eingang' },
];
const ROOM_LABELS = Object.fromEntries(ROOM_OPTIONS.map((room) => [room.key, room.label]));

const STEP_BY_KEY: Record<string, number> = {
  welcome: 0,
  profile: 1,
  prepare_home: 2,
  rooms: 3,
  sensors: 4,
  contacts: 5,
  notifications: 6,
  complete: 7,
};

type SensorTask = { role: string; room: string; title: string; instruction: string };
type DiscoveryUiState = {
  sessionId?: number;
  status: 'idle' | 'starting' | 'waiting' | 'needs_action' | 'found' | 'not_found' | 'confirmed' | 'error';
  message?: string;
  candidate?: SeniorCandidate | null;
  candidates?: SeniorCandidate[];
  elapsedSeconds?: number;
  remainingSeconds?: number;
  baselineStateCount?: number | null;
  currentStateCount?: number | null;
  changedCount?: number | null;
};

export function SetupWizard({ onFinish }: { onFinish: () => void }) {
  const [stepIndex, setStepIndex] = useState(0);
  const [setupStatus, setSetupStatus] = useState<SeniorSetupStatus | null>(null);
  const [profile, setProfile] = useState({ name: '', age: '', notes: '' });
  const [rooms, setRooms] = useState<string[]>(['living_room', 'kitchen', 'bathroom']);
  const [contact, setContact] = useState({ name: '', relationship: '', email: '' });
  const [notifications, setNotifications] = useState({ anomalies: true, critical: true, daily_summary: false });
  const [pairingCodes, setPairingCodes] = useState<Record<string, string>>({});
  const [discovery, setDiscovery] = useState<Record<string, DiscoveryUiState>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pollTimers = useRef<Record<string, number>>({});

  useEffect(() => {
    void loadStatus();
    return () => {
      Object.values(pollTimers.current).forEach((timer) => window.clearTimeout(timer));
    };
  }, []);

  const progress = useMemo(() => ((stepIndex + 1) / STEPS.length) * 100, [stepIndex]);
  const sensorTasks = useMemo(() => buildSensorTasks(rooms), [rooms]);
  const devMode = useMemo(() => new URLSearchParams(window.location.search).get('dev') === '1', []);

  async function loadStatus() {
    try {
      const status = await api.seniorSetupStatus();
      applyStatus(status);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  function applyStatus(status: SeniorSetupStatus) {
    setSetupStatus(status);
    if (status.selected_rooms.length) setRooms(status.selected_rooms);
    setDiscovery((current) => {
      const configured = Object.fromEntries(
        status.sensor_roles
          .filter((role) => role.configured)
          .map((role) => [role.role, {
            ...current[role.role],
            status: 'confirmed' as const,
            message: 'Sensor wurde bestaetigt und gespeichert.',
          }]),
      );
      return { ...current, ...configured };
    });
    setStepIndex(STEP_BY_KEY[status.current_step] ?? 0);
  }

  async function guarded(action: () => Promise<SeniorSetupStatus | void>) {
    setBusy(true);
    setError('');
    try {
      const status = await action();
      if (status) applyStatus(status);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function toggleRoom(room: string) {
    setRooms((current) => current.includes(room) ? current.filter((item) => item !== room) : [...current, room]);
  }

  async function next() {
    if (stepIndex === 0) return guarded(async () => api.startSeniorSetup()).then(() => setStepIndex(1));
    if (stepIndex === 1) {
      return guarded(async () => api.saveSeniorProfile({ name: profile.name, age: profile.age ? Number(profile.age) : null, notes: profile.notes })).then(() => setStepIndex(2));
    }
    if (stepIndex === 2) return setStepIndex(3);
    if (stepIndex === 3) return guarded(async () => api.saveSeniorSetupRooms(rooms)).then(() => setStepIndex(4));
    if (stepIndex === 4) return guarded(async () => api.saveSeniorSetupSensors()).then(() => setStepIndex(5));
    if (stepIndex === 5) return guarded(async () => api.saveSeniorContact(contact)).then(() => setStepIndex(6));
    if (stepIndex === 6) return guarded(async () => api.saveSeniorNotifications(notifications)).then(() => setStepIndex(7));
    return guarded(async () => api.completeSeniorSetup()).then(onFinish);
  }

  async function startPairing(task: SensorTask) {
    stopPolling(task.role);
    setDiscovery((current) => ({ ...current, [task.role]: { status: 'starting', message: 'Kopplung wird gestartet.' } }));
    setError('');
    try {
      const result = await api.startSeniorDiscovery({ role: task.role, room: task.room, pairing_code: pairingCodes[task.role] || undefined });
      const uiStatus: DiscoveryUiState['status'] = result.status === 'pairing_needs_manual_action' ? 'needs_action' : 'waiting';
      setDiscovery((current) => ({ ...current, [task.role]: { sessionId: result.session_id, status: uiStatus, message: result.message } }));
      if (uiStatus === 'waiting') schedulePoll(task.role, result.session_id, Date.now());
    } catch (err) {
      setDiscovery((current) => ({ ...current, [task.role]: { status: 'error', message: errorMessage(err) } }));
    }
  }

  function schedulePoll(role: string, sessionId: number, startedAt: number) {
    stopPolling(role);
    pollTimers.current[role] = window.setTimeout(() => {
      void readCandidates(role, sessionId, startedAt, true);
    }, 2000);
  }

  function stopPolling(role: string) {
    const timer = pollTimers.current[role];
    if (timer) window.clearTimeout(timer);
    delete pollTimers.current[role];
  }

  function applyCandidateResult(role: string, id: number, result: SeniorCandidates) {
    const found = result.status === 'signal_detected' && result.candidate && (result.candidate.score ?? result.candidate.confidence) >= 50;
    const timedOut = result.remaining_seconds === 0 || result.status === 'no_signal_detected';
    setDiscovery((current) => ({
      ...current,
      [role]: {
        ...current[role],
        sessionId: id,
        status: found ? 'found' : timedOut ? 'not_found' : 'waiting',
        message: found ? 'Sensor erkannt.' : result.message,
        candidate: result.candidate,
        candidates: result.candidates,
        elapsedSeconds: result.elapsed_seconds,
        remainingSeconds: result.remaining_seconds,
        baselineStateCount: result.baseline_state_count,
        currentStateCount: result.current_state_count,
        changedCount: result.changed_count,
      },
    }));
    return Boolean(found || timedOut);
  }

  async function readCandidates(role: string, sessionId?: number, startedAt?: number, continuePolling = false) {
    const id = sessionId ?? discovery[role]?.sessionId;
    if (!id) return;
    try {
      const result = await api.seniorDiscoveryCandidates(id, devMode);
      const done = applyCandidateResult(role, id, result);
      const elapsed = Date.now() - (startedAt ?? Date.now());
      if (continuePolling && !done && elapsed < 30000) {
        schedulePoll(role, id, startedAt ?? Date.now());
      } else {
        stopPolling(role);
      }
    } catch (err) {
      stopPolling(role);
      setDiscovery((current) => ({ ...current, [role]: { sessionId: id, status: 'error', message: errorMessage(err) } }));
    }
  }

  async function confirmSensor(role: string) {
    const state = discovery[role];
    if (!state?.sessionId || !state.candidate?.entity_id) return;
    try {
      await api.confirmSeniorDiscovery(state.sessionId, state.candidate.entity_id);
      setDiscovery((current) => ({ ...current, [role]: { ...state, status: 'confirmed', message: 'Sensor wurde bestaetigt und gespeichert.' } }));
      await loadStatus();
    } catch (err) {
      setDiscovery((current) => ({ ...current, [role]: { ...state, status: 'error', message: errorMessage(err) } }));
    }
  }

  return (
    <section className="sc-setup-page">
      <SetupStepHeader current={stepIndex + 1} total={STEPS.length} progress={progress} onBack={stepIndex > 0 ? () => setStepIndex((value) => value - 1) : undefined} />
      {error && <div className="sc-setup-error">{error}</div>}
      <div className="sc-setup-card sc-setup-card-readable">
        <p className="sc-kicker">Einrichtung</p>
        <h1>{STEPS[stepIndex]}</h1>
        {renderStep()}
        <div className="sc-setup-actions">
          <button className="sc-primary-action" type="button" onClick={() => void next()} disabled={busy}>
            {stepIndex === STEPS.length - 1 ? 'Zur Uebersicht' : 'Weiter'}
          </button>
        </div>
      </div>
    </section>
  );

  function renderStep() {
    if (stepIndex === 0) return <p>SeniorCare richtet das Zuhause Schritt fuer Schritt ein. Technische Details bleiben im Hintergrund.</p>;
    if (stepIndex === 1) return (
      <div className="sc-setup-fields">
        <input value={profile.name} onChange={(event) => setProfile((value) => ({ ...value, name: event.target.value }))} placeholder="Name" />
        <input value={profile.age} onChange={(event) => setProfile((value) => ({ ...value, age: event.target.value }))} placeholder="Alter" inputMode="numeric" />
        <textarea value={profile.notes} onChange={(event) => setProfile((value) => ({ ...value, notes: event.target.value }))} placeholder="Wichtige Hinweise optional" />
      </div>
    );
    if (stepIndex === 2) return <HomePreparation status={setupStatus} />;
    if (stepIndex === 3) return (
      <div className="sc-option-grid">
        {ROOM_OPTIONS.map((room) => (
          <button key={room.key} className={`sc-room-choice ${rooms.includes(room.key) ? 'is-active' : ''}`} type="button" onClick={() => toggleRoom(room.key)}>{room.label}</button>
        ))}
      </div>
    );
    if (stepIndex === 4) return (
      <div className="sc-sensor-list">
        <MatterPairingStep onSaved={() => void loadStatus()} />
      </div>
    );
    if (stepIndex === 5) return (
      <div className="sc-setup-fields">
        <input value={contact.name} onChange={(event) => setContact((value) => ({ ...value, name: event.target.value }))} placeholder="Name" />
        <input value={contact.relationship} onChange={(event) => setContact((value) => ({ ...value, relationship: event.target.value }))} placeholder="Beziehung" />
        <input value={contact.email} onChange={(event) => setContact((value) => ({ ...value, email: event.target.value }))} placeholder="E-Mail-Adresse" />
      </div>
    );
    if (stepIndex === 6) return (
      <div className="sc-check-list">
        {[
          ['anomalies', 'Auffaelligkeiten'],
          ['critical', 'Kritische Hinweise'],
          ['daily_summary', 'Taegliche Zusammenfassung'],
        ].map(([key, label]) => (
          <label key={key}>
            <input type="checkbox" checked={Boolean(notifications[key as keyof typeof notifications])} onChange={(event) => setNotifications((value) => ({ ...value, [key]: event.target.checked }))} />
            <span>{label}</span>
          </label>
        ))}
      </div>
    );
    return <p>Die Einrichtung ist gespeichert. Fehlende Sensoren koennen spaeter ergaenzt werden.</p>;
  }
}

function HomePreparation({ status }: { status: SeniorSetupStatus | null }) {
  const checks = [
    ['Zuhause verbunden', status?.home.connected],
    ['Sensor-Einrichtung bereit', status?.home.sensor_ready],
    ['System bereit', status?.home.system_ready],
  ];
  return <div className="sc-prep-checks">{checks.map(([label, ok]) => <div key={String(label)} className={ok ? 'is-ok' : 'is-waiting'}><span>{ok ? '✓' : '...'}</span>{label}</div>)}</div>;
}

function SensorSetupCard({ task, code, state, devMode, onCodeChange, onStart, onCheck, onConfirm }: {
  task: SensorTask;
  code: string;
  state: DiscoveryUiState;
  devMode: boolean;
  onCodeChange: (value: string) => void;
  onStart: () => void;
  onCheck: () => void;
  onConfirm: () => void;
}) {
  const canConfirm = state.status === 'found' && Boolean(state.candidate?.entity_id);
  return (
    <article className={`sc-sensor-task sc-sensor-state-${state.status}`}>
      <div>
        <p className="sc-kicker">{ROOM_LABELS[task.room] || task.room}</p>
        <h2>{task.title}</h2>
        <p>{task.instruction}</p>
      </div>
      <label className="sc-pairing-code">
        <span>Kopplungscode optional</span>
        <input value={code} onChange={(event) => onCodeChange(event.target.value)} placeholder="Code vom Geraet" />
      </label>
      <StatusText state={state} />
      <div className="sc-sensor-actions">
        <button type="button" onClick={onStart} disabled={state.status === 'starting' || state.status === 'waiting'}>{state.status === 'idle' ? 'Kopplung starten' : 'Erneut starten'}</button>
        <button type="button" onClick={onCheck} disabled={!state.sessionId || state.status === 'starting' || state.status === 'needs_action'}>Signal pruefen</button>
        <button type="button" onClick={onConfirm} disabled={!canConfirm}>Sensor bestaetigen</button>
      </div>
      {devMode && <SensorDebug state={state} />}
    </article>
  );
}

function StatusText({ state }: { state: DiscoveryUiState }) {
  if (state.status === 'idle') return <p className="sc-sensor-status">Noch nicht gestartet.</p>;
  if (state.status === 'starting') return <p className="sc-sensor-status">Kopplung wird gestartet.</p>;
  if (state.status === 'waiting') return <p className="sc-sensor-status">Kopplung gestartet. Wir warten jetzt auf ein Signal.</p>;
  if (state.status === 'needs_action') return <p className="sc-sensor-status is-bad">{state.message || 'Der Sensor konnte nicht verbunden werden. Bitte erneut versuchen.'}</p>;
  if (state.status === 'found') return <p className="sc-sensor-status is-good">Signal erkannt. Bitte bestaetigen Sie den Sensor.</p>;
  if (state.status === 'confirmed') return <p className="sc-sensor-status is-good">Sensor bestaetigt und gespeichert. Mit Weiter geht es zum naechsten Schritt.</p>;
  if (state.status === 'error') return <p className="sc-sensor-status is-bad">{state.message || 'Fehler bei der Erkennung.'}</p>;
  return <p className="sc-sensor-status is-bad">Kein eindeutiges Signal erkannt. Bitte Sensor ausloesen und erneut pruefen.</p>;
}

function SensorDebug({ state }: { state: DiscoveryUiState }) {
  const candidates = state.candidates || (state.candidate ? [state.candidate] : []);
  return (
    <div className="sc-sensor-debug">
      <span>Session {state.sessionId || '-'}</span>
      <span>States {state.baselineStateCount ?? '-'} / {state.currentStateCount ?? '-'}</span>
      <span>Geaendert {state.changedCount ?? '-'}</span>
      <span>Rest {Math.ceil(state.remainingSeconds ?? 0)}s</span>
      {candidates.slice(0, 3).map((candidate) => (
        <code key={candidate.entity_id}>{candidate.entity_id} · Score {candidate.score ?? candidate.confidence}</code>
      ))}
    </div>
  );
}

export function SetupStepHeader({ current, total, progress, onBack }: { current: number; total: number; progress: number; onBack?: () => void }) {
  return (
    <header className="sc-setup-header">
      <div className="sc-progress"><span style={{ width: `${progress}%` }} /></div>
      <div>
        <button type="button" onClick={onBack} disabled={!onBack}>Zurueck</button>
        <span>Schritt {current} / {total}</span>
      </div>
    </header>
  );
}

function buildSensorTasks(rooms: string[]): SensorTask[] {
  const tasks: SensorTask[] = [{ role: 'main_door', room: 'entrance', title: 'Wohnungstuer einrichten', instruction: 'Oeffnen und schliessen Sie bitte einmal die Wohnungstuer.' }];
  for (const room of rooms.filter((item) => item !== 'entrance')) {
    tasks.push({ role: `${room}_presence`, room, title: `${ROOM_LABELS[room] || room} einrichten`, instruction: `Gehen Sie bitte in den Bereich ${ROOM_LABELS[room] || room} und loesen Sie den Sensor aus.` });
  }
  return tasks;
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}
