import { Bot, Cpu, LockKeyhole } from 'lucide-react';
import logo from '../assets/logo.svg';
import { LoginForm } from '../components/auth/LoginForm';

interface Props {
  onLoggedIn: () => void;
}

const features = [
  {
    icon: Bot,
    title: 'Agenten zentral steuern',
    text: 'Starte und verwalte deine lokalen KI-Agenten',
  },
  {
    icon: Cpu,
    title: 'Automationen im Blick',
    text: 'Behalte Aufgaben, Ergebnisse und Status im Überblick',
  },
  {
    icon: LockKeyhole,
    title: 'Sicher & Privat',
    text: 'Deine Daten bleiben bei dir',
  },
];

export function LoginPage({ onLoggedIn }: Props) {
  return (
    <main className="login-shell">
      <section className="login-visual">
        <div className="login-brand">
          <div className="brand-logo"><img src={logo} alt="RoboterSteve" /></div>
          <div>
            <strong>RoboterSteve</strong>
            <span>Agent Console</span>
          </div>
        </div>

        <div className="login-copy">
          <span className="eyebrow">Lokale KI-Verwaltung</span>
          <h1>Deine Agenten.<br />Intelligent verwaltet.</h1>
          <p>Steuere, überwache und verwalte deine lokalen KI-Agenten - privat, nachvollziehbar und ohne Cloud-Dienst.</p>
        </div>

        <div className="login-feature-list">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <div className="login-feature" key={feature.title}>
                <div><Icon size={20} /></div>
                <section>
                  <strong>{feature.title}</strong>
                  <span>{feature.text}</span>
                </section>
              </div>
            );
          })}
        </div>
      </section>

      <section className="login-panel">
        <div className="login-card-shell">
          <LoginForm onLoggedIn={onLoggedIn} />
        </div>
      </section>
    </main>
  );
}
