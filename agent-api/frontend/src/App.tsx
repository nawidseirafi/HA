import { useEffect, useMemo, useState } from 'react';
import { DashboardPage } from './pages/finance/DashboardPage';
import { YearsPage } from './pages/finance/YearsPage';
import { YearPage } from './pages/finance/YearPage';
import { MonthPage } from './pages/finance/MonthPage';
import { InvoiceDetailPage } from './pages/finance/InvoiceDetailPage';
import { SettingsPage } from './pages/SettingsPage';
import { LoginPage } from './pages/LoginPage';
import { AgentsPage } from './pages/AgentsPage';
import { AgentMapPage } from './pages/AgentMapPage';
import { MessagesPage } from './pages/MessagesPage';
import { MyWellnessDashboardPage } from './pages/mywellness/MyWellnessDashboardPage';
import { MyWellnessCoursesPage } from './pages/mywellness/MyWellnessCoursesPage';
import { MyWellnessBookingsPage } from './pages/mywellness/MyWellnessBookingsPage';
import { MyWellnessHistoryPage } from './pages/mywellness/MyWellnessHistoryPage';
import { MyWellnessHealthPage } from './pages/mywellness/MyWellnessHealthPage';
import { MarketDashboardPage } from './pages/market/MarketDashboardPage';
import { MarketReportsPage } from './pages/market/MarketReportsPage';
import { MarketSymbolPage } from './pages/market/MarketSymbolPage';
import { MarketWatchlistPage } from './pages/market/MarketWatchlistPage';
import { VacationDashboard } from './pages/VacationDashboard';
import { WallDashboardPage } from './pages/WallDashboardPage';
import { Layout } from './components/Layout';
import { AuthProvider, useAuth } from './context/AuthContext';

export type Route =
  | { name: 'wall' }
  | { name: 'agents' }
  | { name: 'agentList' }
  | { name: 'agentMap' }
  | { name: 'agentMessages' }
  | { name: 'mywellnessDashboard' }
  | { name: 'mywellnessCourses' }
  | { name: 'mywellnessBookings' }
  | { name: 'mywellnessHistory' }
  | { name: 'mywellnessHealth' }
  | { name: 'marketDashboard' }
  | { name: 'marketWatchlist' }
  | { name: 'marketReports' }
  | { name: 'marketSymbol'; symbol: string }
  | { name: 'vacationDashboard' }
  | { name: 'invoiceDashboard' }
  | { name: 'years' }
  | { name: 'year'; year: number }
  | { name: 'month'; year: number; month: number }
  | { name: 'invoice'; id: number }
  | { name: 'settings' };

function parseRoute(): Route {
  const parts = window.location.pathname.split('/').filter(Boolean);
  if (parts[0] === 'wall') return { name: 'wall' };
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
  if (parts[0] === 'market' && parts[1] === 'watchlist') return { name: 'marketWatchlist' };
  if (parts[0] === 'market' && parts[1] === 'reports') return { name: 'marketReports' };
  if (parts[0] === 'market' && parts[1]) return { name: 'marketSymbol', symbol: parts[1].toUpperCase() };
  if (parts[0] === 'market') return { name: 'marketDashboard' };
  if (parts[0] === 'vacationDashboard' || parts[0] === 'vacation') return { name: 'vacationDashboard' };
  if (parts[0] === 'years') return { name: 'years' };
  if (parts[0] === 'agents' && (parts[1] === 'invoices' || parts[1] === 'invoiceDashboard')) return { name: 'invoiceDashboard' };
  if (parts[0] === 'agents' && (parts[1] === 'market' || parts[1] === 'marketDashboard')) return { name: 'marketDashboard' };
  if (parts[0] === 'agents' && (parts[1] === 'mywellness' || parts[1] === 'mywellnessDashboard')) return { name: 'mywellnessDashboard' };
  if (parts[0] === 'agents' && (parts[1] === 'vacation-dashboard' || parts[1] === 'vacationDashboard')) return { name: 'vacationDashboard' };
  if (parts[0] === 'agents' && parts[1] === 'list') return { name: 'agentList' };
  if (parts[0] === 'agents' && parts[1] === 'map') return { name: 'agentMap' };
  if (parts[0] === 'agents' && parts[1] === 'messages') return { name: 'agentMessages' };
  if (parts[0] === 'agents') return { name: 'agents' };
  if (parts[0] === 'mywellness' && parts[1] === 'courses') return { name: 'mywellnessCourses' };
  if (parts[0] === 'mywellness' && parts[1] === 'bookings') return { name: 'mywellnessBookings' };
  if (parts[0] === 'mywellness' && parts[1] === 'history') return { name: 'mywellnessHistory' };
  if (parts[0] === 'mywellness' && parts[1] === 'health') return { name: 'mywellnessHealth' };
  if (parts[0] === 'mywellness') return { name: 'mywellnessDashboard' };
  return { name: 'agents' };
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
    if (route.name === 'wall') return <WallDashboardPage />;
    if (route.name === 'agents') return <AgentsPage navigate={navigate} variant="overview" />;
    if (route.name === 'agentList') return <AgentsPage navigate={navigate} variant="agents" />;
    if (route.name === 'agentMap') return <AgentMapPage navigate={navigate} />;
    if (route.name === 'agentMessages') return <MessagesPage />;
    if (route.name === 'mywellnessDashboard') return <MyWellnessDashboardPage navigate={navigate} />;
    if (route.name === 'mywellnessCourses') return <MyWellnessCoursesPage navigate={navigate} />;
    if (route.name === 'mywellnessBookings') return <MyWellnessBookingsPage navigate={navigate} />;
    if (route.name === 'mywellnessHistory') return <MyWellnessHistoryPage navigate={navigate} />;
    if (route.name === 'mywellnessHealth') return <MyWellnessHealthPage />;
    if (route.name === 'marketDashboard') return <MarketDashboardPage navigate={navigate} />;
    if (route.name === 'marketWatchlist') return <MarketWatchlistPage navigate={navigate} />;
    if (route.name === 'marketReports') return <MarketReportsPage navigate={navigate} />;
    if (route.name === 'marketSymbol') return <MarketSymbolPage symbol={route.symbol} />;
    if (route.name === 'vacationDashboard') return <VacationDashboard />;
    if (route.name === 'years') return <YearsPage navigate={navigate} />;
    if (route.name === 'year') return <YearPage year={route.year} navigate={navigate} />;
    if (route.name === 'month') return <MonthPage year={route.year} month={route.month} navigate={navigate} />;
    if (route.name === 'invoice') return <InvoiceDetailPage id={route.id} navigate={navigate} />;
    if (route.name === 'settings') return <SettingsPage />;
    return <DashboardPage navigate={navigate} />;
  }, [route]);

  if (!isAuthenticated) {
    return <LoginPage onLoggedIn={() => setRoute(parseRoute())} />;
  }

  if (route.name === 'wall') {
    return page;
  }

  return (
    <Layout route={route} navigate={navigate} onLogout={logout}>
      {page}
    </Layout>
  );
}

function routeToPath(route: Route) {
  if (route.name === 'wall') return '/wall';
  if (route.name === 'agents') return '/agents';
  if (route.name === 'agentList') return '/agents/list';
  if (route.name === 'agentMap') return '/agents/map';
  if (route.name === 'agentMessages') return '/agents/messages';
  if (route.name === 'mywellnessDashboard') return '/mywellness';
  if (route.name === 'mywellnessCourses') return '/mywellness/courses';
  if (route.name === 'mywellnessBookings') return '/mywellness/bookings';
  if (route.name === 'mywellnessHistory') return '/mywellness/history';
  if (route.name === 'mywellnessHealth') return '/mywellness/health';
  if (route.name === 'marketDashboard') return '/market';
  if (route.name === 'marketWatchlist') return '/market/watchlist';
  if (route.name === 'marketReports') return '/market/reports';
  if (route.name === 'marketSymbol') return `/market/${encodeURIComponent(route.symbol)}`;
  if (route.name === 'vacationDashboard') return '/vacationDashboard';
  if (route.name === 'invoiceDashboard') return '/invoices';
  if (route.name === 'years') return '/invoices/years';
  if (route.name === 'year') return `/invoices/years/${route.year}`;
  if (route.name === 'month') return `/invoices/years/${route.year}/months/${route.month}`;
  if (route.name === 'invoice') return `/invoices/${route.id}`;
  if (route.name === 'settings') return '/settings';
  return '/agents';
}
