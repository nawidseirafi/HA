import { Activity, ArrowLeft, BarChart3, Bell, BellRing, Bot, CalendarDays, Dumbbell, Gauge, GitBranch, HeartPulse, LineChart, ListChecks, LogOut, Plane, Play, Settings, Upload, X } from 'lucide-react';
import { useRef, useState } from 'react';
import type { Route } from '../App';
import { api } from '@shared/api/client';
import logo from '@shared/assets/logo.svg';

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
  const agentContext = getAgentContext(route);

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
          <span>{agentContext?.subtitle ?? 'Agent Console'}</span>
        </div>
      </div>
      <nav className="nav-list">
        {agentContext ? (
          <>
            <button className="nav-back-link" onClick={() => navigate({ name: 'agents' })}>
              <ArrowLeft size={18} /> Zur Agent Console
            </button>
            <span className="nav-section-label">{agentContext.label}</span>
            {agentContext.kind === 'invoice' && (
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
                  {busy ? <Activity size={18} /> : <Play size={18} />} {busy ? 'Agent läuft...' : 'Invoice Agent starten'}
                </button>
              </>
            )}
            {agentContext.kind === 'mywellness' && (
              <>
                <button className={route.name === 'mywellnessDashboard' ? 'active' : ''} onClick={() => navigate({ name: 'mywellnessDashboard' })}>
                  <Dumbbell size={18} /> Dashboard
                </button>
                <button className={route.name === 'mywellnessCourses' ? 'active' : ''} onClick={() => navigate({ name: 'mywellnessCourses' })}>
                  <CalendarDays size={18} /> Kurse
                </button>
                <button className={route.name === 'mywellnessBookings' ? 'active' : ''} onClick={() => navigate({ name: 'mywellnessBookings' })}>
                  <ListChecks size={18} /> Buchungen
                </button>
                <button className={route.name === 'mywellnessHistory' ? 'active' : ''} onClick={() => navigate({ name: 'mywellnessHistory' })}>
                  <BarChart3 size={18} /> Verlauf
                </button>
                <button className={route.name === 'mywellnessHealth' ? 'active' : ''} onClick={() => navigate({ name: 'mywellnessHealth' })}>
                  <HeartPulse size={18} /> Health
                </button>
              </>
            )}
            {agentContext.kind === 'market' && (
              <>
                <button className={route.name === 'marketDashboard' ? 'active' : ''} onClick={() => navigate({ name: 'marketDashboard' })}>
                  <LineChart size={18} /> Marktanalyse
                </button>
                <button className={route.name === 'marketWatchlist' ? 'active' : ''} onClick={() => navigate({ name: 'marketWatchlist' })}>
                  <ListChecks size={18} /> Watchlist
                </button>
              </>
            )}
            {agentContext.kind === 'vacation' && (
              <button className={route.name === 'vacationDashboard' ? 'active' : ''} onClick={() => navigate({ name: 'vacationDashboard' })}>
                <Plane size={18} /> Vacation Dashboard
              </button>
            )}
            {agentContext.kind === 'scheduler' && (
              <button className={route.name === 'schedulerDashboard' ? 'active' : ''} onClick={() => navigate({ name: 'schedulerDashboard' })}>
                <CalendarDays size={18} /> Zeitsteuerung
              </button>
            )}
            <button onClick={onLogout}>
              <LogOut size={18} /> Abmelden
            </button>
          </>
        ) : (
          <>
            <button className={route.name === 'agents' ? 'active' : ''} onClick={() => navigate({ name: 'agents' })}>
              <Gauge size={18} /> Übersicht
            </button>
            <button className={route.name === 'agentList' ? 'active' : ''} onClick={() => navigate({ name: 'agentList' })}>
              <Bot size={18} /> Agenten
            </button>
            <button className={route.name === 'agentMap' ? 'active' : ''} onClick={() => navigate({ name: 'agentMap' })}>
              <GitBranch size={18} /> Agent Map
            </button>
            <button className={route.name === 'agentMessages' ? 'active' : ''} onClick={() => navigate({ name: 'agentMessages' })}>
              <Bell size={18} /> Nachrichten
            </button>
            <button className={route.name === 'settings' ? 'active' : ''} onClick={() => navigate({ name: 'settings' })}>
              <Settings size={18} /> System
            </button>
            <button onClick={onLogout}>
              <LogOut size={18} /> Abmelden
            </button>
          </>
        )}
      </nav>
      <div className="sidebar-note">
        <BellRing size={16} />
        <span>Lokal verbunden. Sitzung ist per JWT geschützt.</span>
      </div>
    </aside>
  );
}

type AgentContext = {
  kind: 'invoice' | 'market' | 'mywellness' | 'vacation' | 'scheduler';
  label: string;
  subtitle: string;
};

function getAgentContext(route: Route): AgentContext | null {
  if (route.name === 'invoiceDashboard' || route.name === 'years' || route.name === 'year' || route.name === 'month' || route.name === 'invoice') {
    return { kind: 'invoice', label: 'Invoice Agent', subtitle: 'Invoice Manager' };
  }
  if (route.name === 'marketDashboard' || route.name === 'marketWatchlist' || route.name === 'marketReports' || route.name === 'marketSymbol') {
    return { kind: 'market', label: 'Market Agent', subtitle: 'Market Intelligence' };
  }
  if (route.name === 'mywellnessDashboard' || route.name === 'mywellnessCourses' || route.name === 'mywellnessBookings' || route.name === 'mywellnessHistory' || route.name === 'mywellnessHealth') {
    return { kind: 'mywellness', label: 'MyWellness Agent', subtitle: 'Wellness & Recovery' };
  }
  if (route.name === 'vacationDashboard') {
    return { kind: 'vacation', label: 'Vacation Agent', subtitle: 'Vacation Manager' };
  }
  if (route.name === 'schedulerDashboard') {
    return { kind: 'scheduler', label: 'Scheduler Agent', subtitle: 'Zeitsteuerung' };
  }
  return null;
}
