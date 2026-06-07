export const monthNames = [
  'Januar',
  'Februar',
  'Maerz',
  'April',
  'Mai',
  'Juni',
  'Juli',
  'August',
  'September',
  'Oktober',
  'November',
  'Dezember',
];

export function currency(value?: number | null, code = 'EUR') {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: code }).format(value ?? 0);
}

export function shortDate(value?: string | null) {
  if (!value) return '-';
  return new Intl.DateTimeFormat('de-DE').format(new Date(value));
}
