import { useEffect, useMemo, useState } from 'react';
import { DashboardPage } from './pages/DashboardPage';
import { YearsPage } from './pages/YearsPage';
import { YearPage } from './pages/YearPage';
import { MonthPage } from './pages/MonthPage';
import { InvoiceDetailPage } from './pages/InvoiceDetailPage';
import { SettingsPage } from './pages/SettingsPage';
import { LoginPage } from './pages/LoginPage';
import { AgentsPage } from './pages/AgentsPage';
import { Layout } from './components/Layout';
import { AuthProvider, useAuth } from './context/AuthContext';

export type Route =
  | { name: 'agents' }
  | { name: 'invoiceDashboard' }
  | { name: 'years' }
  | { name: 'year'; year: number }
  | { name: 'month'; year: number; month: number }
  | { name: 'invoice'; id: number }
  | { name: 'settings' };

function parseRoute(): Route {
  const parts = window.location.pathname.split('/').filter(Boolean);
  if (parts[0] === 'invoices' && parts[1] === 'years' && parts[2] && parts[3] === 'months' && parts[4]) {
    return { name: 'month', year: Number(parts[2]), month: Number(parts[4]) };
  }
  if (parts[0] === 'invoices' && parts[1] === 'years' && parts[2]) return { name: 'year', year: Number(parts[2]) };
  if (parts[0] === 'invoices' && parts[1] === 'years') return { name: 'years' };
  if (parts[0] === 'invoices' && parts[1] && parts[1] !== 'years') return { name: 'invoice', id: Number(parts[1]) };
  if (parts[0] === 'invoices') return { name: 'invoiceDashboard' };
  if (parts[0] === 'years' && parts[1] && parts[2] === 'months' && parts[3]) {
    return { name: 'month', year: Number(parts[1]), month: Number(parts[3]) };
  }
  if (parts[0] === 'years' && parts[1]) return { name: 'year', year: Number(parts[1]) };
  if (parts[0] === 'invoices' && parts[1]) return { name: 'invoice', id: Number(parts[1]) };
  if (parts[0] === 'settings') return { name: 'settings' };
  if (parts[0] === 'years') return { name: 'years' };
  if (parts[0] === 'agents') return { name: 'agents' };
  return { name: 'invoiceDashboard' };
}

export function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

function AppContent() {
  const [route, setRoute] = useState<Route>(parseRoute());
  const { isAuthenticated, logout } = useAuth();

  useEffect(() => {
    const onPop = () => setRoute(parseRoute());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const navigate = (next: Route) => {
    const path = routeToPath(next);
    window.history.pushState({}, '', path);
    setRoute(next);
  };

  const page = useMemo(() => {
    if (route.name === 'agents') return <AgentsPage navigate={navigate} />;
    if (route.name === 'years') return <YearsPage navigate={navigate} />;
    if (route.name === 'year') return <YearPage year={route.year} navigate={navigate} />;
    if (route.name === 'month') return <MonthPage year={route.year} month={route.month} navigate={navigate} />;
    if (route.name === 'invoice') return <InvoiceDetailPage id={route.id} navigate={navigate} />;
    if (route.name === 'settings') return <SettingsPage />;
    return <DashboardPage navigate={navigate} />;
  }, [route]);

  if (!isAuthenticated) {
    return <LoginPage onLoggedIn={() => navigate({ name: 'invoiceDashboard' })} />;
  }

  return (
    <Layout route={route} navigate={navigate} onLogout={logout}>
      {page}
    </Layout>
  );
}

function routeToPath(route: Route) {
  if (route.name === 'agents') return '/agents';
  if (route.name === 'invoiceDashboard') return '/invoices';
  if (route.name === 'years') return '/invoices/years';
  if (route.name === 'year') return `/invoices/years/${route.year}`;
  if (route.name === 'month') return `/invoices/years/${route.year}/months/${route.month}`;
  if (route.name === 'invoice') return `/invoices/${route.id}`;
  if (route.name === 'settings') return '/settings';
  return '/';
}
