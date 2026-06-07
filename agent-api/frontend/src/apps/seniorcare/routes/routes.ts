export type SeniorCareRoute =
  | { name: 'dashboard' }
  | { name: 'senior' }
  | { name: 'activities' }
  | { name: 'contacts' }
  | { name: 'notifications' }
  | { name: 'settings' };

export type SeniorCareRouteName = SeniorCareRoute['name'];

export function parseSeniorCareRoute(): SeniorCareRoute {
  const parts = window.location.pathname.split('/').filter(Boolean);
  const first = parts[0] || 'dashboard';
  if (first === 'dashboard') return { name: 'dashboard' };
  if (first === 'senior') return { name: 'senior' };
  if (first === 'activities') return { name: 'activities' };
  if (first === 'contacts') return { name: 'contacts' };
  if (first === 'notifications') return { name: 'notifications' };
  if (first === 'settings') return { name: 'settings' };
  return { name: 'dashboard' };
}

export function seniorCareRouteToPath(route: SeniorCareRoute): string {
  if (route.name === 'dashboard') return '/dashboard';
  return `/${route.name}`;
}
