import { useEffect, useState, type FormEvent } from 'react';
import { ScanFace, Trash2 } from 'lucide-react';
import { listPasskeys, passkeyError, passkeySupportMessage, registerPasskey, removePasskey, type Passkey } from '@shared/auth/passkeys';

export function PasskeySettings() {
  const [passkeys, setPasskeys] = useState<Passkey[]>([]);
  const [name, setName] = useState('Mein iPad');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const supportMessage = passkeySupportMessage();

  const reload = async () => setPasskeys((await listPasskeys()).passkeys);
  useEffect(() => {
    reload().catch(err => setError(passkeyError(err))).finally(() => setLoading(false));
  }, []);

  const register = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await registerPasskey(password, name);
      setMessage('Passkey eingerichtet. Bei der nächsten Anmeldung kannst du Face ID / Passkey auswählen.');
      await reload();
    } catch (err) {
      setError(passkeyError(err));
    } finally {
      setPassword('');
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await removePasskey(id);
      setDeleteId(null);
      setMessage('Passkey entfernt. Dieser Passkey kann sich nicht mehr bei RoboterSteve anmelden.');
      await reload();
    } catch (err) {
      setError(passkeyError(err));
    } finally {
      setBusy(false);
    }
  };

  return <section className="panel settings-card passkey-settings" aria-labelledby="passkey-title">
    <div className="settings-card-head">
      <div><span className="eyebrow">Anmeldung</span><h2 id="passkey-title">Face ID & Passkeys</h2></div>
      <ScanFace size={26} aria-hidden />
    </div>
    <p>Richte einen Passkey ein, um dich auf deinem iPad mit Face ID anzumelden. Je nach Gerät bestätigt Touch ID oder der Gerätecode die Anmeldung. Dein Passwort funktioniert weiterhin.</p>
    {supportMessage && <p role="status">{supportMessage}</p>}
    <form className="passkey-form" onSubmit={register}>
      <label>Bezeichnung<input value={name} onChange={event => setName(event.target.value)} maxLength={80} required disabled={busy} autoComplete="off" /></label>
      <label>Aktuelles Passwort<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required disabled={busy || Boolean(supportMessage)} /></label>
      <button className="button secondary" type="submit" disabled={busy || loading || Boolean(supportMessage)}><ScanFace size={18} />{busy ? 'Bitte warten…' : 'Face ID / Passkey einrichten'}</button>
    </form>
    {error && <p className="login-error" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    <h3>Eingerichtete Passkeys</h3>
    {loading ? <p>Passkeys werden geladen…</p> : !passkeys.length && <p>Noch kein Passkey eingerichtet.</p>}
    <ul className="passkey-list">
      {passkeys.map(key => <li key={key.id}>
        <div><strong>{key.name}</strong><p>{key.rp_id} · Erstellt am {new Date(key.created_at * 1000).toLocaleDateString('de-DE')}{key.last_used_at ? ` · Zuletzt verwendet am ${new Date(key.last_used_at * 1000).toLocaleDateString('de-DE')}` : ''}</p></div>
        {deleteId === key.id ? <div className="passkey-actions">
          <span>Diesen Passkey entfernen?</span>
          <button className="button secondary" type="button" disabled={busy} onClick={() => remove(key.id)}>Entfernen</button>
          <button className="button secondary" type="button" disabled={busy} onClick={() => setDeleteId(null)}>Abbrechen</button>
        </div> : <button className="button secondary" type="button" disabled={busy} onClick={() => setDeleteId(key.id)} aria-label={`${key.name} entfernen`}><Trash2 size={18} />Entfernen</button>}
      </li>)}
    </ul>
  </section>;
}
