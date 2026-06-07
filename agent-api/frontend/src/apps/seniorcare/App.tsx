import { useEffect, useState } from 'react';
import { Bell, HeartHandshake, LayoutDashboard, RadioTower, Settings, UserRoundCheck, Wand2 } from 'lucide-react';
import { AuthProvider, useAuth } from '@shared/auth/AuthContext';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { SeniorPage } from './pages/SeniorPage';
import { ActivitiesPage } from './pages/ActivitiesPage';
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

  useEffect(() => {
    const onPop = () => setRoute(parseSeniorCareRoute());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

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
          <p className="eyebrow">SeniorCare</p>
          <h1>Guten Abend</h1>
          <p>Ruhiger Ueberblick fuer Alltag, Aktivitaeten, Hinweise und Vertrauenspersonen.</p>
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

      {route.name === 'dashboard' && <DashboardPage />}
      {route.name === 'senior' && <SeniorPage />}
      {route.name === 'activities' && <ActivitiesPage />}
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
