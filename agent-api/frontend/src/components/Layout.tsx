import type { ReactNode } from 'react';
import type { Route } from '../App';
import { Sidebar } from './Sidebar';

interface Props {
  children: ReactNode;
  route: Route;
  navigate: (route: Route) => void;
  onLogout: () => void;
}

export function Layout({ children, route, navigate, onLogout }: Props) {
  return (
    <div className="app-shell">
      <Sidebar route={route} navigate={navigate} onLogout={onLogout} />
      <main className="main-panel">{children}</main>
    </div>
  );
}
