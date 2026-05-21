import { FormEvent, useState } from 'react';
import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import logo from '../../assets/logo.svg';

interface Props {
  onLoggedIn: () => void;
}

export function LoginForm({ onLoggedIn }: Props) {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
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
      const ok = await login({ email, password, remember });
      if (!ok) {
        setError('Bitte E-Mail-Adresse und Passwort eingeben.');
        return;
      }
      onLoggedIn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="login-form" onSubmit={submit}>
      <div className="login-form-header">
        <div className="login-icon"><img src={logo} alt="RoboterSteve" /></div>
        <h2>Willkommen bei RoboterSteve</h2>
        <p>Bitte melde dich an, um fortzufahren.</p>
      </div>

      <label className="auth-field">
        <span>E-Mail-Adresse</span>
        <div>
          <Mail size={17} />
          <input
            autoFocus
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="nawid@example.local"
            autoComplete="email"
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

      <span className="login-hint">Mock-Login für V1. FastAPI/JWT kann später im AuthContext angebunden werden.</span>
    </form>
  );
}
