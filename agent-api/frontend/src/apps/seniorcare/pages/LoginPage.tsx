import { FormEvent, useState } from 'react';
import { LockKeyhole } from 'lucide-react';
import { useAuth } from '@shared/auth/AuthContext';
import '../styles/seniorcare.css';

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
    } catch {
      setError('Anmeldung nicht moeglich. Bitte versuchen Sie es erneut.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="sc-login-page">
      <section className="sc-login-card">
        <div className="sc-hero-copy">
          <p className="sc-kicker">Sentero</p>
          <h1>Willkommen zurueck.</h1>
          <p>Ein geschuetzter Blick auf den Alltag eines Menschen, der Ihnen wichtig ist.</p>
        </div>
        <form className="sc-login-form" onSubmit={submit}>
          <label>
            <span>Benutzername</span>
            <input autoFocus value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            <span>Passwort</span>
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </label>
          <label className="sc-check-row">
            <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
            Auf diesem Geraet angemeldet bleiben
          </label>
          {error && <div className="sc-form-note" role="alert">{error}</div>}
          <button className="sc-primary-action" type="submit" disabled={busy}>
            <LockKeyhole size={18} />
            {busy ? 'Wir pruefen den Zugang...' : 'Anmelden'}
          </button>
        </form>
      </section>
    </main>
  );
}
