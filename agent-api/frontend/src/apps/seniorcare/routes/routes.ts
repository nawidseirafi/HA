export type SeniorCareRoute =
  | { name: 'setup' }
  | { name: 'dashboard' }
  | { name: 'history' }
  | { name: 'rooms' }
  | { name: 'contacts' }
  | { name: 'settings' };

export type SeniorCareRouteName = SeniorCareRoute['name'];

const routeNames: SeniorCareRouteName[] = ['setup', 'dashboard', 'history', 'rooms', 'contacts', 'settings'];

export function parseSeniorCareRoute(): SeniorCareRoute {
  const parts = window.location.pathname.split('/').filter(Boolean);
  const candidate = parts[0] === 'seniorcare' ? parts[1] : parts[0];
  const name = routeNames.includes(candidate as SeniorCareRouteName) ? candidate as SeniorCareRouteName : 'dashboard';
  return { name };
}

export function seniorCareRouteToPath(route: SeniorCareRoute): string {
  return `/seniorcare/${route.name}`;
}
