import { useEffect, useState } from 'react';
import { SenteroAuthProvider, useSenteroAuth } from './auth/SenteroAuthContext';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { HistoryPage } from './pages/HistoryPage';
import { RoomsPage } from './pages/RoomsPage';
import { ContactsPage } from './pages/ContactsPage';
import { SettingsPage } from './pages/SettingsPage';
import { SetupWizardPage } from './pages/SetupWizardPage';
import { SeniorCareShell } from './components/SeniorCareShell';
import type { SeniorCareRoute, SeniorCareRouteName, SeniorCareSettingsTab } from './routes/routes';
import { parseSeniorCareRoute, seniorCareRouteToPath } from './routes/routes';
import './styles/seniorcare.css';

export function App() {
  return (
    <SenteroAuthProvider>
      <SeniorCareContent />
    </SenteroAuthProvider>
  );
}

function SeniorCareContent() {
  const { loading, setupRequired, isAuthenticated, logout } = useSenteroAuth();
  const [route, setRoute] = useState<SeniorCareRoute>(parseSeniorCareRoute());

  useEffect(() => {
    const onPop = () => setRoute(parseSeniorCareRoute());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const navigate = (name: SeniorCareRouteName, tab?: SeniorCareSettingsTab) => {
    const next = name === 'settings' ? { name, tab: tab || 'profile' } as SeniorCareRoute : { name } as SeniorCareRoute;
    window.history.pushState({}, '', seniorCareRouteToPath(next));
    setRoute(next);
  };

  if (loading) {
    return <main className="sc-login-page"><section className="sc-login-card"><p className="sc-muted-note">Sentero wird geladen...</p></section></main>;
  }

  if (setupRequired || !isAuthenticated) {
    return <LoginPage mode={setupRequired ? 'setup' : 'login'} onLoggedIn={(target) => {
      if (target === 'setup') {
        navigate('setup');
        return;
      }
      setRoute(parseSeniorCareRoute());
    }} />;
  }

  return (
    <SeniorCareShell route={route} onNavigate={navigate} onLogout={logout}>
      {route.name === 'setup' && <SetupWizardPage onFinish={() => navigate('dashboard')} />}
      {route.name === 'dashboard' && <DashboardPage />}
      {route.name === 'history' && <HistoryPage />}
      {route.name === 'rooms' && <RoomsPage />}
      {route.name === 'contacts' && <ContactsPage />}
      {route.name === 'settings' && <SettingsPage activeTab={route.tab || 'profile'} />}
    </SeniorCareShell>
  );
}
