import { BarChart3, Bot, CalendarDays, FileText, LogOut, Settings } from 'lucide-react';
import type { Route } from '../App';
import logo from '../assets/logo.svg';

interface Props {
  route: Route;
  navigate: (route: Route) => void;
  onLogout: () => void;
}

export function Sidebar({ route, navigate, onLogout }: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-logo"><img src={logo} alt="Seirafi" /></div>
        <div>
          <strong>RoboterSteve</strong>
          <span>Agent Console</span>
        </div>
      </div>
      <nav className="nav-list">
        <button className={route.name === 'agents' ? 'active' : ''} onClick={() => navigate({ name: 'agents' })}>
          <Bot size={18} /> Agenten
        </button>
        <button className={route.name === 'invoiceDashboard' ? 'active' : ''} onClick={() => navigate({ name: 'invoiceDashboard' })}>
          <FileText size={18} /> Rechnungs-Agent
        </button>
        <button className={route.name === 'years' || route.name === 'year' || route.name === 'month' ? 'active' : ''} onClick={() => navigate({ name: 'years' })}>
          <CalendarDays size={18} /> Rechnungsarchiv
        </button>
        <button disabled>
          <BarChart3 size={18} /> Steuerexport
        </button>
        <button className={route.name === 'settings' ? 'active' : ''} onClick={() => navigate({ name: 'settings' })}>
          <Settings size={18} /> Settings
        </button>
        <button onClick={onLogout}>
          <LogOut size={18} /> Abmelden
        </button>
      </nav>
      <div className="sidebar-note">Lokal. Kein Cloud-Dienst. API-Key vorbereitet als naechster Schritt.</div>
    </aside>
  );
}
