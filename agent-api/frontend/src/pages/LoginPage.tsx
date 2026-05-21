import { FormEvent, useState } from 'react';
import { LockKeyhole, ShieldCheck } from 'lucide-react';

interface Props {
  onLogin: (accessCode: string) => boolean;
}

export function LoginPage({ onLogin }: Props) {
  const [accessCode, setAccessCode] = useState('');
  const [error, setError] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError('');
    if (!onLogin(accessCode)) {
      setError('Der Zugriffscode ist nicht korrekt.');
    }
  };

  return (
    <main className="login-shell">
      <section className="login-visual">
        <div className="login-brand">
          <div className="brand-mark">RS</div>
          <div>
            <strong>RoboterSteve</strong>
            <span>Agent Console</span>
          </div>
        </div>
        <div className="login-copy">
          <span className="eyebrow">Lokale Verwaltung</span>
          <h1>Deine lokalen Agenten an einem Ort.</h1>
          <p>Agenten starten, Ergebnisse pruefen und lokale Automationen verwalten. Alles auf deinem System, ohne Cloud-Dienst.</p>
        </div>
        <div className="login-assurance">
          <ShieldCheck size={18} />
          <span>Lokaler Zugriff. API-Key/Auth ist vorbereitet.</span>
        </div>
      </section>

      <section className="login-panel">
        <form onSubmit={submit}>
          <div className="login-icon"><LockKeyhole size={24} /></div>
          <h2>Anmelden</h2>
          <p>Gib deinen lokalen Zugriffscode ein.</p>
          <label>
            Zugriffscode
            <input
              autoFocus
              type="password"
              value={accessCode}
              onChange={(event) => setAccessCode(event.target.value)}
              placeholder="Lokaler Code"
            />
          </label>
          {error && <div className="login-error">{error}</div>}
          <button className="button primary login-button" type="submit">Einloggen</button>
          <span className="login-hint">V1 schuetzt die Konsole lokal im Browser. Backend-API-Key folgt als naechster Schritt.</span>
        </form>
      </section>
    </main>
  );
}
