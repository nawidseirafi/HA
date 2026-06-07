import { FormEvent, useState } from 'react';
import { HeartHandshake, LockKeyhole } from 'lucide-react';
import { useAuth } from '@shared/auth/AuthContext';

export function LoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      const ok = await login({ username, password, remember });
      if (!ok) {
        setError('Bitte Zugangsdaten eingeben.');
        return;
      }
      onLoggedIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Anmeldung fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="seniorcare-login">
      <section className="seniorcare-login-card">
        <div className="seniorcare-login-intro">
          <span><HeartHandshake size={26} /></span>
          <p className="eyebrow">SeniorCare</p>
          <h1>Sicher anmelden</h1>
          <p>Geschuetzter Zugang fuer Angehoerige und Betreuungspersonen.</p>
        </div>
        <form className="seniorcare-login-form" onSubmit={submit}>
          <label>
            <span>Benutzername</span>
            <input autoFocus value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            <span>Passwort</span>
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </label>
          <label className="seniorcare-remember">
            <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
            Auf diesem Geraet angemeldet bleiben
          </label>
          {error && <div className="seniorcare-login-error" role="alert">{error}</div>}
          <button type="submit" disabled={busy}>
            <LockKeyhole size={18} />
            {busy ? 'Pruefe Zugang...' : 'Anmelden'}
          </button>
        </form>
      </section>
    </main>
  );
}
