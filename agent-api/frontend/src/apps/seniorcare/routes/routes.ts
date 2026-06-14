export type SeniorCareSettingsTab = 'profile' | 'sensors' | 'contacts' | 'notifications' | 'system';

export type SeniorCareRoute =
  | { name: 'setup' }
  | { name: 'dashboard' }
  | { name: 'history' }
  | { name: 'rooms' }
  | { name: 'contacts' }
  | { name: 'settings'; tab?: SeniorCareSettingsTab };

export type SeniorCareRouteName = SeniorCareRoute['name'];

const routeNames: SeniorCareRouteName[] = ['setup', 'dashboard', 'history', 'rooms', 'contacts', 'settings'];
const settingsTabs: SeniorCareSettingsTab[] = ['profile', 'sensors', 'contacts', 'notifications', 'system'];

export function parseSeniorCareRoute(): SeniorCareRoute {
  const parts = window.location.pathname.split('/').filter(Boolean);
  const candidate = parts[0] === 'seniorcare' ? parts[1] : parts[0];
  const name = routeNames.includes(candidate as SeniorCareRouteName) ? candidate as SeniorCareRouteName : 'dashboard';
  if (name === 'settings') {
    const tabCandidate = parts[0] === 'seniorcare' ? parts[2] : parts[1];
    const tab = settingsTabs.includes(tabCandidate as SeniorCareSettingsTab) ? tabCandidate as SeniorCareSettingsTab : 'profile';
    return { name, tab };
  }
  return { name };
}

export function seniorCareRouteToPath(route: SeniorCareRoute): string {
  if (route.name === 'settings') {
    return `/seniorcare/settings/${route.tab || 'profile'}`;
  }
  return `/seniorcare/${route.name}`;
}
