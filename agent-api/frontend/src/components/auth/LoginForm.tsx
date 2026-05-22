import { FormEvent, useState } from 'react';
import { ArrowRight, Eye, EyeOff, LockKeyhole, User } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import logo from '../../assets/logo.svg';

interface Props {
  onLoggedIn: () => void;
}

export function LoginForm({ onLoggedIn }: Props) {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      const ok = await login({ username, password, remember });
      if (!ok) {
        setError('Bitte Benutzername und Passwort eingeben.');
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
    <form className="login-form" onSubmit={submit}>
      <div className="login-form-header">
        <div className="login-icon"><img src={logo} alt="RoboterSteve" /></div>
        <h2>Roboter Steve</h2>
    
      </div>

      <label className="auth-field">
        <span>Benutzername</span>
        <div>
          <User size={17} />
          <input
            autoFocus
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="Benutzername"
            autoComplete="username"
          />
        </div>
      </label>

      <label className="auth-field">
        <span className="field-row">
          Passwort
          <button type="button" className="text-button">Passwort vergessen?</button>
        </span>
        <div>
          <LockKeyhole size={17} />
          <input
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Passwort"
            autoComplete="current-password"
          />
          <button type="button" className="field-icon-button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? 'Passwort verbergen' : 'Passwort anzeigen'}>
            {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
          </button>
        </div>
      </label>

      <div className="login-options">
        <label className="remember-check">
          <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
          <span>Angemeldet bleiben</span>
        </label>
      </div>

      {error && <div className="login-error">{error}</div>}

      <button className="button primary login-button" type="submit" disabled={busy}>
        <span>{busy ? 'Melde an...' : 'Anmelden'}</span>
        <ArrowRight size={18} />
      </button>

      <span className="login-hint"></span>
    </form>
  );
}
