import type { ReactNode } from 'react';
import type { SeniorCareRouteName } from '../routes/routes';
import { seniorCareNavigation } from '../navigation/navigation';

type Props = {
  route: SeniorCareRouteName;
  onNavigate: (route: SeniorCareRouteName) => void;
  onLogout: () => void;
  children: ReactNode;
};

export function SeniorCareShell({ route, onNavigate, children }: Props) {
  return (
    <main className="sc-app-shell">
      <div className="sc-device-frame">
        <SeniorCareHeader onSetup={() => onNavigate('setup')} />
        <section className="sc-content">{children}</section>
        <SeniorCareBottomNav activeRoute={route} onNavigate={onNavigate} />
      </div>
    </main>
  );
}

export function SeniorCareHeader({ onSetup }: { onSetup: () => void }) {
  return (
    <header className="sc-header">
      <div />
      <button className="sc-brand" type="button" onClick={onSetup} aria-label="SeniorCare Start">
        <span className="sc-brand-dot" />
        <strong>SeniorCare</strong>
      </button>
      <button className="sc-setup-link" type="button" onClick={onSetup}>Einrichten</button>
    </header>
  );
}

export function SeniorCareBottomNav({ activeRoute, onNavigate }: { activeRoute: SeniorCareRouteName; onNavigate: (route: SeniorCareRouteName) => void }) {
  return (
    <nav className="sc-bottom-nav" aria-label="SeniorCare Navigation">
      {seniorCareNavigation.map((item) => (
        <button key={item.route} className={activeRoute === item.route ? 'active' : ''} type="button" onClick={() => onNavigate(item.route)}>
          <span>{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
