export type SeniorCareRoom = {
  id: string;
  name: string;
  status: 'quiet' | 'active' | 'resting';
  summary: string;
  lastSeen: string;
};

export type SeniorCareTimelineItem = {
  id: string;
  time: string;
  title: string;
  text: string;
  tone?: 'calm' | 'note' | 'warm';
};

export type TrustedContact = {
  id: string;
  name: string;
  relation: string;
  note: string;
  email: string;
};

export const seniorProfile = {
  firstName: 'Maria',
  fullName: 'Maria Hoffmann',
  age: 82,
  home: 'Wohnung im Lindenhof',
  currentRoom: 'Wohnzimmer',
  daySummary: 'Maria folgt ihrem gewohnten Tagesablauf.',
  lastActivity: 'Heute 18:52',
  currentSituation: 'Ruhiger Abend im Wohnzimmer',
};

export const todayTimeline: SeniorCareTimelineItem[] = [
  { id: 'morning', time: '08:20', title: 'Fruehstueck in der Kueche', text: 'Ruhiger Start in den Tag.', tone: 'warm' },
  { id: 'kitchen', time: '12:10', title: 'Wohnbereich genutzt', text: 'Der Tagesrhythmus wirkt vertraut.', tone: 'calm' },
  { id: 'door', time: '16:45', title: 'Kurzer Moment am Eingang', text: 'Danach wieder ruhiger Verlauf.', tone: 'note' },
  { id: 'living', time: '18:52', title: 'Wohnzimmer', text: 'Letzte Aktivitaet erkannt.', tone: 'calm' },
];

export const historyTimeline: SeniorCareTimelineItem[] = [
  { id: 'h1', time: 'Heute', title: 'Alles in Ordnung', text: 'Der Tagesverlauf liegt im vertrauten Rahmen.', tone: 'calm' },
  { id: 'h2', time: 'Gestern', title: 'Ruhiger Abend', text: 'Eine sanfte Erinnerung beim naechsten Gespraech genuegt.', tone: 'note' },
  { id: 'h3', time: 'Sonntag', title: 'Besuch am Nachmittag', text: 'Der Nachmittag war aktiver als sonst, danach wieder ruhig.', tone: 'warm' },
  { id: 'h4', time: 'Samstag', title: 'Gewohnter Rhythmus', text: 'Keine besonderen Hinweise im Tagesverlauf.', tone: 'calm' },
];

export const rooms: SeniorCareRoom[] = [
  { id: 'living', name: 'Wohnzimmer', status: 'active', summary: 'Maria haelt sich gerade hier auf.', lastSeen: 'Jetzt' },
  { id: 'kitchen', name: 'Kueche', status: 'quiet', summary: 'Heute zur Mittagszeit genutzt.', lastSeen: '12:10' },
  { id: 'bath', name: 'Bad', status: 'quiet', summary: 'Unauffaelliger Tagesverlauf.', lastSeen: '09:15' },
  { id: 'bedroom', name: 'Schlafzimmer', status: 'resting', summary: 'Bereit fuer den Abend.', lastSeen: 'Heute Morgen' },
  { id: 'entrance', name: 'Eingang', status: 'quiet', summary: 'Seit dem Nachmittag ruhig.', lastSeen: '16:45' },
];

export const trustedContacts: TrustedContact[] = [
  { id: 'max', name: 'Max Hoffmann', relation: 'Sohn', note: 'Erste Vertrauensperson', email: 'max@example.com' },
  { id: 'anna', name: 'Anna Keller', relation: 'Nachbarin', note: 'Kann kurz vorbeischauen', email: 'anna@example.com' },
  { id: 'care', name: 'Pflegedienst Lindenhof', relation: 'Pflegedienst', note: 'Wird bei wichtigen Hinweisen informiert', email: 'pflege@example.com' },
];

export const insightCards = [
  { title: 'Ein leiser Hinweis', text: 'Maria war heute etwas spaeter in der Kueche als sonst. Kein Grund zur Sorge.' },
  { title: 'Naechste Erinnerung', text: 'Beim naechsten Gespraech kann behutsam nach dem Abendessen gefragt werden.' },
];

export const setupOptions = {
  focus: ['Mutter', 'Vater', 'Partnerin', 'Partner', 'Andere Person'],
  home: ['Wohnung', 'Haus', 'Betreutes Wohnen'],
  hints: ['Bewegung', 'Nachtruhe', 'Tueraktivitaet', 'Tagesrhythmus', 'Trinken & Essen', 'Sturzerkennung'],
  sensors: ['Tuer am Eingang', 'Bewegung im Wohnzimmer', 'Bewegung in der Kueche', 'Bad genutzt', 'Schlafzimmer aktiv', 'Notfallknopf'],
};
