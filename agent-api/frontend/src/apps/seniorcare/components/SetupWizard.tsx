import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, HeartHandshake, Plus, ShieldCheck, Trash2, UserRound } from 'lucide-react';
import { api, type SeniorCandidates } from '@shared/api/client';
import { SensorWizard, type SensorBinding, type SensorDiscoveryState } from './SensorWizard';

type Profile = {
  name: string;
  birthDate: string;
  age: string;
  notes: string;
};

type Contact = {
  id: string;
  name: string;
  relation: string;
  phone: string;
  email: string;
  channels: string[];
};

const steps = ['Willkommen', 'Profil', 'Räume', 'Sensoren', 'Vertraute Personen', 'Benachrichtigungen', 'Abschluss'];
const ZIGBEE_DISCOVERY_SECONDS = 180;

const roomOptions = [
  { id: 'living_room', label: 'Wohnzimmer', door: true },
  { id: 'kitchen', label: 'Küche', door: true },
  { id: 'bathroom', label: 'Bad', door: true },
  { id: 'toilet', label: 'Toilette', door: true },
  { id: 'bedroom', label: 'Schlafzimmer', door: true },
  { id: 'hallway', label: 'Flur/Eingang', door: true },
  { id: 'office', label: 'Arbeitszimmer', door: true },
  { id: 'garden', label: 'Balkon/Garten', door: false },
];

const baseRoomLabel = Object.fromEntries(roomOptions.map((room) => [room.id, room.label]));

export function SetupWizard({ onFinish }: { onFinish: () => void }) {
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState<Profile>({ name: '', birthDate: '', age: '', notes: '' });
  const [selectedRooms, setSelectedRooms] = useState<string[]>([]);
  const [customRooms, setCustomRooms] = useState<Record<string, string>>({});
  const [sensorPlan, setSensorPlan] = useState<Record<string, { motion: boolean; door: boolean }>>({});
  const [customRoom, setCustomRoom] = useState('');
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [contactForm, setContactForm] = useState<Contact>({ id: '', name: '', relation: 'Tochter', phone: '', email: '', channels: ['WhatsApp'] });
  const [notification, setNotification] = useState({ from: '07:00', to: '22:00', nightCriticalOnly: true, sensitivity: 2 });
  const [confirmed, setConfirmed] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [sensorBindings, setSensorBindings] = useState<SensorBinding[]>([]);
  const [discovery, setDiscovery] = useState<Record<string, SensorDiscoveryState>>({});
  const timers = useRef<Record<string, number>>({});
  const devMode = new URLSearchParams(window.location.search).get('dev') === '1';

  useEffect(() => {
    setSensorBindings((current) => buildBindings(selectedRooms, sensorPlan, customRooms, current));
  }, [selectedRooms, sensorPlan, customRooms]);

  useEffect(() => {
    void api.seniorSetupStatus().then((status) => {
      if (status.selected_rooms.length) setSelectedRooms(status.selected_rooms);
      const unknownRooms = Object.fromEntries(
        status.selected_rooms
          .filter((room) => !baseRoomLabel[room])
          .map((room) => [room, room]),
      );
      if (Object.keys(unknownRooms).length) setCustomRooms((current) => ({ ...unknownRooms, ...current }));
      if (status.profile?.name) {
        setProfile((value) => ({
          ...value,
          name: status.profile?.name || '',
          age: status.profile?.age ? String(status.profile.age) : '',
          notes: status.profile?.notes || '',
        }));
      }
      if (status.trusted_contacts?.length) {
        setContacts(status.trusted_contacts.map((contact) => ({
          id: String(contact.id),
          name: contact.name,
          relation: contact.relationship || '',
          phone: '',
          email: contact.email || '',
          channels: ['E-Mail'],
        })));
      }
    }).catch(() => undefined);
    return () => Object.values(timers.current).forEach((timer) => window.clearTimeout(timer));
  }, []);

  const calculatedAge = useMemo(() => {
    if (!profile.birthDate) return '';
    const birth = new Date(profile.birthDate);
    const today = new Date();
    let years = today.getFullYear() - birth.getFullYear();
    const beforeBirthday = today.getMonth() < birth.getMonth() || (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate());
    if (beforeBirthday) years -= 1;
    return `${years} Jahre`;
  }, [profile.birthDate]);

  const displayAge = profile.age || (calculatedAge ? calculatedAge.replace(/\D+/g, '') : '');

  const connectedSensors = sensorBindings.filter((sensor) => sensor.status === 'connected').length;

  async function next() {
    const validation = validateStep();
    setErrors(validation);
    if (validation.length) return;

    if (step === 0) {
      await safeBackend(() => api.startSeniorSetup());
    }
    if (step === 1) {
      await safeBackend(() => api.saveSeniorProfile({ name: profile.name.trim(), age: displayAge ? Number.parseInt(displayAge, 10) : null, notes: profile.notes }));
    }
    if (step === 2) {
      await safeBackend(() => api.saveSeniorSetupRooms(selectedRooms));
    }
    if (step === 4 && contacts[0]) {
      await safeBackend(() => api.saveSeniorContact({ name: contacts[0].name, relationship: contacts[0].relation, email: contacts[0].email }));
    }
    if (step === 5) {
      await safeBackend(() => api.saveSeniorNotifications({ anomalies: true, critical: true, daily_summary: false }));
    }
    if (step === steps.length - 1) {
      await safeBackend(() => api.completeSeniorSetup());
      onFinish();
      return;
    }
    setStep((value) => Math.min(value + 1, steps.length - 1));
  }

  function back() {
    setErrors([]);
    setStep((value) => Math.max(value - 1, 0));
  }

  function validateStep() {
    if (step === 1 && !profile.name.trim()) return ['Bitte geben Sie den Namen ein.'];
    if (step === 2 && selectedRooms.length === 0) return ['Bitte wählen Sie mindestens einen Raum aus.'];
    if (step === 4 && contacts.length === 0) return ['Bitte fügen Sie mindestens eine vertraute Person hinzu.'];
    if (step === 6 && !confirmed) return ['Bitte bestätigen Sie die Zusammenfassung.'];
    return [];
  }

  async function safeBackend(action: () => Promise<unknown>) {
    try {
      await action();
    } catch {
      // The wizard remains usable with mock data when the local backend is not reachable.
    }
  }

  function toggleRoom(roomId: string) {
    setSelectedRooms((current) => {
      if (current.includes(roomId)) return current.filter((id) => id !== roomId);
      setSensorPlan((plans) => ({ ...plans, [roomId]: plans[roomId] || defaultSensorPlan(roomId) }));
      return [...current, roomId];
    });
  }

  function addCustomRoom() {
    const label = customRoom.trim();
    if (!label) return;
    const id = label;
    setCustomRooms((current) => ({ ...current, [id]: label }));
    setSelectedRooms((current) => current.includes(id) ? current : [...current, id]);
    setSensorPlan((current) => ({ ...current, [id]: current[id] || { motion: true, door: false } }));
    setCustomRoom('');
  }

  function roomLabel(roomId: string) {
    return customRooms[roomId] || baseRoomLabel[roomId] || roomId;
  }

  function toggleSensorType(roomId: string, type: 'motion' | 'door') {
    setSensorPlan((current) => {
      const fallback = defaultSensorPlan(roomId);
      const next = { ...(current[roomId] || fallback), [type]: !(current[roomId] || fallback)[type] };
      if (!next.motion && !next.door) next[type] = true;
      return { ...current, [roomId]: next };
    });
  }

  function updateSensor(id: string, patch: Partial<SensorBinding>) {
    setSensorBindings((current) => current.map((sensor) => sensor.id === id ? { ...sensor, ...patch } : sensor));
  }

  async function searchSensor(sensor: SensorBinding) {
    updateSensor(sensor.id, { status: 'searching' });
    setDiscovery((current) => ({ ...current, [sensor.id]: { remainingSeconds: ZIGBEE_DISCOVERY_SECONDS } }));
    try {
      const result = await api.startSeniorZigbeePairing({ role: sensor.id, room: sensor.roomId, duration: ZIGBEE_DISCOVERY_SECONDS });
      if (result.status === 'pairing_needs_manual_action') {
        throw new Error(result.message || 'Die Sensor-Einrichtung ist noch nicht bereit.');
      }
      updateSensor(sensor.id, { sessionId: result.session_id });
      setDiscovery((current) => ({ ...current, [sensor.id]: { ...(current[sensor.id] || {}), provider: result.detail?.provider, remainingSeconds: ZIGBEE_DISCOVERY_SECONDS } }));
      pollSensor(sensor.id, result.session_id, Date.now(), sensor.name, sensor.roomId);
    } catch (err) {
      updateSensor(sensor.id, { status: 'missing' });
      setDiscovery((current) => ({ ...current, [sensor.id]: { error: err instanceof Error ? err.message : 'Sensor nicht gefunden.' } }));
    }
  }

  function pollSensor(sensorId: string, sessionId: number, startedAt: number, sensorName: string, roomId: string) {
    window.clearTimeout(timers.current[sensorId]);
    timers.current[sensorId] = window.setTimeout(async () => {
      try {
        const result = await api.seniorDiscoveryCandidates(sessionId, devMode);
        const done = await applyCandidate(sensorId, sessionId, result, sensorName, roomId);
        if (!done && Date.now() - startedAt < ZIGBEE_DISCOVERY_SECONDS * 1000) {
          pollSensor(sensorId, sessionId, startedAt, sensorName, roomId);
        }
      } catch (err) {
        updateSensor(sensorId, { status: 'missing' });
        setDiscovery((current) => ({ ...current, [sensorId]: { error: err instanceof Error ? err.message : 'Sensor nicht gefunden.' } }));
      }
    }, 2000);
  }

  async function applyCandidate(sensorId: string, sessionId: number, result: SeniorCandidates, sensorName: string, roomId: string) {
    const score = result.candidate ? (result.candidate.score ?? result.candidate.confidence) : 0;
    const found = Boolean(result.candidate && score >= 50);
    const timedOut = result.status === 'no_signal_detected' || result.remaining_seconds === 0;
    setDiscovery((current) => ({ ...current, [sensorId]: { candidate: result.candidate, candidates: result.candidates, remainingSeconds: result.remaining_seconds } }));
    if (found && result.candidate) {
      const name = sensorName || result.candidate.label || 'Sensor';
      try {
        await api.confirmSeniorDiscovery(sessionId, result.candidate.entity_id, { name, room: roomId });
        updateSensor(sensorId, { status: 'connected', sessionId, score, entityId: result.candidate.entity_id, name });
      } catch (err) {
        updateSensor(sensorId, { status: 'missing' });
        setDiscovery((current) => ({ ...current, [sensorId]: { ...(current[sensorId] || {}), error: err instanceof Error ? err.message : 'Sensor konnte nicht gespeichert werden.' } }));
      }
      return true;
    }
    if (timedOut) {
      updateSensor(sensorId, { status: 'missing' });
      return true;
    }
    return false;
  }

  function addContact() {
    const nextErrors = [];
    if (!contactForm.name.trim()) nextErrors.push('Bitte geben Sie einen Namen ein.');
    if (!contactForm.phone.trim()) nextErrors.push('Bitte geben Sie eine Telefonnummer ein.');
    if (!contactForm.channels.length) nextErrors.push('Bitte wählen Sie mindestens einen Kanal.');
    if (nextErrors.length) {
      setErrors(nextErrors);
      return;
    }
    setContacts((current) => [...current, { ...contactForm, id: crypto.randomUUID() }]);
    setContactForm({ id: '', name: '', relation: 'Tochter', phone: '', email: '', channels: ['WhatsApp'] });
    setErrors([]);
  }

  return (
    <section className="sc-wizard">
      <WizardProgress step={step} />
      {errors.length > 0 && <div className="sc-form-errors" role="alert">{errors.map((error) => <p key={error}>{error}</p>)}</div>}
      <div className="sc-wizard-card">
        {step === 0 && <WelcomeStep />}
        {step === 1 && <ProfileStep profile={profile} calculatedAge={calculatedAge} onChange={setProfile} />}
        {step === 2 && <RoomsStep selected={selectedRooms} customRooms={customRooms} sensorPlan={sensorPlan} customRoom={customRoom} onToggle={toggleRoom} onCustomChange={setCustomRoom} onCustomAdd={addCustomRoom} onToggleSensorType={toggleSensorType} />}
        {step === 3 && <SensorWizard sensors={sensorBindings} discovery={discovery} roomLabel={roomLabel} devMode={devMode} connected={connectedSensors} total={sensorBindings.length} onChange={updateSensor} onSearch={searchSensor} />}
        {step === 4 && <ContactsStep contacts={contacts} form={contactForm} onFormChange={setContactForm} onAdd={addContact} onDelete={(id) => setContacts((current) => current.filter((contact) => contact.id !== id))} />}
        {step === 5 && <NotificationStep value={notification} onChange={setNotification} />}
        {step === 6 && <SummaryStep profile={profile} age={displayAge} rooms={selectedRooms} roomLabel={roomLabel} contacts={contacts} sensors={connectedSensors} totalSensors={sensorBindings.length} notification={notification} confirmed={confirmed} onConfirm={setConfirmed} />}
      </div>
      <footer className="sc-wizard-actions">
        <button type="button" onClick={back} disabled={step === 0}><ArrowLeft size={20} /> Zurück</button>
        <button className="primary" type="button" onClick={() => void next()}>
          {step === 0 ? 'Einrichtung starten' : step === steps.length - 1 ? 'Einrichtung abschließen' : 'Weiter'}
          <ArrowRight size={20} />
        </button>
      </footer>
    </section>
  );
}

function WizardProgress({ step }: { step: number }) {
  return (
    <header className="sc-wizard-progress">
      <div className="sc-stepper-scroll" aria-label={`Schritt ${step + 1} von ${steps.length}`}>
        <ol className="sc-stepper">
          {steps.map((label, index) => {
            const state = index < step ? 'completed' : index === step ? 'current' : 'future';
            return (
              <li key={label} className={state}>
                <span aria-current={index === step ? 'step' : undefined}>{index + 1}</span>
              </li>
            );
          })}
        </ol>
      </div>
      <div className="sc-wizard-step-title">
        <p>Schritt {step + 1} von {steps.length}</p>
        <h2>{steps[step]}</h2>
      </div>
    </header>
  );
}

function WelcomeStep() {
  return (
    <section className="sc-wizard-welcome">
      <span className="sc-hero-illustration"><HeartHandshake size={58} /><ShieldCheck size={66} /></span>
      <h1>Willkommen bei Sentero</h1>
      <p>Sentero achtet leise im Hintergrund auf vertraute Tagesabläufe. Wenn etwas ungewöhnlich wirkt, werden vertraute Personen behutsam informiert.</p>
      <p>Die Einrichtung dauert nur wenige Minuten und kann später jederzeit angepasst werden.</p>
    </section>
  );
}

function ProfileStep({ profile, calculatedAge, onChange }: { profile: Profile; calculatedAge: string; onChange: (profile: Profile) => void }) {
  return (
    <section className="sc-form-grid">
      <label>Name<input required value={profile.name} onChange={(event) => onChange({ ...profile, name: event.target.value })} /></label>
      <label>Geburtsdatum<input type="date" value={profile.birthDate} onChange={(event) => onChange({ ...profile, birthDate: event.target.value })} /></label>
      <label>Alter<input inputMode="numeric" value={profile.age || calculatedAge.replace(/\D+/g, '')} onChange={(event) => onChange({ ...profile, age: event.target.value })} aria-label="Alter" /></label>
      <label className="sc-form-wide">Hinweise<textarea value={profile.notes} onChange={(event) => onChange({ ...profile, notes: event.target.value })} placeholder="z.B. steht normalerweise früh auf, eingeschränkte Mobilität, wichtige Gewohnheiten" /></label>
    </section>
  );
}

function RoomsStep({ selected, customRooms, sensorPlan, customRoom, onToggle, onCustomChange, onCustomAdd, onToggleSensorType }: {
  selected: string[];
  customRooms: Record<string, string>;
  sensorPlan: Record<string, { motion: boolean; door: boolean }>;
  customRoom: string;
  onToggle: (id: string) => void;
  onCustomChange: (value: string) => void;
  onCustomAdd: () => void;
  onToggleSensorType: (roomId: string, type: 'motion' | 'door') => void;
}) {
  const visibleRooms = [...roomOptions, ...Object.entries(customRooms).map(([id, label]) => ({ id, label, door: false }))];
  return (
    <section className="sc-room-select">
      <p>Wählen Sie die Räume in der Wohnung.</p>
      <div className="sc-room-choice-grid">
        {visibleRooms.map((room) => {
          const active = selected.includes(room.id);
          const plan = sensorPlan[room.id] || defaultSensorPlan(room.id);
          return (
            <div key={room.id} className={`sc-room-choice-card ${active ? 'active' : ''}`}>
              <button type="button" onClick={() => onToggle(room.id)}>
                <strong>{room.label}</strong>
              </button>
              {active && (
                <div className="sc-room-sensor-toggles">
                  <label><input type="checkbox" checked={plan.motion} onChange={() => onToggleSensorType(room.id, 'motion')} /> Präsenzsensor</label>
                  <label><input type="checkbox" checked={plan.door} onChange={() => onToggleSensorType(room.id, 'door')} /> Türsensor</label>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="sc-inline-add">
        <input value={customRoom} onChange={(event) => onCustomChange(event.target.value)} placeholder="Eigenen Raum hinzufügen" />
        <button type="button" onClick={onCustomAdd}><Plus size={20} /> Hinzufügen</button>
      </div>
      <strong>{selected.length} Räume ausgewählt</strong>
    </section>
  );
}

function ContactsStep({ contacts, form, onFormChange, onAdd, onDelete }: { contacts: Contact[]; form: Contact; onFormChange: (contact: Contact) => void; onAdd: () => void; onDelete: (id: string) => void }) {
  return (
    <section className="sc-contacts-step">
      <p>Wen sollen wir bei Auffälligkeiten benachrichtigen?</p>
      <div className="sc-form-grid">
        <label>Name<input value={form.name} onChange={(event) => onFormChange({ ...form, name: event.target.value })} /></label>
        <label>Beziehung<select value={form.relation} onChange={(event) => onFormChange({ ...form, relation: event.target.value })}>{['Tochter', 'Sohn', 'Pflegeperson', 'Nachbar', 'Arzt', 'Sonstige'].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Telefonnummer<input type="tel" value={form.phone} onChange={(event) => onFormChange({ ...form, phone: event.target.value })} placeholder="+49 ..." /></label>
        <label>E-Mail<input type="email" value={form.email} onChange={(event) => onFormChange({ ...form, email: event.target.value })} /></label>
      </div>
      <div className="sc-checkbox-row">{['SMS', 'WhatsApp', 'E-Mail'].map((channel) => <label key={channel}><input type="checkbox" checked={form.channels.includes(channel)} onChange={(event) => onFormChange({ ...form, channels: event.target.checked ? [...form.channels, channel] : form.channels.filter((item) => item !== channel) })} /> {channel}</label>)}</div>
      <button className="sc-soft-button" type="button" onClick={onAdd}><Plus size={20} /> Person hinzufügen</button>
      <div className="sc-contact-list-editor">
        {contacts.map((contact) => <div key={contact.id}><span className="sc-avatar">{contact.name[0]}</span><strong>{contact.name}</strong><small>{contact.relation}</small><button type="button" onClick={() => onDelete(contact.id)}><Trash2 size={18} /></button></div>)}
      </div>
    </section>
  );
}

function NotificationStep({ value, onChange }: { value: { from: string; to: string; nightCriticalOnly: boolean; sensitivity: number }; onChange: (value: { from: string; to: string; nightCriticalOnly: boolean; sensitivity: number }) => void }) {
  const labels = ['Nur bei langen Pausen (>4h)', 'Ungewöhnliche Aktivitätsmuster (>2h)', 'Bei jeder kleinen Auffälligkeit (>1h)'];
  return (
    <section className="sc-notification-step">
      <div className="sc-form-grid two">
        <label>Von<input type="time" value={value.from} onChange={(event) => onChange({ ...value, from: event.target.value })} /></label>
        <label>Bis<input type="time" value={value.to} onChange={(event) => onChange({ ...value, to: event.target.value })} /></label>
      </div>
      <label className="sc-large-check"><input type="checkbox" checked={value.nightCriticalOnly} onChange={(event) => onChange({ ...value, nightCriticalOnly: event.target.checked })} /> Nachts nur bei dringenden Alarmen</label>
      <label className="sc-slider-label">Empfindlichkeit<strong>{labels[value.sensitivity - 1]}</strong><input type="range" min="1" max="3" value={value.sensitivity} onChange={(event) => onChange({ ...value, sensitivity: Number(event.target.value) })} /></label>
    </section>
  );
}

function SummaryStep({ profile, age, rooms, roomLabel, contacts, sensors, totalSensors, notification, confirmed, onConfirm }: { profile: Profile; age: string; rooms: string[]; roomLabel: (room: string) => string; contacts: Contact[]; sensors: number; totalSensors: number; notification: { from: string; to: string; sensitivity: number }; confirmed: boolean; onConfirm: (value: boolean) => void }) {
  return (
    <section className="sc-summary-step">
      <div className="sc-summary-card">
        <UserRound size={28} /><strong>{profile.name}</strong><span>{age ? `${age} Jahre` : 'Alter offen'}</span>
      </div>
      <div className="sc-summary-grid">
        <p><strong>Räume</strong>{rooms.map((room) => roomLabel(room)).join(', ')}</p>
        <p><strong>Sensoren</strong>{sensors} von {totalSensors} verbunden</p>
        <p><strong>Kontakte</strong>{contacts.map((contact) => `${contact.name} (${contact.relation})`).join(', ')}</p>
        <p><strong>Benachrichtigungen</strong>{notification.from} - {notification.to}, Stufe {notification.sensitivity}</p>
      </div>
      <label className="sc-large-check"><input type="checkbox" checked={confirmed} onChange={(event) => onConfirm(event.target.checked)} /> Ich bestätige, dass alle Angaben korrekt sind.</label>
    </section>
  );
}

function buildBindings(roomIds: string[], sensorPlan: Record<string, { motion: boolean; door: boolean }>, customRooms: Record<string, string>, current: SensorBinding[]) {
  const byId = Object.fromEntries(current.map((sensor) => [sensor.id, sensor]));
  return roomIds.flatMap((roomId) => {
    const label = customRooms[roomId] || baseRoomLabel[roomId] || roomId;
    const plan = sensorPlan[roomId] || defaultSensorPlan(roomId);
    const bindings: SensorBinding[] = [];
    if (plan.motion) {
      const motionId = `${roomId}_presence`;
      bindings.push(byId[motionId] || { id: motionId, roomId, type: 'motion', sensorId: '', name: `${label} Präsenz`, status: 'idle' });
    }
    if (plan.door) {
      const doorId = `${roomId}_door`;
      bindings.push(byId[doorId] || { id: doorId, roomId, type: 'door', sensorId: '', name: `${label} Türkontakt`, status: 'idle' });
    }
    return bindings;
  });
}

function defaultSensorPlan(roomId: string) {
  const option = roomOptions.find((room) => room.id === roomId);
  return { motion: true, door: option?.door !== false };
}
