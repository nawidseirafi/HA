import { useMemo, useState } from 'react';
import { Battery, CheckCircle2, Download, Mail, Pencil, Plus, RotateCcw, Save, Send, ShieldAlert, Trash2, Wifi, WifiOff } from 'lucide-react';
import type { SeniorCareSettingsTab } from '../routes/routes';
import { notificationSettings, rooms as mockRooms, seniorProfile, sensors, trustedContacts } from '../data/mockSeniorCareData';

export function SettingsPage({ activeTab }: { activeTab: SeniorCareSettingsTab }) {
  const [saved, setSaved] = useState('');
  const [resetText, setResetText] = useState('');
  const [template, setTemplate] = useState(notificationSettings.template);
  const offlineCount = sensors.filter((sensor) => sensor.status === 'offline').length;
  const preview = useMemo(() => template
    .replace('{name}', seniorProfile.fullName)
    .replace('{raum}', seniorProfile.currentRoom)
    .replace('{uhrzeit}', '13:08')
    .replace('{dauer}', '2 Stunden'), [template]);

  function save(message = 'Gespeichert') {
    setSaved(`✓ ${message}`);
    window.setTimeout(() => setSaved(''), 2200);
  }

  return (
    <section className="sc-page sc-settings">
      {saved && <div className="sc-toast" role="status">{saved}</div>}

      {activeTab === 'profile' && (
        <section className="sc-panel sc-settings-panel">
          <h2>Senior-Profil</h2>
          <div className="sc-form-grid">
            <label>Vorname<input defaultValue={seniorProfile.firstName} /></label>
            <label>Nachname<input defaultValue={seniorProfile.lastName} /></label>
            <label>Geburtsdatum<input type="date" defaultValue={seniorProfile.birthDate} /></label>
          </div>
          <button className="sc-primary-button" type="button" onClick={() => save()}><Save size={20} /> Speichern</button>
        </section>
      )}

      {activeTab === 'sensors' && (
        <section className="sc-panel sc-settings-panel">
          <div className="sc-section-title"><h2>Räume & Sensoren</h2><button type="button"><Plus size={20} /> Raum hinzufügen</button></div>
          <div className="sc-room-settings-list">
            {mockRooms.map((room) => (
              <details key={room.id} open={room.id === 'living_room'}>
                <summary>
                  <div>
                    <strong>{room.name}</strong>
                    <small>{room.sensors} Sensoren verbunden</small>
                  </div>
                </summary>
                <div className="sc-room-edit">
                  <label>Raumname<input defaultValue={room.name} /></label>
                  <button type="button" onClick={() => window.confirm(`${room.name} wirklich löschen?`)}><Trash2 size={18} /> Raum löschen</button>
                </div>
                <div className="sc-sensor-settings-list">
                  {sensors.filter((sensor) => sensor.roomId === room.id).map((sensor) => (
                    <div key={sensor.id}>
                      <div className="sc-sensor-settings-main">
                        <strong>{sensor.name}</strong>
                        <small>{sensor.id} · {sensor.type === 'motion' ? 'Bewegung' : 'Türkontakt'} · zuletzt {sensor.lastSeen}</small>
                        <div className="sc-sensor-health">
                          <span className={sensor.status === 'online' ? 'online' : 'offline'}>
                            {sensor.status === 'online' ? <CheckCircle2 size={17} /> : <WifiOff size={17} />}
                            {sensor.status === 'online' ? 'Erreichbar' : 'Nicht erreichbar'}
                          </span>
                          <span className={sensor.battery < 30 ? 'battery low' : sensor.battery < 50 ? 'battery medium' : 'battery'}>
                            <Battery size={17} />
                            Akku {sensor.battery}%
                          </span>
                          <i aria-hidden="true"><b style={{ width: `${sensor.battery}%` }} /></i>
                        </div>
                      </div>
                      <div className="sc-sensor-settings-actions">
                        <button type="button"><Pencil size={18} /> Name</button>
                        <button type="button" onClick={() => save('Sensor getestet')}><Wifi size={18} /> Test</button>
                        <button type="button" onClick={() => window.confirm(`${sensor.name} entfernen?`)}><Trash2 size={18} /> Löschen</button>
                      </div>
                    </div>
                  ))}
                </div>
                <button className="sc-soft-button" type="button"><Plus size={19} /> Sensor hinzufügen</button>
              </details>
            ))}
          </div>
        </section>
      )}

      {activeTab === 'contacts' && (
        <section className="sc-panel sc-settings-panel">
          <div className="sc-section-title"><h2>Vertraute Personen</h2><button type="button"><Plus size={20} /> Person hinzufügen</button></div>
          <div className="sc-settings-contact-grid">
            {trustedContacts.map((contact) => (
              <article key={contact.id}>
                <span className="sc-avatar">{contact.name[0]}</span>
                <h3>{contact.name}</h3>
                <p>{contact.relation}</p>
                <small>{contact.phone}</small>
                <small>{contact.email}</small>
                <div>{contact.channels.map((channel) => <span className="sc-chip ok" key={channel}>{channel}</span>)}</div>
                <footer>
                  <button type="button"><Pencil size={18} /> Bearbeiten</button>
                  <button type="button" onClick={() => window.confirm(`${contact.name} löschen?`)}><Trash2 size={18} /> Löschen</button>
                </footer>
              </article>
            ))}
          </div>
        </section>
      )}

      {activeTab === 'notifications' && (
        <section className="sc-panel sc-settings-panel">
          <h2>Benachrichtigungen</h2>
          <div className="sc-form-grid two">
            <label>Von<input type="time" defaultValue={notificationSettings.from} /></label>
            <label>Bis<input type="time" defaultValue={notificationSettings.to} /></label>
          </div>
          <label className="sc-large-check"><input type="checkbox" defaultChecked={notificationSettings.nightCriticalOnly} /> Nachts nur bei dringenden Alarmen</label>
          <label className="sc-slider-label">Empfindlichkeit<strong>Ungewöhnliche Aktivitätsmuster (&gt;2h)</strong><input type="range" min="1" max="3" defaultValue="2" /></label>
          <button className="sc-soft-button" type="button" onClick={() => save('Testnachricht gesendet')}><Send size={20} /> Testnachricht senden an alle</button>
          <label className="sc-template-editor">Vorlage für Benachrichtigungen<textarea value={template} onChange={(event) => setTemplate(event.target.value)} /></label>
          <p className="sc-template-vars">Variablen: {'{name}'}, {'{raum}'}, {'{uhrzeit}'}, {'{dauer}'}</p>
          <div className="sc-message-preview"><Mail size={20} /> {preview}</div>
          <button className="sc-primary-button" type="button" onClick={() => save()}><Save size={20} /> Speichern</button>
        </section>
      )}

      {activeTab === 'system' && (
        <section className="sc-panel sc-settings-panel">
          <h2>System</h2>
          <div className="sc-system-grid">
            <p><strong>App-Version</strong><span>1.0.0</span></p>
            <p><strong>Sensoren verbunden</strong><span>{sensors.length - offlineCount}</span></p>
            <p><strong>Sensoren offline</strong><span>{offlineCount}</span></p>
          </div>
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
