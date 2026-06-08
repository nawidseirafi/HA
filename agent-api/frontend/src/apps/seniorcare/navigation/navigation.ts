import type { SeniorCareRouteName } from '../routes/routes';

export type SeniorCareNavIcon = 'home' | 'history' | 'rooms' | 'more';

export const seniorCareNavigation: Array<{ route: SeniorCareRouteName; label: string; icon: SeniorCareNavIcon }> = [
  { route: 'dashboard', label: 'Heute', icon: 'home' },
  { route: 'history', label: 'Verlauf', icon: 'history' },
  { route: 'rooms', label: 'Raeume', icon: 'rooms' },
  { route: 'settings', label: 'Mehr', icon: 'more' },
];
