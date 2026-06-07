export type SeniorCareRoute =
  | { name: 'setup' }
  | { name: 'dashboard' }
  | { name: 'sensors' }
  | { name: 'contacts' }
  | { name: 'notifications' }
  | { name: 'settings' };

export type SeniorCareRouteName = SeniorCareRoute['name'];

export function parseSeniorCareRoute(): SeniorCareRoute {
  const parts = window.location.pathname.split('/').filter(Boolean);
  const first = parts[0] || 'setup';
  if (first === 'dashboard') return { name: 'dashboard' };
  if (first === 'sensors') return { name: 'sensors' };
  if (first === 'contacts') return { name: 'contacts' };
  if (first === 'notifications') return { name: 'notifications' };
  if (first === 'settings') return { name: 'settings' };
  return { name: 'setup' };
}

export function seniorCareRouteToPath(route: SeniorCareRoute): string {
  if (route.name === 'setup') return '/setup';
  return `/${route.name}`;
}
