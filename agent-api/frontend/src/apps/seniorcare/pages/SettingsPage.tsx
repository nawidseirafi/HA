import { useEffect, useMemo, useState } from 'react';
import { Battery, CheckCircle2, Mail, Pencil, Plus, Save, Send, ShieldAlert, Trash2, Wifi, WifiOff } from 'lucide-react';
import { api, type SeniorSensorRole, type SeniorSetupStatus } from '@shared/api/client';
import { UpdatePanel } from '@shared/components/system/UpdatePanel';
import type { SeniorCareSettingsTab } from '../routes/routes';

const roomLabels: Record<string, string> = {
  living_room: 'Wohnzimmer',
  kitchen: 'Küche',
  bathroom: 'Bad',
  bedroom: 'Schlafzimmer',
  hallway: 'Flur',
  entrance: 'Eingang',
};

export function SettingsPage({ activeTab }: { activeTab: SeniorCareSettingsTab }) {
  const [status, setStatus] = useState<SeniorSetupStatus | null>(null);
  const [sensors, setSensors] = useState<SeniorSensorRole[]>([]);
  const [saved, setSaved] = useState('');
  const [error, setError] = useState('');
  const [resetText, setResetText] = useState('');
  const [profile, setProfile] = useState({ name: '', age: '', notes: '' });
  const [contactForm, setContactForm] = useState({ name: '', relationship: '', email: '' });
  const [roomDraft, setRoomDraft] = useState('');
  const [notifications, setNotifications] = useState({ anomalies: true, critical: true, daily_summary: false });
  const [template, setTemplate] = useState('Hallo, bei {name} wurde um {uhrzeit} im Bereich {raum} seit {dauer} keine gewohnte Aktivität erkannt.');

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      const [nextStatus, nextSensors] = await Promise.all([
        api.seniorSetupStatus(),
        api.seniorSensorRoles(true),
      ]);
      setStatus(nextStatus);
      setSensors(nextSensors.sensor_roles);
      setProfile({
        name: nextStatus.profile?.name || '',
        age: nextStatus.profile?.age ? String(nextStatus.profile.age) : '',
        notes: nextStatus.profile?.notes || '',
      });
      setNotifications({
        anomalies: Boolean(nextStatus.notifications?.anomalies ?? true),
        critical: Boolean(nextStatus.notifications?.critical ?? true),
        daily_summary: Boolean(nextStatus.notifications?.daily_summary ?? false),
      });
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Einstellungen konnten nicht geladen werden.');
    }
  }

  const rooms = useMemo(() => {
    const selected = status?.selected_rooms || [];
    const fromSensors = sensors.map((sensor) => sensor.room).filter(Boolean) as string[];
    return Array.from(new Set([...selected, ...fromSensors]));
  }, [status?.selected_rooms, sensors]);

  const preview = template
    .replace('{name}', profile.name || 'Name')
    .replace('{raum}', roomLabels[sensors[0]?.room || ''] || 'Raum')
    .replace('{uhrzeit}', '13:08')
    .replace('{dauer}', '2 Stunden');

  function toast(message = 'Gespeichert') {
    setSaved(`✓ ${message}`);
    window.setTimeout(() => setSaved(''), 2200);
  }

  async function saveProfile() {
    try {
      await api.saveSeniorProfile({ name: profile.name, age: profile.age ? Number(profile.age) : null, notes: profile.notes });
      toast();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Profil konnte nicht gespeichert werden.');
    }
  }

  async function addContact() {
    if (!contactForm.name.trim()) {
      setError('Bitte geben Sie einen Namen ein.');
      return;
    }
    try {
      await api.saveSeniorContact(contactForm);
      setContactForm({ name: '', relationship: '', email: '' });
      toast('Person hinzugefügt');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Kontakt konnte nicht gespeichert werden.');
    }
  }

  async function deleteContact(contactId: number) {
    if (!window.confirm('Vertraute Person wirklich löschen?')) return;
    try {
      await api.deleteSeniorContact(contactId);
      toast('Person gelöscht');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Kontakt konnte nicht gelöscht werden.');
    }
  }

  async function saveRooms(nextRooms: string[]) {
    try {
      await api.saveSeniorSetupRooms(nextRooms);
      toast('Räume gespeichert');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Räume konnten nicht gespeichert werden.');
    }
  }

  async function addRoom() {
    const label = roomDraft.trim();
    if (!label) {
      setError('Bitte geben Sie einen Raumnamen ein.');
      return;
    }
    if (rooms.includes(label)) {
      setError('Dieser Raum existiert bereits.');
      return;
    }
    setRoomDraft('');
    await saveRooms([...rooms, label]);
  }

  async function deleteRoom(room: string) {
    const roomSensors = sensors.filter((sensor) => sensor.room === room);
    const message = roomSensors.length
      ? 'Raum wirklich löschen? Zugeordnete Sensoren werden ebenfalls entfernt.'
      : 'Raum wirklich löschen?';
    if (!window.confirm(message)) return;
    try {
      for (const sensor of roomSensors) {
        await api.deleteSeniorSensorRole(sensor.role);
      }
      await api.saveSeniorSetupRooms(rooms.filter((item) => item !== room));
      toast('Raum gelöscht');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Raum konnte nicht gelöscht werden.');
    }
  }

  async function saveNotifications() {
    try {
      await api.saveSeniorNotifications(notifications);
      toast();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Benachrichtigungen konnten nicht gespeichert werden.');
    }
  }

  async function deleteSensor(role: string) {
    if (!window.confirm('Sensor wirklich entfernen?')) return;
    try {
      await api.deleteSeniorSensorRole(role);
      toast('Sensor entfernt');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sensor konnte nicht entfernt werden.');
    }
  }

  return (
    <section className="sc-page sc-settings">
      {saved && <div className="sc-toast" role="status">{saved}</div>}
      {error && <div className="sc-form-errors" role="alert"><p>{error}</p></div>}

      {activeTab === 'profile' && (
        <section className="sc-panel sc-settings-panel">
          <h2>Senior-Profil</h2>
          <div className="sc-form-grid">
            <label>Name<input value={profile.name} onChange={(event) => setProfile((value) => ({ ...value, name: event.target.value }))} /></label>
            <label>Alter<input inputMode="numeric" value={profile.age} onChange={(event) => setProfile((value) => ({ ...value, age: event.target.value }))} /></label>
            <label className="sc-form-wide">Hinweise<textarea value={profile.notes} onChange={(event) => setProfile((value) => ({ ...value, notes: event.target.value }))} /></label>
          </div>
          <button className="sc-primary-button" type="button" onClick={() => void saveProfile()}><Save size={20} /> Speichern</button>
        </section>
      )}

      {activeTab === 'sensors' && (
        <section className="sc-panel sc-settings-panel">
          <div className="sc-section-title"><h2>Räume & Sensoren</h2><button type="button" onClick={() => window.location.assign('/seniorcare/setup')}><Plus size={20} /> Sensor hinzufügen</button></div>
          <div className="sc-inline-add">
            <input value={roomDraft} onChange={(event) => setRoomDraft(event.target.value)} placeholder="Raum hinzufügen" />
            <button type="button" onClick={() => void addRoom()}><Plus size={20} /> Raum hinzufügen</button>
          </div>
          {rooms.length === 0 && <EmptyState text="Noch keine Räume oder Sensoren eingerichtet." action="Einrichtungsassistent starten" />}
          <div className="sc-room-settings-list">
            {rooms.map((room) => {
              const roomSensors = sensors.filter((sensor) => sensor.room === room);
              return (
                <details key={room} open>
                  <summary>
                    <div>
                      <strong>{roomLabels[room] || room}</strong>
                      <small>{roomSensors.length} Sensoren verbunden</small>
                    </div>
                    <button className="sc-room-delete" type="button" onClick={(event) => { event.preventDefault(); void deleteRoom(room); }}><Trash2 size={18} /> Löschen</button>
                  </summary>
                  <div className="sc-sensor-settings-list">
                    {roomSensors.length === 0 && <p className="sc-muted-note">Für diesen Raum ist noch kein Sensor verbunden.</p>}
                    {roomSensors.map((sensor) => (
                      <div key={sensor.role}>
                        <div className="sc-sensor-settings-main">
                          <strong>{sensor.label || sensor.role}</strong>
                          <small>{sensorType(sensor)} · zuletzt {formatDateTime(sensor.last_changed || sensor.last_updated || sensor.updated_at)}</small>
                          <div className="sc-sensor-health">
                            <span className={sensor.reachable === false ? 'offline' : 'online'}>
                              {sensor.reachable === false ? <WifiOff size={17} /> : <CheckCircle2 size={17} />}
                              {sensor.reachable === false ? 'Nicht erreichbar' : 'Erreichbar'}
                            </span>
                            <span className={batteryClass(sensor.battery_level)}>
                              <Battery size={17} />
                              Akku {sensor.battery_level ?? 'unbekannt'}{sensor.battery_level == null ? '' : '%'}
                            </span>
                            <i aria-hidden="true"><b style={{ width: `${sensor.battery_level ?? 0}%` }} /></i>
                          </div>
                        </div>
                        <div className="sc-sensor-settings-actions">
                          <button type="button"><Pencil size={18} /> Name</button>
                          <button type="button" onClick={() => toast('Sensor geprüft')}><Wifi size={18} /> Test</button>
                          <button type="button" onClick={() => void deleteSensor(sensor.role)}><Trash2 size={18} /> Löschen</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              );
            })}
          </div>
        </section>
      )}

      {activeTab === 'contacts' && (
        <section className="sc-panel sc-settings-panel">
          <div className="sc-section-title"><h2>Vertraute Personen</h2><button type="button" onClick={() => void addContact()}><Plus size={20} /> Person hinzufügen</button></div>
          <div className="sc-form-grid">
            <label>Name<input value={contactForm.name} onChange={(event) => setContactForm((value) => ({ ...value, name: event.target.value }))} /></label>
            <label>Beziehung<input value={contactForm.relationship} onChange={(event) => setContactForm((value) => ({ ...value, relationship: event.target.value }))} /></label>
            <label>E-Mail<input type="email" value={contactForm.email} onChange={(event) => setContactForm((value) => ({ ...value, email: event.target.value }))} /></label>
          </div>
          <div className="sc-settings-contact-grid">
            {(status?.trusted_contacts || []).map((contact) => (
              <article key={contact.id}>
                <span className="sc-avatar">{contact.name[0]}</span>
                <h3>{contact.name}</h3>
                <p>{contact.relationship || 'Kontakt'}</p>
                <small>{contact.email || 'Keine E-Mail hinterlegt'}</small>
                <footer>
                  <button type="button" onClick={() => void deleteContact(contact.id)}><Trash2 size={18} /> Löschen</button>
                </footer>
              </article>
            ))}
          </div>
        </section>
      )}

      {activeTab === 'notifications' && (
        <section className="sc-panel sc-settings-panel">
          <h2>Benachrichtigungen</h2>
          <label className="sc-large-check"><input type="checkbox" checked={notifications.anomalies} onChange={(event) => setNotifications((value) => ({ ...value, anomalies: event.target.checked }))} /> Hinweise bei Auffälligkeiten</label>
          <label className="sc-large-check"><input type="checkbox" checked={notifications.critical} onChange={(event) => setNotifications((value) => ({ ...value, critical: event.target.checked }))} /> Dringende Alarme senden</label>
          <label className="sc-large-check"><input type="checkbox" checked={notifications.daily_summary} onChange={(event) => setNotifications((value) => ({ ...value, daily_summary: event.target.checked }))} /> Tägliche Zusammenfassung</label>
          <button className="sc-soft-button" type="button" onClick={() => toast('Testnachricht gesendet')}><Send size={20} /> Testnachricht senden</button>
          <label className="sc-template-editor">Vorlage für Benachrichtigungen<textarea value={template} onChange={(event) => setTemplate(event.target.value)} /></label>
          <div className="sc-message-preview"><Mail size={20} /> {preview}</div>
          <button className="sc-primary-button" type="button" onClick={() => void saveNotifications()}><Save size={20} /> Speichern</button>
        </section>
      )}

      {activeTab === 'system' && (
        <section className="sc-panel sc-settings-panel">
          <h2>System</h2>
          <div className="sc-system-grid">
            <p><strong>Home verbunden</strong><span>{status?.home.connected ? 'Ja' : 'Nein'}</span></p>
            <p><strong>Sensoren verbunden</strong><span>{sensors.filter((sensor) => sensor.configured).length}</span></p>
            <p><strong>Sensoren offline</strong><span>{sensors.filter((sensor) => sensor.reachable === false).length}</span></p>
            <p><strong>Letzte Aktualisierung</strong><span>{formatDateTime(status?.updated_at)}</span></p>
          </div>
          <UpdatePanel variant="seniorcare" />
          <div className="sc-danger-zone">
            <h3><ShieldAlert size={22} /> Werkseinstellungen</h3>
            <p>Zum Zurücksetzen bitte ZURÜCKSETZEN eingeben.</p>
            <input value={resetText} onChange={(event) => setResetText(event.target.value)} placeholder="ZURÜCKSETZEN" />
            <button type="button" disabled={resetText !== 'ZURÜCKSETZEN'} onClick={() => window.confirm('Alle Sentero-Daten löschen?')}>Factory Reset</button>
          </div>
        </section>
      )}
    </section>
  );
}

function EmptyState({ text, action }: { text: string; action: string }) {
  return (
    <div className="sc-empty-state">
      <p>{text}</p>
      <button type="button" onClick={() => window.location.assign('/seniorcare/setup')}>{action}</button>
    </div>
  );
}

function sensorType(sensor: SeniorSensorRole) {
  if (sensor.role === 'main_door' || ['door', 'window', 'opening', 'contact'].includes(String(sensor.device_class || ''))) return 'Türkontakt';
  return 'Bewegung';
}

function batteryClass(value?: number | null) {
  if (value == null) return 'battery unknown';
  if (value < 30) return 'battery low';
  if (value < 50) return 'battery medium';
  return 'battery';
}

function formatDateTime(value?: string | null) {
  if (!value) return 'noch keine Daten';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return 'noch keine Daten';
  return new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date);
}
