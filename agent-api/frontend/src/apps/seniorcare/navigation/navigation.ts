import type { SeniorCareRouteName } from '../routes/routes';

export type SeniorCareNavIcon = 'Wand2' | 'LayoutDashboard' | 'RadioTower' | 'UserRoundCheck' | 'Bell' | 'Settings';

export const seniorCareNavigation: Array<{ route: SeniorCareRouteName; label: string; icon: SeniorCareNavIcon }> = [
  { route: 'setup', label: 'Setup', icon: 'Wand2' },
  { route: 'dashboard', label: 'Dashboard', icon: 'LayoutDashboard' },
  { route: 'sensors', label: 'Sensoren', icon: 'RadioTower' },
  { route: 'contacts', label: 'Kontakte', icon: 'UserRoundCheck' },
  { route: 'notifications', label: 'Hinweise', icon: 'Bell' },
  { route: 'settings', label: 'Einstellungen', icon: 'Settings' },
];
