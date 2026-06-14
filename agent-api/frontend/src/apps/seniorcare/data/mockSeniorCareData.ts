export type GlobalStatus = 'ok' | 'warning' | 'alarm';
export type SensorStatus = 'online' | 'offline';
export type EventTone = 'normal' | 'unusual' | 'alert';
export type SensorType = 'motion' | 'door';

export type SeniorProfile = {
  firstName: string;
  lastName: string;
  fullName: string;
  birthDate: string;
  age: number;
  language: string;
  home: string;
  currentRoom: string;
  lastSeenMinutes: number;
};

export type Room = {
  id: string;
  name: string;
  icon: string;
  status?: 'quiet' | 'active' | 'resting';
  summary?: string;
  lastSeen: string;
  lastSeenMinutes: number;
  sensors: number;
};

export type SeniorCareRoom = Room & {
  status: 'quiet' | 'active' | 'resting';
  summary: string;
};

export type SeniorCareTimelineItem = {
  id: string;
  time: string;
  title: string;
  text: string;
  tone?: 'calm' | 'note' | 'warm';
};

export type Sensor = {
  id: string;
  name: string;
  type: SensorType;
  roomId: string;
  battery: number;
  status: SensorStatus;
  lastSeen: string;
  open?: boolean;
};

export type DoorSensor = Sensor & {
  type: 'door';
  lastOpened: string;
  open: boolean;
};

export type SeniorEvent = {
  id: string;
  time: string;
  icon: string;
  description: string;
  tone: EventTone;
  roomId?: string;
};

export type TrustedContact = {
  id: string;
  name: string;
  relation: string;
  note: string;
  phone: string;
  email: string;
  channels: Array<'WhatsApp' | 'SMS' | 'E-Mail'>;
  lastNotification: string;
};

export const seniorProfile: SeniorProfile = {
  firstName: 'Hildegard',
  lastName: 'Müller',
  fullName: 'Hildegard Müller',
  birthDate: '1948-03-18',
  age: 78,
  language: 'Deutsch',
  home: 'Wohnung am Stadtpark',
  currentRoom: 'Wohnzimmer',
  lastSeenMinutes: 8,
};

export const rooms: SeniorCareRoom[] = [
  { id: 'living_room', name: 'Wohnzimmer', icon: '🛋️', status: 'active', summary: 'Hildegard hält sich gerade hier auf.', lastSeen: 'vor 8 Minuten', lastSeenMinutes: 8, sensors: 1 },
  { id: 'kitchen', name: 'Küche', icon: '🍳', status: 'quiet', summary: 'Heute Morgen normal genutzt.', lastSeen: '09:18', lastSeenMinutes: 76, sensors: 1 },
  { id: 'bathroom', name: 'Bad', icon: '🛁', status: 'quiet', summary: 'Unauffälliger Besuch am Morgen.', lastSeen: '08:32', lastSeenMinutes: 122, sensors: 1 },
  { id: 'bedroom', name: 'Schlafzimmer', icon: '🛏️', status: 'resting', summary: 'Seit dem Aufstehen ruhig.', lastSeen: '06:59', lastSeenMinutes: 215, sensors: 1 },
  { id: 'hallway', name: 'Flur', icon: '🏠', status: 'quiet', summary: 'Haustür zuletzt am Vormittag genutzt.', lastSeen: '09:42', lastSeenMinutes: 52, sensors: 2 },
];

export const sensors: Sensor[] = [
  { id: 'SEN-MOT-101', name: 'Bewegung Wohnzimmer', type: 'motion', roomId: 'living_room', battery: 92, status: 'online', lastSeen: '10:26' },
  { id: 'SEN-MOT-102', name: 'Bewegung Küche', type: 'motion', roomId: 'kitchen', battery: 71, status: 'online', lastSeen: '09:18' },
  { id: 'SEN-MOT-103', name: 'Bewegung Bad', type: 'motion', roomId: 'bathroom', battery: 39, status: 'online', lastSeen: '08:32' },
  { id: 'SEN-MOT-104', name: 'Bewegung Schlafzimmer', type: 'motion', roomId: 'bedroom', battery: 64, status: 'offline', lastSeen: '06:59' },
  { id: 'SEN-DOOR-201', name: 'Haustür', type: 'door', roomId: 'hallway', battery: 88, status: 'online', lastSeen: '09:42', open: false },
  { id: 'SEN-DOOR-202', name: 'Balkontür', type: 'door', roomId: 'living_room', battery: 24, status: 'online', lastSeen: 'Gestern 18:15', open: false },
];

export const doorSensors: DoorSensor[] = [
  { ...(sensors[4] as Sensor), type: 'door', lastOpened: '09:42', open: false },
  { ...(sensors[5] as Sensor), type: 'door', lastOpened: 'Gestern 18:15', open: false },
];

export const events: SeniorEvent[] = [
  { id: 'e01', time: '06:45', icon: '🛏️', description: 'Schlafzimmer verlassen', tone: 'normal', roomId: 'bedroom' },
  { id: 'e02', time: '06:52', icon: '🏠', description: 'Flur betreten', tone: 'normal', roomId: 'hallway' },
  { id: 'e03', time: '07:04', icon: '🍳', description: 'Küche betreten', tone: 'normal', roomId: 'kitchen' },
  { id: 'e04', time: '07:26', icon: '🍳', description: 'Frühstücksaktivität erkannt', tone: 'normal', roomId: 'kitchen' },
  { id: 'e05', time: '08:15', icon: '🚪', description: 'Haustür geöffnet', tone: 'normal', roomId: 'hallway' },
  { id: 'e06', time: '08:32', icon: '🛁', description: 'Bad betreten', tone: 'normal', roomId: 'bathroom' },
  { id: 'e07', time: '08:47', icon: '🛁', description: 'Bad verlassen', tone: 'normal', roomId: 'bathroom' },
  { id: 'e08', time: '09:18', icon: '🍳', description: 'Küche kurz genutzt', tone: 'normal', roomId: 'kitchen' },
  { id: 'e09', time: '09:42', icon: '🚪', description: 'Haustür geöffnet und geschlossen', tone: 'normal', roomId: 'hallway' },
  { id: 'e10', time: '10:02', icon: '🛋️', description: 'Wohnzimmer betreten', tone: 'normal', roomId: 'living_room' },
  { id: 'e11', time: '10:26', icon: '🛋️', description: 'Bewegung im Wohnzimmer', tone: 'normal', roomId: 'living_room' },
  { id: 'e12', time: '11:20', icon: '⏱️', description: 'Längere Ruhephase beginnt', tone: 'unusual', roomId: 'living_room' },
  { id: 'e13', time: '12:54', icon: '⚠️', description: 'Ungewöhnlich lange Pause erkannt', tone: 'unusual', roomId: 'living_room' },
  { id: 'e14', time: '13:08', icon: '📨', description: 'Hinweis an Maria gesendet', tone: 'unusual' },
  { id: 'e15', time: '13:22', icon: '✓', description: 'Bewegung wieder erkannt', tone: 'normal', roomId: 'living_room' },
];

export const trustedContacts: TrustedContact[] = [
  {
    id: 'maria',
    name: 'Maria Schneider',
    relation: 'Tochter',
    note: 'Erste Kontaktperson bei Auffälligkeiten',
    phone: '+49 151 23456789',
    email: 'maria.schneider@example.de',
    channels: ['WhatsApp', 'SMS'],
    lastNotification: 'Heute 13:08',
  },
  {
    id: 'thomas',
    name: 'Thomas Berger',
    relation: 'Nachbar',
    note: 'Kann schnell nach dem Rechten sehen',
    phone: '+49 176 98765432',
    email: 'thomas.berger@example.de',
    channels: ['SMS', 'E-Mail'],
    lastNotification: 'Gestern 19:40',
  },
];

export const activityTimeline = [
  { time: '06:00', room: 'Schlafzimmer', icon: '🛏️', status: 'normal' },
  { time: '07:00', room: 'Küche', icon: '🍳', status: 'normal' },
  { time: '08:00', room: 'Bad', icon: '🛁', status: 'normal' },
  { time: '09:00', room: 'Flur', icon: '🏠', status: 'normal' },
  { time: '10:00', room: 'Wohnzimmer', icon: '🛋️', status: 'normal' },
  { time: '12:00', room: 'Ruhephase', icon: '⏱️', status: 'gap' },
  { time: '13:00', room: 'Wohnzimmer', icon: '🛋️', status: 'normal' },
  { time: '16:00', room: 'Küche', icon: '🍳', status: 'normal' },
  { time: '20:00', room: 'Wohnzimmer', icon: '🛋️', status: 'normal' },
];

export const activityChart = [
  { hour: '06', aktiv: 2 },
  { hour: '07', aktiv: 5 },
  { hour: '08', aktiv: 4 },
  { hour: '09', aktiv: 3 },
  { hour: '10', aktiv: 4 },
  { hour: '11', aktiv: 1 },
  { hour: '12', aktiv: 0 },
  { hour: '13', aktiv: 2 },
  { hour: '14', aktiv: 3 },
  { hour: '15', aktiv: 2 },
  { hour: '16', aktiv: 4 },
  { hour: '17', aktiv: 2 },
  { hour: '18', aktiv: 3 },
  { hour: '19', aktiv: 2 },
  { hour: '20', aktiv: 3 },
  { hour: '21', aktiv: 1 },
  { hour: '22', aktiv: 1 },
];

export const notificationSettings = {
  from: '07:00',
  to: '22:00',
  nightCriticalOnly: true,
  sensitivity: 'Mittel',
  retentionDays: 30,
  template: 'Hallo, bei {name} wurde um {uhrzeit} im Bereich {raum} seit {dauer} keine gewohnte Aktivität erkannt.',
};

export const historyTimeline: SeniorCareTimelineItem[] = [
  { id: 'h1', time: 'Heute', title: 'Alles in Ordnung', text: 'Der Tagesverlauf liegt im vertrauten Rahmen.', tone: 'calm' },
  { id: 'h2', time: 'Gestern', title: 'Veraltete Sensordaten vermieden', text: 'Der aktuelle Zustand wurde neu synchronisiert.', tone: 'note' },
  { id: 'h3', time: 'Samstag', title: 'Ruhiger Abend', text: 'Keine besonderen Hinweise im Tagesverlauf.', tone: 'calm' },
];
