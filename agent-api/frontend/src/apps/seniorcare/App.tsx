import { useEffect, useState } from 'react';
import { Bell, HeartHandshake, LayoutDashboard, RadioTower, Settings, UserRoundCheck, Wand2 } from 'lucide-react';
import { api, type AgentManifest } from '@shared/api/client';
import { AuthProvider, useAuth } from '@shared/auth/AuthContext';
import { LoginPage } from './pages/LoginPage';
import { SetupWizardPage } from './pages/SetupWizardPage';
import { DashboardPage } from './pages/DashboardPage';
import { SensorsPage } from './pages/SensorsPage';
import { ContactsPage } from './pages/ContactsPage';
import { NotificationsPage } from './pages/NotificationsPage';
import { SettingsPage } from './pages/SettingsPage';
import type { SeniorCareRoute } from './routes/routes';
import { parseSeniorCareRoute, seniorCareRouteToPath } from './routes/routes';
import { seniorCareNavigation } from './navigation/navigation';

export function App() {
  return (
    <AuthProvider>
      <SeniorCareContent />
    </AuthProvider>
  );
}

function SeniorCareContent() {
  const { isAuthenticated, logout } = useAuth();
  const [route, setRoute] = useState<SeniorCareRoute>(parseSeniorCareRoute());
  const [agents, setAgents] = useState<AgentManifest[]>([]);

  useEffect(() => {
    const onPop = () => setRoute(parseSeniorCareRoute());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    api.agents().then(setAgents).catch(() => setAgents([]));
  }, [isAuthenticated]);

  const navigate = (next: SeniorCareRoute) => {
    window.history.pushState({}, '', seniorCareRouteToPath(next));
    setRoute(next);
  };

  if (!isAuthenticated) {
    return <LoginPage onLoggedIn={() => setRoute(parseSeniorCareRoute())} />;
  }

  return (
    <main className="seniorcare-shell">
      <section className="seniorcare-hero">
        <div>
          <p className="eyebrow">RoboterSteve SeniorCare</p>
          <h1>Betreuungsedition vorbereiten</h1>
          <p>Eine eigenstaendige Produkt-App fuer Betreuung, Sensorik, Kontakte und Hinweise.</p>
        </div>
        <button type="button" onClick={logout}>Abmelden</button>
      </section>

      <nav className="seniorcare-nav" aria-label="SeniorCare Navigation">
        {seniorCareNavigation.map((item) => {
          const Icon = iconMap[item.icon] ?? LayoutDashboard;
          return (
            <button
              key={item.route}
              className={route.name === item.route ? 'active' : ''}
              type="button"
              onClick={() => navigate({ name: item.route })}
            >
              <Icon size={18} />
              {item.label}
            </button>
          );
        })}
      </nav>

      {route.name === 'setup' && <SetupWizardPage agents={agents} />}
      {route.name === 'dashboard' && <DashboardPage agents={agents} />}
      {route.name === 'sensors' && <SensorsPage />}
      {route.name === 'contacts' && <ContactsPage />}
      {route.name === 'notifications' && <NotificationsPage />}
      {route.name === 'settings' && <SettingsPage />}
    </main>
  );
}

const iconMap: Record<string, typeof LayoutDashboard> = {
  Wand2,
  LayoutDashboard,
  RadioTower,
  UserRoundCheck,
  Bell,
  Settings,
  HeartHandshake,
};
