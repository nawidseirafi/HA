import { FormEvent, useState } from 'react';
import { LockKeyhole } from 'lucide-react';
import { useAuth } from '@shared/auth/AuthContext';
import senteroLogo from '../assets/logo.png';
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
          <div className="sc-login-brand">
            <img src={senteroLogo} alt="Sentero" />
          </div>
          <p>Melden Sie sich an, um den Alltag Ihrer Angehörigen im Blick zu behalten.</p>
        </div>
        <form className="sc-login-form" onSubmit={submit}>
          <label className="sc-floating-field">
            <input autoFocus value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" placeholder=" " />
            <span>E-Mail-Adresse</span>
          </label>
          <label className="sc-floating-field">
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" placeholder=" " />
            <span>Passwort</span>
          </label>
          <div className="sc-login-form-row">
            <a className="sc-login-link" href="/seniorcare/password-forgotten" onClick={(event) => event.preventDefault()}>Passwort vergessen?</a>
          </div>
          <label className={`sc-check-row${remember ? ' active' : ''}`}>
            <span>Dieses Gerät merken</span>
            <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
            <i aria-hidden="true" />
          </label>
          {error && <div className="sc-form-note" role="alert">{error}</div>}
          <button className="sc-primary-action" type="submit" disabled={busy}>
            <LockKeyhole size={18} />
            {busy ? 'Wir pruefen den Zugang...' : 'Anmelden'}
          </button>
        </form>
      </section>
      <footer className="sc-login-footer">
        <a href="https://www.mma-plus.com/datenschutz" onClick={(event) => event.preventDefault()}>Datenschutz</a>
        <span aria-hidden="true">·</span>
        <a href="https://www.mma-plus.com/impressum" onClick={(event) => event.preventDefault()}>Impressum</a>
      </footer>
    </main>
  );
}
