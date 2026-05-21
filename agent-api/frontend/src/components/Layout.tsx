import type { ReactNode } from 'react';
import { Menu } from 'lucide-react';
import { useState } from 'react';
import type { Route } from '../App';
import { Sidebar } from './Sidebar';

interface Props {
  children: ReactNode;
  route: Route;
  navigate: (route: Route) => void;
  onLogout: () => void;
}

export function Layout({ children, route, navigate, onLogout }: Props) {
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  const navigateAndClose = (next: Route) => {
    navigate(next);
    setIsMobileNavOpen(false);
  };

  return (
    <div className="app-shell">
      <button className="mobile-menu-toggle" type="button" onClick={() => setIsMobileNavOpen(true)} aria-label="Menü öffnen">
        <Menu size={20} />
      </button>
      {isMobileNavOpen && <button className="mobile-nav-backdrop" type="button" onClick={() => setIsMobileNavOpen(false)} aria-label="Menü schließen" />}
      <Sidebar
        route={route}
        navigate={navigateAndClose}
        onLogout={onLogout}
        isOpen={isMobileNavOpen}
        onClose={() => setIsMobileNavOpen(false)}
      />
      <main className="main-panel">{children}</main>
    </div>
  );
}
