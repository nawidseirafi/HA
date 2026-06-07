export function parseCourseDate(value?: string | null) {
  if (!value) return null;
  if (/^\d{8}$/.test(value)) {
    const year = Number(value.slice(0, 4));
    const month = Number(value.slice(4, 6)) - 1;
    const day = Number(value.slice(6, 8));
    return new Date(year, month, day);
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function relativeDay(date: Date) {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const diffDays = Math.round((target - start) / 86400000);
  if (diffDays === 0) return 'heute';
  if (diffDays === 1) return 'morgen';
  if (diffDays === 2) return 'übermorgen';
  if (diffDays === -1) return 'gestern';
  return new Intl.DateTimeFormat('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit' }).format(date);
}

export function formatCourseDate(value?: string | null) {
  const date = parseCourseDate(value);
  if (!date) return value || '-';
  const day = relativeDay(date);
  const time = new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' }).format(date);
  return time === '00:00' ? day : `${day}, ${time}`;
}

export function courseDayKey(value?: string | null) {
  const date = parseCourseDate(value);
  if (!date) return 'all';
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const diffDays = Math.round((target - start) / 86400000);
  if (diffDays === 0) return 'today';
  if (diffDays === 1) return 'tomorrow';
  if (diffDays === 2) return 'dayAfterTomorrow';
  return 'all';
}
