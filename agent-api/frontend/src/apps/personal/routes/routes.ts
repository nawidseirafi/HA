export type Route =
  | { name: 'wall' }
  | { name: 'agents' }
  | { name: 'agentList' }
  | { name: 'agentMap' }
  | { name: 'agentMessages' }
  | { name: 'mywellnessDashboard' }
  | { name: 'mywellnessCourses' }
  | { name: 'mywellnessBookings' }
  | { name: 'mywellnessHistory' }
  | { name: 'mywellnessHealth' }
  | { name: 'marketDashboard' }
  | { name: 'marketWatchlist' }
  | { name: 'marketReports' }
  | { name: 'marketSymbol'; symbol: string }
  | { name: 'vacationDashboard' }
  | { name: 'schedulerDashboard' }
  | { name: 'invoiceDashboard' }
  | { name: 'years' }
  | { name: 'year'; year: number }
  | { name: 'month'; year: number; month: number }
  | { name: 'invoice'; id: number }
  | { name: 'settings' };
