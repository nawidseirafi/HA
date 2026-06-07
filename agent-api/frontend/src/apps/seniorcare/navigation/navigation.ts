import type { SeniorCareRouteName } from '../routes/routes';

export type SeniorCareNavIcon = 'Wand2' | 'LayoutDashboard' | 'RadioTower' | 'UserRoundCheck' | 'Bell' | 'Settings';

export const seniorCareNavigation: Array<{ route: SeniorCareRouteName; label: string; icon: SeniorCareNavIcon }> = [
  { route: 'dashboard', label: 'Dashboard', icon: 'LayoutDashboard' },
  { route: 'senior', label: 'Senior', icon: 'UserRoundCheck' },
  { route: 'activities', label: 'Aktivitaeten', icon: 'RadioTower' },
  { route: 'notifications', label: 'Benachrichtigungen', icon: 'Bell' },
  { route: 'contacts', label: 'Vertrauenspersonen', icon: 'Wand2' },
  { route: 'settings', label: 'Einstellungen', icon: 'Settings' },
];
