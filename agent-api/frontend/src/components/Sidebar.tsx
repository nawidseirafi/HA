import { BarChart3, BellRing, Bot, CalendarDays, Dumbbell, Gauge, LogOut, Play, Settings, Upload, X } from 'lucide-react';
import { useRef, useState } from 'react';
import type { Route } from '../App';
import { api } from '../api/client';
import logo from '../assets/logo.svg';

interface Props {
  route: Route;
  navigate: (route: Route) => void;
  onLogout: () => void;
  isOpen?: boolean;
  onClose?: () => void;
}

export function Sidebar({ route, navigate, onLogout, isOpen = false, onClose }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const isNeutralArea = route.name === 'agents' || route.name === 'settings' || route.name === 'mywellness';

  const runAgent = async () => {
    setBusy(true);
    try {
      await api.runAgent();
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file?: File) => {
    if (!file) return;
    setBusy(true);
    try {
      await api.upload(file);
      navigate({ name: 'invoiceDashboard' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
      <button className="mobile-menu-close" type="button" onClick={onClose} aria-label="Menü schließen">
        <X size={20} />
      </button>
      <div className="brand">
        <div className="brand-logo"><img src={logo} alt="Seirafi" /></div>
        <div>
          <strong>RoboterSteve</strong>
          <span>{isNeutralArea ? 'Agent Console' : 'Invoice Manager'}</span>
        </div>
      </div>
      <nav className="nav-list">
        <button className={route.name === 'agents' ? 'active' : ''} onClick={() => navigate({ name: 'agents' })}>
          <Bot size={18} /> Agenten
        </button>
        {route.name === 'mywellness' && (
          <button className="active" onClick={() => navigate({ name: 'mywellness' })}>
            <Dumbbell size={18} /> MyWellness
          </button>
        )}
        {!isNeutralArea && (
          <>
            <button className={route.name === 'invoiceDashboard' ? 'active' : ''} onClick={() => navigate({ name: 'invoiceDashboard' })}>
              <Gauge size={18} /> Übersicht
            </button>
            <button className={route.name === 'years' || route.name === 'year' || route.name === 'month' ? 'active' : ''} onClick={() => navigate({ name: 'years' })}>
              <CalendarDays size={18} /> Jahre
            </button>
            <button onClick={() => fileRef.current?.click()} disabled={busy}>
              <Upload size={18} /> Belege hochladen
            </button>
            <input ref={fileRef} type="file" hidden onChange={(event) => upload(event.target.files?.[0])} />
            <button onClick={runAgent} disabled={busy}>
              <Play size={18} /> Invoice Agent starten
            </button>
            <button disabled>
              <BarChart3 size={18} /> Exports
            </button>
          </>
        )}
        <button className={route.name === 'settings' ? 'active' : ''} onClick={() => navigate({ name: 'settings' })}>
          <Settings size={18} /> Settings
        </button>
        <button onClick={onLogout}>
          <LogOut size={18} /> Abmelden
        </button>
      </nav>
      <div className="sidebar-note">
        <BellRing size={16} />
        <span>Lokal verbunden. Sitzung ist per JWT geschützt.</span>
      </div>
    </aside>
  );
}
