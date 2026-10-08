import { FormEvent, useState } from 'react';
import { ArrowRight, Eye, EyeOff, ScanFace } from 'lucide-react';
import { useAuth } from '@shared/auth/AuthContext';
import logo from '@shared/assets/logo.svg';
import { passkeySupportMessage, passkeyError } from '@shared/auth/passkeys';

interface Props {
  onLoggedIn: () => void;
}

export function LoginForm({ onLoggedIn }: Props) {
  const { login, loginWithPasskey } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const supportMessage = passkeySupportMessage();

  const submitPasskey = async () => {
    setError('');
    setBusy(true);
    setPasskeyBusy(true);
    try {
      await loginWithPasskey(remember);
      onLoggedIn();
    } catch (err) {
      setError(passkeyError(err));
    } finally {
      setBusy(false);
      setPasskeyBusy(false);
    }
  };

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

  const invalid = Boolean(error);

  return (
    <form className={`login-form${invalid ? ' has-error' : ''}`} onSubmit={submit} noValidate>
      <div className="login-form-header">
        <div className="login-icon"><img src={logo} alt="RoboterSteve" /></div>
        <h2>Roboter Steve</h2>
      </div>

      <label className={`auth-field${invalid ? ' invalid' : ''}`}>
        <input
          id="login-username"
          autoFocus
          type="text"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder=" "
          autoComplete="username"
          aria-invalid={invalid}
          aria-label="Benutzername"
        />
        <span className="auth-field-label">Benutzername</span>
        <span className="auth-field-underline" aria-hidden />
      </label>

      <label className={`auth-field has-trailing${invalid ? ' invalid' : ''}`}>
        <input
          id="login-password"
          type={showPassword ? 'text' : 'password'}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder=" "
          autoComplete="current-password"
          aria-invalid={invalid}
          aria-label="Passwort"
        />
        <span className="auth-field-label">Passwort</span>
        <button
          type="button"
          className="field-icon-button"
          onClick={() => setShowPassword((value) => !value)}
          aria-label={showPassword ? 'Passwort verbergen' : 'Passwort anzeigen'}
          tabIndex={-1}
        >
          {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
        </button>
        <span className="auth-field-underline" aria-hidden />
      </label>

      <div className="login-options">
        <label className="remember-switch">
          <input
            type="checkbox"
            checked={remember}
            onChange={(event) => setRemember(event.target.checked)}
          />
          <span className="remember-switch-track" aria-hidden>
            <span className="remember-switch-thumb" />
          </span>
          <span className="remember-switch-label">Auf diesem Gerät angemeldet bleiben</span>
        </label>
      </div>

      {error && <div className="login-error" role="alert">{error}</div>}

      <button className="button primary login-button" type="submit" disabled={busy}>
        <span>{busy && !passkeyBusy ? 'Melde an…' : 'Anmelden'}</span>
        <ArrowRight size={18} />
      </button>

      <button className="button secondary passkey-login-button" type="button" onClick={submitPasskey} disabled={busy || Boolean(supportMessage)} aria-describedby="passkey-hint">
        <ScanFace size={20} />
        <span>{passkeyBusy ? 'Passkey wird bestätigt…' : 'Mit Face ID / Passkey anmelden'}</span>
      </button>
      <span className="login-hint" id="passkey-hint">{supportMessage || 'Zuerst mit Passwort anmelden und unter Settings einen Passkey einrichten. Danach mit Face ID, Touch ID oder Gerätecode bestätigen.'}</span>
    </form>
  );
}
