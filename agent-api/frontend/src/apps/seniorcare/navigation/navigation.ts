import type { SeniorCareRouteName } from '../routes/routes';

export type SeniorCareNavIcon = 'home' | 'history' | 'rooms' | 'more';

export const seniorCareNavigation: Array<{ route: SeniorCareRouteName; label: string; icon: SeniorCareNavIcon }> = [
  { route: 'dashboard', label: 'Dashboard', icon: 'home' },
  { route: 'setup', label: 'Wizard', icon: 'history' },
  { route: 'settings', label: 'Einstellungen', icon: 'more' },
];
