import {Component, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import type {ErrorInfo, ReactNode} from 'react';
import {
    Activity,
    ArrowDown,
    ArrowUp,
    Battery,
    BatteryFull,
    BatteryMedium,
    BatteryWarning,
    Bell,
    Bot,
    ChevronRight,
    CloudSun,
    DoorOpen,
    Home,
    Lightbulb,
    Mailbox,
    Layers3,
    Minus,
    Plane,
    Plug,
    Plus,
    Trash2,
    RefreshCw,
    ShieldAlert,
    Square,
    Thermometer,
    Zap,
    Warehouse,
    Wifi,
} from 'lucide-react';
import {
    api,
    type AgentStatus,
    type MessageCenterItem,
    type WallCover,
    type WallDashboardData,
    type WallEntity,
    type WallFan,
    type WallLight,
    type WallLightGroup,
    type WallLightRoom,
    type WallTemperatureSensor
} from '@shared/api/client';
import {AgentMap} from '../components/AgentMap';
import '@shared/styles/wall.css';

type WallSection = 'home' | 'lights' | 'climate' | 'security' | 'agents' | 'floor' | 'room' | 'batteries';
type BatteryBadge = { label: string; tone: string };
type OutletPower = { watts: number; label: string };
type OutletEntity = WallEntity & { outlet_power?: OutletPower | null };
type OutletGroup = { id: string; name: string; items: OutletEntity[]; power?: OutletPower | null };
type InternetStatus = 'ok' | 'down' | 'unstable' | 'unknown';
type FritzboxInfo = {
    status: InternetStatus;
    pillLabel: string;
    cardValue: string;
    cardDetail: string;
    routerName: string;
};
const LOW_BATTERY_THRESHOLD = 40;
type MetricTone =
    | 'info'
    | 'ok'
    | 'warn'
    | 'critical'
    | 'neutral'
    | 'active'
    | 'light'
    | 'climate'
    | 'weather-sunny'
    | 'weather-cloudy'
    | 'weather-rainy'
    | 'weather-night'
    | 'waste-bio'
    | 'waste-paper'
    | 'waste-yellow'
    | 'waste-rest';

export function WallDashboardPage() {
    return (
        <WallErrorBoundary>
            <WallDashboardContent/>
        </WallErrorBoundary>
    );
}

function postStatus(data: WallDashboardData) {
    return data.post?.state === 'on';
}

function vacationStatus(data: WallDashboardData) {
    const agentVacationMode = data.agents.vacation?.vacation_mode;
    const agentVacationActive = agentVacationMode && typeof agentVacationMode === 'object'
        ? agentVacationMode.active === true
        : agentVacationMode === true;
    return agentVacationActive || data.agents.vacation?.vacation_mode_active === true || data.household?.vacation?.vacation_mode === true || data.waste?.context?.vacation_mode === true;
}

function vacationDetail(data: WallDashboardData) {
    const vacation = data.agents.vacation;
    if (vacation?.error) return String(vacation.error);
    return vacationStatus(data) ? 'Haus im Urlaubsmodus' : 'Antippen zum Aktivieren';
}

function wasteTitle(data: WallDashboardData) {
    const waste = data.waste;
    if (!waste?.ok) return 'Keine Daten';
    if (!waste.next) return 'Kein Termin';
    const sameDate = waste.items.filter((item) => item.date && item.date === waste.next?.date);
    const types = sameDate.length ? sameDate.map((item) => shortWasteType(item.type)) : [shortWasteType(waste.next.type)];
    return types.join(' + ');
}

function wasteDetail(data: WallDashboardData) {
    const waste = data.waste;
    if (!waste?.ok) return waste?.error || 'Abfall-Sensor nicht verfügbar';
    if (!waste.next) return 'Sensor meldet keinen nächsten Termin';
    return `${waste.next.date_de || waste.next.date || ''} · ${waste.next.label}`.trim();
}

function weatherTone(data: WallDashboardData): MetricTone {
    const state = String(data.weather?.state || '').toLowerCase();
    if (state.includes('clear-night')) return 'weather-night';
    if (state.includes('sunny') || state.includes('clear')) return 'weather-sunny';
    if (state.includes('rain') || state.includes('pouring') || state.includes('lightning')) return 'weather-rainy';
    if (state.includes('cloud')) return 'weather-cloudy';
    return 'info';
}

function wasteTone(data: WallDashboardData): MetricTone {
    const waste = data.waste;
    if (!waste?.ok || !waste.next) return 'neutral';
    const sameDate = waste.items.filter((item) => item.date && item.date === waste.next?.date);
    const types = (sameDate.length ? sameDate : [waste.next]).map((item) => String(item.type || '').toLowerCase());
    if (types.some((type) => type.includes('bio'))) return 'waste-bio';
    if (types.some((type) => type.includes('gelb') || type.includes('leicht') || type.includes('verpackung'))) return 'waste-yellow';
    if (types.some((type) => type.includes('papier') || type.includes('altpapier') || type.includes('blaue'))) return 'waste-paper';
    if (types.some((type) => type.includes('rest'))) return 'waste-rest';
    return 'neutral';
}

function shortWasteType(value: string) {
    const text = value.toLowerCase();
    if (text.includes('bio')) return 'Bio';
    if (text.includes('papier') || text.includes('altpapier') || text.includes('blaue')) return 'Papier';
    if (text.includes('gelb') || text.includes('leicht') || text.includes('verpackung')) return 'Gelb';
    if (text.includes('rest')) return 'Rest';
    return value;
}

function MessageCenter({ messages, onDeleteAll }: { messages: MessageCenterItem[]; onDeleteAll: () => void }) {
    const groups = groupMessagesByDay(messages);
    return (
        <section className="wall-message-center">
            <div className="wall-message-center-head">
                <div>
                    <span>Nachrichten</span>
                    <strong>Message Center</strong>
                </div>
                <button type="button" onClick={onDeleteAll}>Alle löschen</button>
            </div>
            {groups.length === 0 && <div className="wall-message-empty">Keine Nachrichten vorhanden.</div>}
            {groups.map((group) => (
                <div className="wall-message-group" key={group.label}>
                    <h3>{group.label}</h3>
                    {group.items.map((item) => (
                        <article key={item.id} className={`wall-message-card ${item.severity} ${item.read ? 'read' : 'unread'}`}>
                            <span className="wall-message-icon">{messageIcon(item)}</span>
                            <div>
                                <strong>{item.title}</strong>
                                <p>{item.message}</p>
                                <small>{sourceLabel(item.source)} · {formatDateTime(item.created_at)} · {item.read ? 'gelesen' : 'ungelesen'}</small>
                            </div>
                        </article>
                    ))}
                </div>
            ))}
        </section>
    );
}

function groupMessagesByDay(messages: MessageCenterItem[]) {
    const formatter = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium' });
    const today = formatter.format(new Date());
    const groups = new Map<string, MessageCenterItem[]>();
    for (const item of messages) {
        const date = new Date(item.created_at);
        const label = Number.isNaN(date.getTime()) ? 'Unbekannt' : formatter.format(date) === today ? 'Heute' : formatter.format(date);
        groups.set(label, [...(groups.get(label) ?? []), item]);
    }
    return Array.from(groups.entries()).map(([label, items]) => ({ label, items }));
}

function messageIcon(item: MessageCenterItem) {
    if (item.severity === 'critical') return '!';
    if (item.severity === 'warning') return '!';
    if (item.source === 'market') return '^';
    return 'i';
}

function sourceLabel(source: string) {
    const labels: Record<string, string> = {
        vacation: 'Vacation Agent',
        mywellness: 'MyWellness Agent',
        market: 'Market Agent',
        invoice: 'Invoice Agent',
        household: 'Household',
        system: 'System',
        orchestrator: 'Orchestrator',
    };
    return labels[source] || source;
}

function isBasementArea(area?: string) {
    const value = normalizeArea(area);
    return value.includes('basement') || value.includes('keller');
}

function houseClimateSummary(data: WallDashboardData) {
    const fromHa = data.climate_summary;
    if (fromHa) {
        return {
            houseTemp: fromHa.house_temp ?? null,
            houseHumidity: fromHa.house_humidity ?? null,
            basementTemp: fromHa.basement_temp ?? null,
            basementHumidity: fromHa.basement_humidity ?? null,
        };
    }

    const houseTemps: number[] = [];
    const houseHums: number[] = [];
    const basementTemps: number[] = [];
    const basementHums: number[] = [];

    for (const sensor of data.temperature_sensors ?? []) {
        const area = sensor.area || '';
        const temp = Number(sensor.temperature);
        const hum = Number((sensor as WallTemperatureSensor & { humidity?: number | null }).humidity);

        if (Number.isFinite(temp)) {
            if (isBasementArea(area)) basementTemps.push(temp);
            else houseTemps.push(temp);
        }

        if (Number.isFinite(hum)) {
            if (isBasementArea(area)) basementHums.push(hum);
            else houseHums.push(hum);
        }
    }

    for (const item of data.climate ?? []) {
        const temp = Number(item.current_temperature);
        const hum = Number(item.humidity);

        if (Number.isFinite(temp)) {
            if (isBasementArea(item.area)) basementTemps.push(temp);
            else houseTemps.push(temp);
        }

        if (Number.isFinite(hum)) {
            if (isBasementArea(item.area)) basementHums.push(hum);
            else houseHums.push(hum);
        }
    }

    return {
        houseTemp: avg(houseTemps),
        houseHumidity: avg(houseHums),
        basementTemp: avg(basementTemps),
        basementHumidity: avg(basementHums),
    };
}

function avg(values: number[]) {
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function WallDashboardContent() {
    const [data, setData] = useState<WallDashboardData | null>(null);
    const [section, setSection] = useState<WallSection>('home');
    const [selectedFloor, setSelectedFloor] = useState('Alle Etagen');
    const [floorView, setFloorView] = useState('');
    const [roomView, setRoomView] = useState('');
    const [loading, setLoading] = useState(false);
    const [busyEntity, setBusyEntity] = useState('');
    const [error, setError] = useState('');
    const [runtimeError, setRuntimeError] = useState('');
    const [messages, setMessages] = useState<MessageCenterItem[]>([]);
    const [unreadMessages, setUnreadMessages] = useState(0);
    const [messageCenterOpen, setMessageCenterOpen] = useState(false);
    const [now, setNow] = useState(new Date());
    const brightnessTimers = useRef<Record<string, number>>({});
    const fanTimers = useRef<Record<string, number>>({});
    const refreshTimer = useRef<number | null>(null);

    const load = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        setError('');
        try {
            const [next, messageData, unreadData] = await Promise.all([
                api.wallDashboard(),
                api.messages(60),
                api.unreadMessageCount(),
            ]);
            setData(next);
            setMessages(messageData.messages);
            setUnreadMessages(unreadData.unread_count);
            setSelectedFloor((currentFloor) => (
                currentFloor === 'Alle Etagen' || next.light_groups.some((group) => group.area === currentFloor)
                    ? currentFloor
                    : 'Alle Etagen'
            ));
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Wall-Dashboard konnte nicht geladen werden.');
        } finally {
            if (!silent) setLoading(false);
        }
    }, []);

    const openMessageCenter = async () => {
        setMessageCenterOpen((current) => !current);
        try {
            const [messageData, unreadData] = await Promise.all([api.messages(60), api.unreadMessageCount()]);
            setMessages(messageData.messages);
            setUnreadMessages(unreadData.unread_count);
        } catch {
            // Dashboard data remains usable even if the message center is unavailable.
        }
    };

    const deleteAllMessages = async () => {
        try {
            await api.deleteAllMessages();
            const [messageData, unreadData] = await Promise.all([api.messages(60), api.unreadMessageCount()]);
            setMessages(messageData.messages);
            setUnreadMessages(unreadData.unread_count);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Nachrichten konnten nicht gelöscht werden.');
        }
    };

    useEffect(() => {
        load();
        const refresh = window.setInterval(() => load(true), 15000);
        const clock = window.setInterval(() => setNow(new Date()), 1000);
        const onError = (event: ErrorEvent) => {
            setRuntimeError(event.error instanceof Error ? `${event.error.name}: ${event.error.message}` : event.message);
        };
        const onRejection = (event: PromiseRejectionEvent) => {
            const reason = event.reason;
            setRuntimeError(reason instanceof Error ? `${reason.name}: ${reason.message}` : String(reason));
        };
        window.addEventListener('error', onError);
        window.addEventListener('unhandledrejection', onRejection);
        return () => {
            window.clearInterval(refresh);
            window.clearInterval(clock);
            window.removeEventListener('error', onError);
            window.removeEventListener('unhandledrejection', onRejection);
            if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
            Object.values(brightnessTimers.current).forEach((timer) => window.clearTimeout(timer));
            Object.values(fanTimers.current).forEach((timer) => window.clearTimeout(timer));
        };
    }, [load]);

    const visibleGroups = useMemo(() => {
        if (!data) return [];
        if (selectedFloor === 'Alle Etagen') return data.light_groups;
        return data.light_groups.filter((group) => group.area === selectedFloor);
    }, [data, selectedFloor]);

    const allSelectedLights = useMemo(() => visibleGroups.flatMap((group) => group.items), [visibleGroups]);

    const scheduleRefresh = () => {
        if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
        refreshTimer.current = window.setTimeout(() => load(true), 900);
    };

    const callLight = async (service: 'turn_on' | 'turn_off', entity_id: string | string[], payload: Record<string, unknown> = {}) => {
        const ids = Array.isArray(entity_id) ? entity_id : [entity_id];
        setData((current) => patchWallLights(current, ids, {
            on: service === 'turn_on',
            brightness_pct: typeof payload.brightness_pct === 'number' ? payload.brightness_pct : service === 'turn_off' ? 0 : undefined,
        }));
        setBusyEntity(Array.isArray(entity_id) ? 'bulk' : entity_id);
        setError('');
        try {
            await api.callHomeAssistantService({domain: 'light', service, entity_id, data: payload});
            scheduleRefresh();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Aktion fehlgeschlagen.');
            await load(true);
        } finally {
            setBusyEntity('');
        }
    };

    const setBrightness = (light: WallLight, value: number) => {
        const brightness = clampPercent(value);
        setData((current) => patchWallLights(current, [light.entity_id], {on: true, brightness_pct: brightness}));
        if (brightnessTimers.current[light.entity_id]) {
            window.clearTimeout(brightnessTimers.current[light.entity_id]);
        }
        brightnessTimers.current[light.entity_id] = window.setTimeout(async () => {
            try {
                await api.callHomeAssistantService({
                    domain: 'light',
                    service: 'turn_on',
                    entity_id: light.entity_id,
                    data: {brightness_pct: brightness},
                });
                delete brightnessTimers.current[light.entity_id];
                scheduleRefresh();
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Helligkeit konnte nicht gesetzt werden.');
                delete brightnessTimers.current[light.entity_id];
                await load(true);
            }
        }, 220);
    };

    const turnSelected = async (on: boolean) => {
        const ids = allSelectedLights.map((light) => light.entity_id);
        if (ids.length) await callLight(on ? 'turn_on' : 'turn_off', ids);
    };

    const callFan = async (fan: WallFan, service: string, payload: Record<string, unknown> = {}, patch: Partial<WallFan> = {}) => {
        setData((current) => patchWallFan(current, fan.entity_id, patch));
        setBusyEntity(fan.entity_id);
        setError('');
        try {
            await api.callHomeAssistantService({domain: 'fan', service, entity_id: fan.entity_id, data: payload});
            scheduleRefresh();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Ventilator konnte nicht geschaltet werden.');
            await load(true);
        } finally {
            setBusyEntity('');
        }
    };

    const toggleFan = (fan: WallFan) => {
        const nextOn = !deviceActive(fan);
        void callFan(fan, nextOn ? 'turn_on' : 'turn_off', {}, {state: nextOn ? 'on' : 'off'});
    };

    const setFanPercentage = (fan: WallFan, value: number) => {
        const percentage = clampPercent(value);
        setData((current) => patchWallFan(current, fan.entity_id, {state: percentage > 0 ? 'on' : 'off', percentage}));
        if (fanTimers.current[fan.entity_id]) {
            window.clearTimeout(fanTimers.current[fan.entity_id]);
        }
        fanTimers.current[fan.entity_id] = window.setTimeout(async () => {
            setBusyEntity(fan.entity_id);
            setError('');
            try {
                await api.callHomeAssistantService({
                    domain: 'fan',
                    service: 'set_percentage',
                    entity_id: fan.entity_id,
                    data: {percentage},
                });
                delete fanTimers.current[fan.entity_id];
                scheduleRefresh();
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Ventilatorleistung konnte nicht gesetzt werden.');
                delete fanTimers.current[fan.entity_id];
                await load(true);
            } finally {
                setBusyEntity('');
            }
        }, 260);
    };

    const setFanPreset = (fan: WallFan, presetMode: string) => {
        void callFan(fan, 'set_preset_mode', {preset_mode: presetMode}, {state: 'on', preset_mode: presetMode});
    };

    const toggleFanOscillation = (fan: WallFan) => {
        const oscillating = fan.oscillating !== true;
        void callFan(fan, 'oscillate', {oscillating}, {oscillating});
    };

    const toggleFanDirection = (fan: WallFan) => {
        const nextDirection = String(fan.direction || '').toLowerCase() === 'reverse' ? 'forward' : 'reverse';
        void callFan(fan, 'set_direction', {direction: nextDirection}, {direction: nextDirection});
    };

    const toggleOutlet = async (outlet: WallEntity) => {
        const nextOn = !deviceActive(outlet);
        setData((current) => patchWallSwitch(current, outlet.entity_id, {state: nextOn ? 'on' : 'off'}));
        setBusyEntity(outlet.entity_id);
        setError('');
        try {
            await api.callHomeAssistantService({domain: 'switch', service: nextOn ? 'turn_on' : 'turn_off', entity_id: outlet.entity_id});
            scheduleRefresh();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Steckdose konnte nicht geschaltet werden.');
            await load(true);
        } finally {
            setBusyEntity('');
        }
    };

    const clearPost = async () => {
        const entityId = data?.post?.entity_id;
        if (!entityId || data?.post?.state !== 'on') return;
        setData((current) => current ? {
            ...current,
            post: current.post ? {...current.post, state: 'off'} : current.post
        } : current);
        setBusyEntity(entityId);
        setError('');
        try {
            await api.callHomeAssistantService({domain: 'input_boolean', service: 'turn_off', entity_id: entityId});
            scheduleRefresh();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Post-Status konnte nicht zurückgesetzt werden.');
            await load(true);
        } finally {
            setBusyEntity('');
        }
    };

    const toggleVacation = async () => {
        if (!data) return;
        const entityId = 'input_boolean.vacation_mode';
        const nextOn = !vacationStatus(data);
        setData((current) => {
            if (!current) return current;
            return {
                ...current,
                waste: current.waste ? {
                    ...current.waste,
                    context: {...current.waste.context, vacation_mode: nextOn},
                } : current.waste,
            };
        });
        setBusyEntity(entityId);
        setError('');
        try {
            await (nextOn ? api.enableVacationMode() : api.disableVacationMode());
            scheduleRefresh();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Urlaubsmodus konnte nicht geschaltet werden.');
            await load(true);
        } finally {
            setBusyEntity('');
        }
    };

    const callCover = async (cover: WallCover, service: 'open_cover' | 'close_cover' | 'stop_cover') => {
        const nextState = service === 'open_cover' ? 'opening' : service === 'close_cover' ? 'closing' : cover.state;
        setData((current) => patchWallCover(current, cover.entity_id, {state: nextState}));
        setBusyEntity(cover.entity_id);
        setError('');
        try {
            await api.callHomeAssistantService({domain: 'cover', service, entity_id: cover.entity_id});
            scheduleRefresh();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Garagentor konnte nicht geschaltet werden.');
            await load(true);
        } finally {
            setBusyEntity('');
        }
    };

    const setCoverPosition = async (cover: WallCover, position: number) => {
        const nextPosition = clampPercent(position);
        setData((current) => patchWallCover(current, cover.entity_id, {position: nextPosition}));
        setBusyEntity(cover.entity_id);
        setError('');
        try {
            await api.callHomeAssistantService({
                domain: 'cover',
                service: 'set_cover_position',
                entity_id: cover.entity_id,
                data: {position: nextPosition}
            });
            scheduleRefresh();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Jalousieposition konnte nicht gesetzt werden.');
            await load(true);
        } finally {
            setBusyEntity('');
        }
    };

    const callClimate = async (item: WallDashboardData['climate'][number], service: 'set_hvac_mode' | 'set_temperature', payload: Record<string, unknown>) => {
        setData((current) => patchWallClimate(current, item.entity_id, payload));
        setBusyEntity(item.entity_id);
        setError('');
        try {
            await api.callHomeAssistantService({domain: 'climate', service, entity_id: item.entity_id, data: payload});
            scheduleRefresh();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Klima konnte nicht geschaltet werden.');
            await load(true);
        } finally {
            setBusyEntity('');
        }
    };

    const goSection = (next: WallSection) => {
        setSection(next);
        if (next !== 'floor') setFloorView('');
        if (next !== 'room') setRoomView('');
    };

    const openLights = () => {
        setSelectedFloor('Alle Etagen');
        goSection('lights');
    };

    const openFloor = (floor: string) => {
        setFloorView(floor);
        setSelectedFloor(floor);
        setRoomView('');
        setSection('floor');
    };

    const openFloors = () => {
        const firstFloor = data?.light_groups[0]?.area || '';
        const floor = selectedFloor !== 'Alle Etagen' ? selectedFloor : firstFloor;
        setFloorView(floor);
        setSelectedFloor(floor || 'Alle Etagen');
        setRoomView('');
        setSection('floor');
    };

    const openBatteries = () => {
        setFloorView('');
        setRoomView('');
        setSection('batteries');
    };

    const openClimates = () => {
        setFloorView('');
        setRoomView('');
        setSection('climate');
    };

    const openAgents = () => {
        setFloorView('');
        setRoomView('');
        setSection('agents');
    };

    const openRoom = (floor: string, room: string) => {
        setFloorView(floor);
        setSelectedFloor(floor);
        setRoomView(room);
        setSection('room');
    };

    const activeLights = data?.lights.filter((light) => light.on).length ?? 0;
    const totalLights = data?.lights.length ?? 0;
    const problemCount = (data?.security.problems.length ?? 0) + (data?.health.unavailable.length ?? 0);
    const internetInfo = data ? fritzboxInfo(data) : unknownFritzboxInfo();
    const headerTitle = section === 'floor' ? 'Etagen' : section === 'room' ? roomView || 'Raum' : titleFor(section);

    return (
        <div className="wall-shell">
            <aside className="wall-nav">
                <button className={section === 'home' ? 'active' : ''} onClick={() => goSection('home')}
                        aria-label="Home"><Home size={24}/></button>
                <button className={section === 'floor' || section === 'room' ? 'active' : ''} onClick={openFloors}
                        aria-label="Etagen"><Layers3 size={24}/></button>
                <button className={section === 'lights' ? 'active' : ''} onClick={openLights} aria-label="Lampen">
                    <Lightbulb size={24}/></button>
                <button className={section === 'climate' ? 'active' : ''} onClick={() => goSection('climate')}
                        aria-label="Klima"><Thermometer size={24}/></button>
                <button className={section === 'security' ? 'active' : ''} onClick={() => goSection('security')}
                        aria-label="Sicherheit"><ShieldAlert size={24}/></button>
                <button className={section === 'agents' ? 'active' : ''} onClick={() => goSection('agents')}
                        aria-label="Agenten"><Bot size={24}/></button>
            </aside>

            <main className="wall-main">
                <header className="wall-header">
                    <div>
                        <span>{formatWallDate(now)}</span>
                        <div className="wall-title-row">
                            <h1>{headerTitle}</h1>
                            <InternetStatusPill info={internetInfo}/>
                        </div>
                        <p>{subtitleFor(section, activeLights, totalLights, problemCount, data)}</p>
                    </div>
                    <div className="wall-header-side">
                        <strong>{formatClock(now)}</strong>
                        <button className={`wall-message-button ${unreadMessages ? 'has-unread' : ''}`} type="button" onClick={openMessageCenter} aria-label="Nachrichten">
                            <Bell size={18}/>
                            {unreadMessages > 0 && <span>{unreadMessages > 99 ? '99+' : unreadMessages}</span>}
                        </button>
                        <button type="button" onClick={() => load()} disabled={loading} aria-label="Aktualisieren">
                            <RefreshCw size={18}/> Aktualisieren
                        </button>
                    </div>
                </header>
                {messageCenterOpen && (
                    <MessageCenter messages={messages} onDeleteAll={deleteAllMessages} />
                )}

                {error && <section className="wall-error">{error}</section>}
                {runtimeError && <section className="wall-error">Browserfehler: {runtimeError}</section>}
                {!data && !error && <section className="wall-loading">Lade Home Assistant...</section>}

                {data && section === 'home' &&
                    <HomeSection data={data} busyEntity={busyEntity} onLights={openLights} onFloor={openFloor}
                                 onBatteries={openBatteries} onAgents={openAgents} onClimate={openClimates}
                                 onClearPost={clearPost} onToggleVacation={toggleVacation}
                                 onGarageCommand={callCover}/>}
                {data && section === 'lights' && (
                    <LightsSection
                        data={data}
                        groups={data.light_groups}
                        visibleGroups={visibleGroups}
                        selectedFloor={selectedFloor}
                        busyEntity={busyEntity}
                        onFloor={setSelectedFloor}
                        onToggle={(light) => callLight(light.on ? 'turn_off' : 'turn_on', light.entity_id)}
                        onBrightness={setBrightness}
                        onBulk={turnSelected}
                    />
                )}
                {data && section === 'climate' &&
                    <ClimateSection data={data} selectedFloor={selectedFloor} onFloor={setSelectedFloor}/>}
                {data && section === 'security' && <SecuritySection data={data}/>}
                {data && section === 'agents' && <AgentsSection data={data}/>}
                {data && section === 'batteries' && <BatteriesSection data={data} onBack={() => goSection('home')}/>}
                {data && section === 'floor' && (
                    <FloorSection
                        data={data}
                        floor={floorView}
                        onBack={() => goSection('home')}
                        onFloor={openFloor}
                        onRoom={openRoom}
                    />
                )}
                {data && section === 'room' && (
                    <RoomSection
                        data={data}
                        floor={floorView}
                        room={roomView}
                        busyEntity={busyEntity}
                        onBack={() => setSection('floor')}
                        onToggle={(light) => callLight(light.on ? 'turn_off' : 'turn_on', light.entity_id)}
                        onBrightness={setBrightness}
                        onCoverCommand={callCover}
                        onCoverPosition={setCoverPosition}
                        onClimateMode={(item, mode) => callClimate(item, 'set_hvac_mode', {hvac_mode: mode})}
                        onClimateTemperature={(item, temperature) => callClimate(item, 'set_temperature', {temperature})}
                        onFanToggle={toggleFan}
                        onFanPercentage={setFanPercentage}
                        onFanPreset={setFanPreset}
                        onFanOscillation={toggleFanOscillation}
                        onFanDirection={toggleFanDirection}
                        onOutletToggle={toggleOutlet}
                    />
                )}
            </main>
        </div>
    );
}

function HomeSection({
                         data,
                         onLights,
                         onFloor,
                         onBatteries,
                         onAgents,
                         onClimate,
                         onClearPost,
                         onToggleVacation,
                         onGarageCommand,
                         busyEntity,
                     }: {
    data: WallDashboardData;
    busyEntity: string;
    onLights: () => void;
    onFloor: (floor: string) => void;
    onBatteries: () => void;
    onAgents: () => void;
    onClimate: () => void;
    onClearPost: () => void;
    onToggleVacation: () => void;
    onGarageCommand: (cover: WallCover, service: 'open_cover' | 'close_cover' | 'stop_cover') => void;
}) {
    const hasPost = postStatus(data);
    const vacation = vacationStatus(data);
    const climate = houseClimateSummary(data);
    const activeLights = data.lights.filter((light) => light.on).length;
    const open = data.security.openings_open;
    const issues = data.security.problems.length + data.health.unavailable.length;
    const batterySummary = homeBatterySummary(data);
    const wallBatteries = wallBatteryEntities(data.health.batteries ?? []);
    const wallLowBatteries = wallLowBatteryEntities(data.health.low_batteries ?? []);
    const garage = garageCover(data);
    const internetInfo = fritzboxInfo(data);
    return (
        <div className="wall-home-grid">
            <MetricCard
                icon={<CloudSun size={24}/>}
                label="Wetter"
                value={data.weather?.state ? labelState(data.weather.state) : 'Keine Daten'}
                detail={`${formatNumber(data.weather?.temperature)}°C · ${formatNumber(data.weather?.humidity)}%`}
                tone={weatherTone(data)}
            />
            <MetricCard
                icon={<Thermometer size={24}/>}
                label="Haus ohne Keller"
                value={`Ø ${formatNumber(climate.houseTemp)}°C · ${formatNumber(climate.houseHumidity)}%`}
                detail={`Keller Ø ${formatNumber(climate.basementTemp)}°C · ${formatNumber(climate.basementHumidity)}%`}
                tone="climate"
                onClick={onClimate}
            />
            <MetricCard
                icon={<Trash2 size={24}/>}
                label="Müllabfuhr"
                value={wasteTitle(data)}
                detail={wasteDetail(data)}
                tone={wasteTone(data)}
            />
            <MetricCard
                icon={<Plane size={24}/>}
                label="Vacation Mode"
                value={vacation ? 'Aktiv' : 'Aus'}
                detail={vacationDetail(data)}
                tone={vacation ? 'warn' : 'neutral'}
                onClick={onToggleVacation}
            />
            <MetricCard icon={<Lightbulb size={24}/>} label="Lampen" value={`${activeLights}/${data.lights.length}`}
                        detail="aktiv" tone={activeLights ? 'light' : 'neutral'} onClick={onLights}/>
            <MetricCard icon={<DoorOpen size={24}/>} label="Fenster & Türen"
                        value={`${open}/${data.security.openings_total}`} detail="offen"
                        tone={open ? 'critical' : 'ok'}/>
            <MetricCard
                icon={<Mailbox size={24}/>}
                label="Posteingang"
                value={hasPost ? 'Post da' : 'Leer'}
                detail={hasPost ? 'Antippen zum Zurücksetzen' : 'Briefkasten'}
                tone={hasPost ? 'critical' : hasPost ? 'warn' : 'neutral'}
                onClick={hasPost ? onClearPost : undefined}
            />
            <GarageDoorCard
                cover={garage}
                busy={garage ? busyEntity === garage.entity_id : false}
                onCommand={onGarageCommand}
            />
            <MetricCard icon={batterySummary.icon} label="Batterien" value={`${wallLowBatteries.length}`}
                        detail={`${wallBatteries.length} gesamt`} tone={batterySummary.tone}
                        onClick={onBatteries}/>
            <MetricCard
                icon={<Wifi size={24}/>}
                label="Fritzbox"
                value={internetInfo.cardValue}
                detail={internetInfo.cardDetail}
                tone={internetMetricTone(internetInfo.status)}
            />
            <section className="wall-panel wall-span-2">
                <div className="wall-section-title">
                    <span>Etagen</span>
                    <strong>{data.light_groups.length}</strong>
                </div>
                <div className="wall-area-strip">
                    {data.light_groups.map((group) => (
                        <button key={group.area} type="button" onClick={() => onFloor(group.area)}>
                            <strong>{group.area}</strong>
                            <span>{group.on}/{group.total} Lampen an</span>
                        </button>
                    ))}
                </div>
            </section>
        </div>
    );
}

function FloorSection({
                          data,
                          floor,
                          onBack,
                          onFloor,
                          onRoom,
                      }: {
    data: WallDashboardData;
    floor: string;
    onBack: () => void;
    onFloor: (floor: string) => void;
    onRoom: (floor: string, room: string) => void;
}) {
    const selectedFloor = floor || data.light_groups[0]?.area || '';
    const group = data.light_groups.find((item) => item.area === selectedFloor);
    const rooms = group?.rooms?.length ? group.rooms : group ? [{
        area: group.area,
        total: group.total,
        on: group.on,
        items: group.items
    }] : [];

    return (
        <div className="wall-page-stack">

            <div className="wall-tabs">
                {data.light_groups.map((group) => (
                    <button key={group.area} className={group.area === selectedFloor ? 'active' : ''}
                            onClick={() => onFloor(group.area)}>
                        {group.area}
                        <span>{group.rooms?.length || 1} · Ø {formatNumber(floorTemperature(data, group.area))}°C</span>
                    </button>
                ))}
            </div>
            <div className="wall-room-grid">
                {rooms.map((room) => {
                    const climateLine = roomClimateLine(data, room.area);
                    const roomDeviceTotal = roomOverviewDeviceCount(data, room.area);
                    return (
                        <button className={`wall-room-card wall-click-card ${room.on ? 'room-active' : ''}`}
                                type="button" key={`${selectedFloor}-${room.area}`}
                                onClick={() => onRoom(selectedFloor, room.area)}>
                            <div className="wall-room-head">
                                <span><Lightbulb size={24}/></span>
                                <div>
                                    <h2>{room.area}</h2>
                                    <p>{selectedFloor} · {roomDeviceTotal} Geräte{room.total > 0 ? ` · ${room.on}/${room.total} Lampen an` : ''}
                                        {climateLine ? ` · ${climateLine}` : ''}</p>
                                </div>
                                <ChevronRight size={20}/>
                            </div>
                            <div className="wall-room-summary">
                                <strong>{roomDeviceTotal}</strong>
                                <span>Lampen und Geräte anzeigen</span>
                            </div>
                        </button>
                    );
                })}
                {rooms.length === 0 && <section className="wall-panel">Keine Räume für diese Etage gefunden.</section>}
            </div>
        </div>
    );
}

function RoomSection({
                         data,
                         floor,
                         room,
                         busyEntity,
                         onBack,
                         onToggle,
                         onBrightness,
                         onCoverCommand,
                         onCoverPosition,
                         onClimateMode,
                         onClimateTemperature,
                         onFanToggle,
                         onFanPercentage,
                         onFanPreset,
                         onFanOscillation,
                         onFanDirection,
                         onOutletToggle,
                     }: {
    data: WallDashboardData;
    floor: string;
    room: string;
    busyEntity: string;
    onBack: () => void;
    onToggle: (light: WallLight) => void;
    onBrightness: (light: WallLight, value: number) => void;
    onCoverCommand: (cover: WallCover, service: 'open_cover' | 'close_cover' | 'stop_cover') => void;
    onCoverPosition: (cover: WallCover, position: number) => void;
    onClimateMode: (item: WallDashboardData['climate'][number], mode: string) => void;
    onClimateTemperature: (item: WallDashboardData['climate'][number], temperature: number) => void;
    onFanToggle: (fan: WallFan) => void;
    onFanPercentage: (fan: WallFan, value: number) => void;
    onFanPreset: (fan: WallFan, presetMode: string) => void;
    onFanOscillation: (fan: WallFan) => void;
    onFanDirection: (fan: WallFan) => void;
    onOutletToggle: (outlet: WallEntity) => void;
}) {
    const lights = findRoom(data, floor, room)?.items ?? data.lights.filter((light) => sameArea(light.area, room));
    const covers = (data.covers ?? []).filter((cover) => sameArea(cover.area, room));
    const climates = data.climate.filter((item) => sameArea(item.area, room));
    const fans = (data.fans ?? []).filter((fan) => sameArea(fan.area, room));
    const outlets = roomOutlets(data, room);
    const outletGroups = groupRoomOutlets(outlets, room, data);
    const sensorChips = roomSensorChips(data, room);
    const excluded = new Set([
        ...lights.map((light) => light.entity_id),
        ...covers.map((cover) => cover.entity_id),
        ...climates.map((item) => item.entity_id),
        ...fans.map((fan) => fan.entity_id),
        ...outlets.map((outlet) => outlet.entity_id),
        ...sensorChips.map((chip) => chip.entity_id),
    ]);
    const otherDevices = roomDevices(data, room, excluded);
    const roomTemp = roomTemperature(data, room);
    const roomHumidityValue = roomHumidity(data, room);
    const activeLights = lights.filter((light) => light.on).length;
    const deviceCount = lights.length + covers.length + climates.length + fans.length + outlets.length + sensorChips.length + otherDevices.length;
    const mood = roomMood(data, room, climates);
    const temperatureClass = roomTemperatureClass(roomTemp);

    return (
        <div className="wall-page-stack wall-room-detail-page">

            <section
                className={`wall-room-hero ${temperatureClass} ${activeLights ? 'active' : ''} ${mood.classes.join(' ')}`}>
                <span><Home size={30}/></span>
                <div>
                    <small>{floor}</small>
                    <h2>{room}</h2>
                    <p>
                        {roomTemp !== null ? `${formatNumber(roomTemp)}°C` : '--°C'}
                        {roomHumidityValue !== null ? ` · ${formatNumber(roomHumidityValue)}% Luftfeuchte` : ''}
                    </p>
                    <p>{activeLights ? `${activeLights} Licht an` : 'Licht aus'} · {deviceCount} Geräte</p>
                    {mood.chips.length > 0 && (
                        <div className="wall-room-mood-chips">
                            {mood.chips.map((chip) => <span key={chip.label} className={chip.tone}>{chip.label}</span>)}
                        </div>
                    )}
                </div>
            </section>
            <div className="wall-room-control-grid">
                {lights.length > 0 && (
                    <RoomLightControl
                        lights={lights}
                        busyEntity={busyEntity}
                        onToggle={onToggle}
                        onBrightness={onBrightness}
                    />
                )}
                {climates.map((item) => (
                    <RoomClimateControl
                        key={item.entity_id}
                        item={item}
                        battery={batteryForDeviceName(data, room, item.name)}
                        busy={busyEntity === item.entity_id}
                        onMode={onClimateMode}
                        onTemperature={onClimateTemperature}
                    />
                ))}
                {covers.map((cover) => (
                    <RoomCoverControl
                        key={cover.entity_id}
                        cover={cover}
                        battery={batteryForDeviceName(data, room, cover.name)}
                        busy={busyEntity === cover.entity_id}
                        onCommand={onCoverCommand}
                        onPosition={onCoverPosition}
                    />
                ))}
                {fans.map((fan) => (
                    <RoomFanControl
                        key={fan.entity_id}
                        fan={fan}
                        battery={batteryForDeviceName(data, room, fan.name)}
                        busy={busyEntity === fan.entity_id}
                        onToggle={onFanToggle}
                        onPercentage={onFanPercentage}
                        onPreset={onFanPreset}
                        onOscillation={onFanOscillation}
                        onDirection={onFanDirection}
                    />
                ))}
                {outlets.length > 0 && (
                    <RoomOutletControl
                        groups={outletGroups}
                        busyEntity={busyEntity}
                        onToggle={onOutletToggle}
                    />
                )}
                {sensorChips.length > 0 && (
                    <section className="wall-room-panel wall-room-sensors">
                        <div className="wall-room-panel-title">
                            <span>Sensoren</span>
                            <strong>{sensorChips.length}</strong>
                        </div>
                        <div className="wall-sensor-chip-grid">
                            {sensorChips.map((chip) => (
                                <article key={chip.entity_id} className={`wall-sensor-chip ${chip.tone}`}>
                                    <small>{chip.label}</small>
                                    <strong>{chip.value}{chip.battery && <BatteryPill battery={chip.battery}/>}</strong>
                                </article>
                            ))}
                        </div>
                    </section>
                )}
                {otherDevices.length > 0 && (
                    <section className="wall-room-panel wall-room-devices">
                        <div className="wall-room-panel-title">
                            <span>Geräte</span>
                            <strong>{otherDevices.length}</strong>
                        </div>
                        <div className="wall-device-card-grid">
                            {otherDevices.map((device) => <RoomDeviceCard key={device.entity_id} device={device}
                                                                          battery={batteryForDeviceName(data, room, device.name)}/>)}
                        </div>
                    </section>
                )}
                {lights.length === 0 && climates.length === 0 && covers.length === 0 && fans.length === 0 && outlets.length === 0 && sensorChips.length === 0 && otherDevices.length === 0 && (
                    <section className="wall-room-panel">Keine Geräte für diesen Raum gefunden.</section>
                )}
            </div>
        </div>
    );
}

function RoomLightControl({
                              lights,
                              busyEntity,
                              onToggle,
                              onBrightness,
                          }: {
    lights: WallLight[];
    busyEntity: string;
    onToggle: (light: WallLight) => void;
    onBrightness: (light: WallLight, value: number) => void;
}) {
    const active = lights.filter((light) => light.on);
    const dimmable = lights.filter((light) => light.brightness_pct !== null && light.brightness_pct !== undefined);
    const brightness = active.length ? Math.round(avg(active.map((light) => light.brightness_pct ?? 100)) ?? 100) : 0;
    const busy = lights.some((light) => busyEntity === light.entity_id);
    const setAll = (on: boolean) => lights.forEach((light) => {
        if (light.on !== on) onToggle(light);
    });
    const setScene = (value: number) => {
        dimmable.forEach((light) => onBrightness(light, value));
        lights.filter((light) => !light.on).forEach((light) => onToggle(light));
    };

    return (
        <section className={`wall-room-panel wall-light-control ${active.length ? 'on' : ''}`}>
            <div className="wall-room-panel-title">
                <span>Licht</span>
                <strong>{active.length}/{lights.length}</strong>
            </div>
            <div className="wall-light-control-main">
                <span><Lightbulb size={32}/></span>
                <div>
                    <h3>{active.length ? 'Licht an' : 'Licht aus'}</h3>
                    <p>{active.length ? `${brightness}% Helligkeit` : 'Ruhiger Modus'}</p>
                </div>
                <button type="button" className={`wall-room-power ${active.length ? 'on' : ''}`} disabled={busy}
                        onClick={() => setAll(!active.length)}>
                    {active.length ? 'Ausschalten' : 'Einschalten'}
                </button>
            </div>
            {active.length > 0 && dimmable.length > 0 && (
                <label className="wall-room-slider">
                    <span>Helligkeit</span>
                    <strong>{brightness}%</strong>
                    <input type="range" min="1" max="100" value={brightness}
                           onChange={(event) => setScene(Number(event.target.value))}/>
                </label>
            )}
            <div className="wall-scene-buttons">
                <button type="button" onClick={() => setScene(100)}>Hell</button>
                <button type="button" onClick={() => setScene(35)}>Relax</button>
                <button type="button" onClick={() => setScene(75)}>Sport</button>
                <button type="button" onClick={() => setScene(15)}>Kino</button>
                <button type="button" onClick={() => setAll(false)}>Alles aus</button>
            </div>
        </section>
    );
}

function RoomClimateControl({
                                item,
                                battery,
                                busy,
                                onMode,
                                onTemperature,
                            }: {
    item: WallDashboardData['climate'][number];
    battery?: BatteryBadge | null;
    busy: boolean;
    onMode: (item: WallDashboardData['climate'][number], mode: string) => void;
    onTemperature: (item: WallDashboardData['climate'][number], temperature: number) => void;
}) {
    const mode = String(item.state || 'off').toLowerCase();
    const target = Number(item.target_temperature ?? item.current_temperature ?? 20);
    return (
        <section className={`wall-room-panel wall-climate-control ${climateToneClass(mode)}`}>
            <div className="wall-room-panel-title">
                <span>Klima</span>
                <strong><b
                    className={`wall-climate-status ${climateToneClass(mode)}`}>{labelClimateMode(mode)}</b>{battery &&
                    <BatteryPill battery={battery}/>}</strong>
            </div>
            <div className="wall-climate-dial">
                <button type="button" disabled={busy}
                        onClick={() => onTemperature(item, Math.round((target - 0.5) * 10) / 10)}
                        aria-label="Zieltemperatur senken"><Minus size={20}/></button>
                <div className="wall-thermostat-circle">
                    <strong>{formatNumber(target)}°C</strong>
                    <span>Zieltemperatur</span>
                    <small>Aktuell {formatNumber(item.current_temperature)}°C</small>
                </div>
                <button type="button" disabled={busy}
                        onClick={() => onTemperature(item, Math.round((target + 0.5) * 10) / 10)}
                        aria-label="Zieltemperatur erhöhen"><Plus size={20}/></button>
            </div>
            <div className="wall-mode-buttons">
                {['off', 'heat', 'cool', 'auto', 'dry'].map((nextMode) => (
                    <button key={nextMode} type="button" className={mode === nextMode ? 'active' : ''} disabled={busy}
                            onClick={() => onMode(item, nextMode)}>
                        {labelClimateMode(nextMode)}
                    </button>
                ))}
            </div>
        </section>
    );
}

function RoomCoverControl({
                              cover,
                              battery,
                              busy,
                              onCommand,
                              onPosition,
                          }: {
    cover: WallCover;
    battery?: BatteryBadge | null;
    busy: boolean;
    onCommand: (cover: WallCover, service: 'open_cover' | 'close_cover' | 'stop_cover') => void;
    onPosition: (cover: WallCover, position: number) => void;
}) {
    const position = clampPercent(cover.position ?? (cover.state === 'open' ? 100 : 0));
    return (
        <section className="wall-room-panel wall-cover-control">
            <div className="wall-room-panel-title">
                <span>Jalousien</span>
                <strong>{coverStatus(cover)}{battery && <BatteryPill battery={battery}/>}</strong>
            </div>
            <div className="wall-cover-body">
                <div className="wall-cover-visual" aria-hidden="true">
                    <i style={{height: `${100 - position}%`}}/>
                </div>
                <div>
                    <h3>{cover.name}</h3>
                    <p>{formatNumber(position)}% offen</p>
                    <label className="wall-room-slider compact">
                        <input type="range" min="0" max="100" value={position} disabled={busy}
                               onChange={(event) => onPosition(cover, Number(event.target.value))}/>
                    </label>
                    <div className="wall-cover-actions">
                        <button type="button" disabled={busy || cover.state === 'open'}
                                onClick={() => onCommand(cover, 'open_cover')}><ArrowUp size={18}/> Hoch
                        </button>
                        <button type="button" disabled={busy} onClick={() => onCommand(cover, 'stop_cover')}><Square
                            size={14}/> Stop
                        </button>
                        <button type="button" disabled={busy || cover.state === 'closed'}
                                onClick={() => onCommand(cover, 'close_cover')}><ArrowDown size={18}/> Runter
                        </button>
                    </div>
                </div>
            </div>
        </section>
    );
}

function RoomDeviceCard({
                            device,
                            battery,
                        }: {
    device: WallEntity;
    battery?: BatteryBadge | null;
}) {
    return (
        <article className="wall-room-device-card">
            <div className={`wall-dot ${deviceActive(device) ? 'on' : ''}`}/>
            <div>
                <strong>{device.name}</strong>
                <span>{deviceValue(device)}{battery && <BatteryPill battery={battery}/>}</span>
            </div>
        </article>
    );
}

function RoomOutletControl({
                               groups,
                               busyEntity,
                               onToggle,
                           }: {
    groups: OutletGroup[];
    busyEntity: string;
    onToggle: (outlet: WallEntity) => void;
}) {
    const outlets = groups.flatMap((group) => group.items);
    const active = outlets.filter(deviceActive).length;
    return (
        <section className={`wall-room-panel wall-outlet-control ${active ? 'active' : ''}`}>
            <div className="wall-room-panel-title">
                <span>Steckdosen</span>
                <strong>{active}/{outlets.length} an</strong>
            </div>
            <div className="wall-outlet-group-list">
                {groups.map((group) => {
                    const groupActive = group.items.filter(deviceActive).length;
                    return (
                        <article key={group.id} className={`wall-outlet-group ${groupActive ? 'active' : ''}`}>
                            <div className="wall-outlet-group-head">
                                <span><Plug size={22}/></span>
                                <div>
                                    <strong>{group.name}{group.power && <b>{group.power.label}</b>}</strong>
                                    <small>{group.items.length > 1 ? `${groupActive}/${group.items.length} Ausgänge an` : outletStateLabel(group.items[0])}</small>
                                </div>
                            </div>
                            <div className="wall-outlet-list">
                                {group.items.map((outlet) => {
                                    const isOn = deviceActive(outlet);
                                    const busy = busyEntity === outlet.entity_id;
                                    return (
                                        <button
                                            key={outlet.entity_id}
                                            type="button"
                                            className={`wall-outlet-button ${isOn ? 'on' : ''}`}
                                            disabled={busy}
                                            onClick={() => onToggle(outlet)}
                                            aria-pressed={isOn}
                                        >
                                            <span>{outletDisplayName(outlet, group.name)}{outletPowerLabel(outlet) && <small>{outletPowerLabel(outlet)}</small>}</span>
                                            <i className={`wall-switch ${isOn ? 'on' : ''}`} aria-hidden="true"/>
                                        </button>
                                    );
                                })}
                            </div>
                        </article>
                    );
                })}
            </div>
        </section>
    );
}

function RoomFanControl({
                            fan,
                            battery,
                            busy,
                            onToggle,
                            onPercentage,
                            onPreset,
                            onOscillation,
                            onDirection,
                        }: {
    fan: WallFan;
    battery?: BatteryBadge | null;
    busy?: boolean;
    onToggle?: (fan: WallFan) => void;
    onPercentage?: (fan: WallFan, value: number) => void;
    onPreset?: (fan: WallFan, presetMode: string) => void;
    onOscillation?: (fan: WallFan) => void;
    onDirection?: (fan: WallFan) => void;
}) {
    const percentage = clampPercent(fan.percentage ?? (deviceActive(fan) ? 100 : 0));
    const presetModes = fan.preset_modes ?? [];
    const direction = String(fan.direction || 'forward').toLowerCase();
    return (
        <article className={`wall-room-panel wall-fan-control ${deviceActive(fan) ? 'active' : ''}`}>
            <div className="wall-room-panel-title">
                <span>{fan.name}</span>
                <strong>{busy ? 'Schaltet...' : fanStatusLabel(fan)}{battery && <BatteryPill battery={battery}/>}</strong>
            </div>
            <div className="wall-fan-status-row">
                <span className={`wall-status-dot ${deviceActive(fan) ? 'active' : ''}`}/>
                <span>{deviceActive(fan) ? 'Aktiv' : 'Aus'}</span>
            </div>
            <div className="wall-fan-speed">
                <div>
                    <span>Geschwindigkeit</span>
                    <strong>{percentage}%</strong>
                </div>
                <label className="wall-room-slider compact wall-fan-slider">
                    <input
                        type="range"
                        min="0"
                        max="100"
                        step={fan.percentage_step || 1}
                        value={percentage}
                        disabled={busy}
                        onChange={(event) => onPercentage?.(fan, Number(event.target.value))}
                        aria-label="Ventilator Geschwindigkeit"
                    />
                </label>
            </div>
            <div className="wall-fan-control-list">
                <div className="wall-fan-control-row">
                    <span>Ventilator</span>
                    <button type="button" className={`wall-switch ${deviceActive(fan) ? 'on' : ''}`}
                            disabled={busy} onClick={() => onToggle?.(fan)}
                            aria-pressed={deviceActive(fan)} aria-label="Ventilator ein- oder ausschalten"/>
                </div>
                {fanSupportsOscillation(fan) && (
                    <div className="wall-fan-control-row">
                        <span>Oszillation</span>
                        <button type="button" className={`wall-switch ${fan.oscillating ? 'on' : ''}`}
                                disabled={busy} onClick={() => onOscillation?.(fan)}
                                aria-pressed={fan.oscillating === true} aria-label="Oszillation ein- oder ausschalten"/>
                    </div>
                )}
                {fanSupportsDirection(fan) && (
                    <div className="wall-fan-control-row">
                        <span>Luftstrom</span>
                        <div className="wall-fan-segment" role="group" aria-label="Luftstromrichtung">
                            <button type="button" className={direction !== 'reverse' ? 'active' : ''}
                                    disabled={busy || direction !== 'reverse'} onClick={() => onDirection?.(fan)}>
                                Vorwärts
                            </button>
                            <button type="button" className={direction === 'reverse' ? 'active' : ''}
                                    disabled={busy || direction === 'reverse'} onClick={() => onDirection?.(fan)}>
                                Rückwärts
                            </button>
                        </div>
                    </div>
                )}
                {presetModes.length > 0 && (
                    <label className="wall-fan-control-row wall-fan-select">
                        <span>Modus</span>
                        <select value={fan.preset_mode || ''} disabled={busy}
                                onChange={(event) => onPreset?.(fan, event.target.value)}>
                            {!fan.preset_mode && <option value="">Auswählen</option>}
                            {presetModes.map((mode) => (
                                <option key={mode} value={mode}>{labelFanPreset(mode)}</option>
                            ))}
                        </select>
                    </label>
                )}
            </div>
        </article>
    );
}

function BatteryPill({battery}: { battery: BatteryBadge }) {
    return <em className={`wall-battery-pill ${battery.tone}`}>{battery.label}</em>;
}

function LightsSection({
                           data,
                           groups,
                           visibleGroups,
                           selectedFloor,
                           busyEntity,
                           onFloor,
                           onToggle,
                           onBrightness,
                           onBulk,
                       }: {
    data: WallDashboardData;
    groups: WallLightGroup[];
    visibleGroups: WallLightGroup[];
    selectedFloor: string;
    busyEntity: string;
    onFloor: (floor: string) => void;
    onToggle: (light: WallLight) => void;
    onBrightness: (light: WallLight, value: number) => void;
    onBulk: (on: boolean) => void;
}) {
    const visibleRooms = visibleGroups.flatMap((group) =>
        (group.rooms?.length ? group.rooms : [{
            area: group.area,
            total: group.total,
            on: group.on,
            items: group.items
        }]).map((room) => ({
            ...room,
            floor: group.area,
        })),
    );

    return (
        <div className="wall-lights">
            <div className="wall-tabs">
                <button className={selectedFloor === 'Alle Etagen' ? 'active' : ''}
                        onClick={() => onFloor('Alle Etagen')}>
                    Alle
                    Etagen <span>{groups.reduce((sum, group) => sum + group.on, 0)}/{groups.reduce((sum, group) => sum + group.total, 0)}</span>
                </button>
                {groups.map((group) => (
                    <button key={group.area} className={selectedFloor === group.area ? 'active' : ''}
                            onClick={() => onFloor(group.area)}>
                        {group.area} <span>{group.on}/{group.total}</span>
                    </button>
                ))}
            </div>
            <div className="wall-bulk-actions">
                <button onClick={() => onBulk(false)} disabled={busyEntity === 'bulk'}>Alle aus</button>
                <button className="primary" onClick={() => onBulk(true)} disabled={busyEntity === 'bulk'}>Alle an
                </button>
            </div>
            <div className="wall-room-grid">
                {visibleRooms.map((room) => {
                    const climateLine = roomClimateLine(data, room.area);
                    return (
                        <section className={`wall-room-card ${room.on ? 'room-active' : ''}`}
                                 key={`${room.floor}-${room.area}`}>
                            <div className="wall-room-head">
                                <span><Lightbulb size={24}/></span>
                                <div>
                                    <h2>{room.area}</h2>
                                    <p>{room.floor} · {room.on}/{room.total} an{climateLine ? ` · ${climateLine}` : ''}</p>
                                </div>
                            </div>
                            <div className="wall-light-list">
                                {room.items.map((light) => (
                                    <LightRow
                                        key={light.entity_id}
                                        light={light}
                                        busy={busyEntity === light.entity_id}
                                        onToggle={onToggle}
                                        onBrightness={onBrightness}
                                    />
                                ))}
                            </div>
                        </section>
                    );
                })}
            </div>
        </div>
    );
}

function averageHouseTemperature(data: WallDashboardData) {
    const values = [
        ...(data.temperature_sensors ?? [])
            .map((sensor) => sensor.temperature)
            .filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value))),
        ...data.climate
            .map((item) => item.current_temperature)
            .filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value))),
    ];

    if (!values.length) return null;
    return values.reduce((sum, value) => sum + Number(value), 0) / values.length;
}

function ClimateSection({
                            data,
                            selectedFloor,
                            onFloor,
                        }: {
    data: WallDashboardData;
    selectedFloor: string;
    onFloor: (floor: string) => void;
}) {
    const floor = selectedFloor === 'Alle Etagen' ? 'Alle Etagen' : selectedFloor || data.light_groups[0]?.area || 'Alle Etagen';
    const rooms = temperatureRooms(data, floor);
    const hasClimateData = data.climate.length > 0 || (data.temperature_sensors ?? []).length > 0;
    return (
        <div className="wall-page-stack">
            <div className="wall-tabs">
                <button className={floor === 'Alle Etagen' ? 'active' : ''} onClick={() => onFloor('Alle Etagen')}>
                    Alle Etagen <span>Ø {formatNumber(averageHouseTemperature(data))}°C</span>
                </button>
                {data.light_groups.map((group) => (
                    <button key={group.area} className={floor === group.area ? 'active' : ''}
                            onClick={() => onFloor(group.area)}>
                        {group.area} <span>Ø {formatNumber(floorTemperature(data, group.area))}°C</span>
                    </button>
                ))}
            </div>
            <div className="wall-card-grid">
                {rooms.map((room) => (
                    <section className={`wall-panel wall-temperature-room ${roomTemperatureClass(room.temperature)}`} key={`${room.floor}-${room.area}`}>
                        <div className="wall-section-title">
                            <span>{room.floor}</span>
                            <Thermometer size={20}/>
                        </div>
                        <h2>{room.area}</h2>
                        <div className="wall-climate-value">{formatNumber(room.temperature)}°C</div>
                        <p>{room.humidity !== null ? `${formatNumber(room.humidity)}% Luftfeuchtigkeit` : 'Luftfeuchtigkeit --'}</p>
                        <div className="wall-climate-sensor-chips">
                          {[
                            ...room.climate.map((item) => ({
                              name: item.name.replace(/ Temperatur| Sensor| Gerä/gi, '').trim(),
                              value: item.current_temperature,
                            })),
                            ...room.items
                                .filter(isRoomTemperatureSensor)
                                .map((item) => ({
                                  name: item.name.replace(/ Temperatur| Sensor| Gerä/gi, '').trim(),
                                  value: item.temperature,
                                })),
                          ].slice(0, 2).map((item) => (
                            <span key={item.name}>
                              {item.name} {formatNumber(item.value)}°C
                            </span>
                          ))}

                          {room.climate.length + room.items.length > 2 && (
                            <span>+{room.climate.length + room.items.length - 2}</span>
                          )}
                        </div>
                    </section>
                ))}
                {hasClimateData && rooms.length === 0 &&
                    <section className="wall-panel">Keine Temperaturdaten für diese Etage gefunden.</section>}
                {!hasClimateData && <section className="wall-panel">Keine Temperaturdaten gefunden.</section>}
            </div>
        </div>
    );
}

function SecuritySection({data}: { data: WallDashboardData }) {
    const openItems = data.security.openings.filter((item) => item.state === 'on');
    const wallLowBatteries = wallLowBatteryEntities(data.health.low_batteries ?? []);
    return (
        <div className="wall-card-grid">
            <MetricCard icon={<DoorOpen size={24}/>} label="Offene Kontakte" value={`${openItems.length}`}
                        detail={`${data.security.openings_total} gesamt`} tone={openItems.length ? 'critical' : 'ok'}/>
            <MetricCard icon={<ShieldAlert size={24}/>} label="Probleme" value={`${data.security.problems.length}`}
                        detail="gemeldet" tone={data.security.problems.length ? 'critical' : 'ok'}/>
            <MetricCard icon={<Zap size={24}/>} label="Offline" value={`${data.health.unavailable.length}`}
                        detail="unknown/unavailable" tone={data.health.unavailable.length ? 'neutral' : 'ok'}/>
            <MetricCard icon={<BatteryWarning size={24}/>} label="Batterie"
                        value={`${wallLowBatteries.length}`} detail="niedrig"
                        tone={wallLowBatteries.length ? 'critical' : 'ok'}/>
            <ListPanel title="Offene Fenster & Türen" items={openItems}/>
            <ListPanel title="Niedrige Batterien" items={wallLowBatteries}/>
            <ListPanel title="Nicht erreichbar" items={data.health.unavailable.slice(0, 12)}/>
        </div>
    );
}

function BatteriesSection({data, onBack}: { data: WallDashboardData; onBack: () => void }) {
    const batteries = wallBatteryEntities(data.health.batteries ?? data.health.low_batteries);
    return (
        <div className="wall-page-stack">

            <section className="wall-panel wall-list-panel wall-battery-panel">
                <div className="wall-section-title">
                    <span>Batterien</span>
                    <strong>{batteries.length}</strong>
                </div>
                {batteries.length === 0 ? <p>Keine Batterie-Entities gefunden.</p> : batteries.map((battery) => (
                    <article className="wall-battery-row" key={battery.entity_id}>
                        <div>
                            <strong>{battery.name}</strong>
                            <span>{battery.area || 'Haus'} · {battery.entity_id}</span>
                        </div>
                        <div className="wall-battery-status">
                            <b>{formatBatteryLevel(battery)}</b>
                            <span className={`wall-battery-bar ${batteryTone(battery)}`}>
                <i style={{width: `${batteryBarWidth(battery)}%`}}/>
              </span>
                        </div>
                    </article>
                ))}
            </section>
        </div>
    );
}

function AgentsSection({data: _data}: { data: WallDashboardData }) {
    return (
        <div className="wall-agent-map-surface">
            <AgentMap navigate={() => undefined} chrome={false} interactive={false}/>
        </div>
    );
}

function homeAgentState(data: WallDashboardData) {
    if (data.agents.invoices.is_running || data.agents.mywellness.is_running) return 'Aktiv';
    if (data.agents.invoices.enabled === false && data.agents.mywellness.enabled === false) return 'Pausiert';
    return 'Bereit';
}

function homeAgentTone(data: WallDashboardData): MetricTone {
    const invoices = data.agents.invoices;
    const wellness = data.agents.mywellness;
    const market = data.agents.market;
    if (invoices.status === 'error' || wellness.status === 'error' || market.status === 'error') return 'critical';
    if (invoices.is_running || wellness.is_running) return 'active';
    if (invoices.enabled === false || wellness.enabled === false) return 'warn';
    if (invoices.last_status === 'ok' || wellness.last_status === 'ok' || market.status === 'ok') return 'ok';
    return 'neutral';
}

function homeAgentDetail(data: WallDashboardData) {
    const invoiceNext = formatAgentNextRun(data.agents.invoices.next_scheduled_run, data.agents.invoices.schedule);
    return data.agents.invoices.enabled === false ? 'Invoice pausiert' : `Invoice ${invoiceNext}`;
}

function invoiceState(invoices: WallDashboardData['agents']['invoices']) {
    if (invoices.status !== 'ok') return 'Fehler';
    if (invoices.is_running) return 'Läuft';
    if (invoices.enabled === false) return 'Pausiert';
    return 'Aktiv';
}

function LightRow({
                      light,
                      busy,
                      onToggle,
                      onBrightness,
                  }: {
    light: WallLight;
    busy: boolean;
    onToggle: (light: WallLight) => void;
    onBrightness: (light: WallLight, value: number) => void;
}) {
    const brightness = clampPercent(light.brightness_pct ?? (light.on ? 100 : 0));
    return (
        <article className="wall-light-row">
            <div className={`wall-dot ${light.on ? 'on' : ''}`}/>
            <div>
                <strong>{light.name}</strong>
                <label>
                    <span>Helligkeit</span>
                    <span>{brightness}%</span>
                </label>
                <input
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    value={brightness}
                    onChange={(event) => onBrightness(light, Number(event.target.value))}
                />
            </div>
            <button className={`wall-switch ${light.on ? 'on' : ''}`} onClick={() => onToggle(light)} disabled={busy}
                    aria-label={`${light.name} schalten`}/>
        </article>
    );
}

function DeviceRow({device}: { device: WallEntity }) {
    return (
        <article className="wall-device-row">
            <div className={`wall-dot ${deviceActive(device) ? 'on' : ''}`}/>
            <div>
                <strong>{device.name}</strong>
                <span>{device.entity_id}</span>
            </div>
            <b>{deviceValue(device)}</b>
        </article>
    );
}

function MetricCard({icon, label, value, detail, tone = 'info', onClick}: {
    icon: ReactNode;
    label: string;
    value: string;
    detail: string;
    tone?: MetricTone;
    onClick?: () => void
}) {
    const content = (
        <>
            <span>{icon}</span>
            <div>
                <small>{label}</small>
                <strong>{value}</strong>
                <p>{detail}</p>
            </div>
        </>
    );
    if (onClick) {
        return <button className={`wall-metric wall-click-card ${tone}`} type="button"
                       onClick={onClick}>{content}</button>;
    }
    return <section className={`wall-metric ${tone}`}>{content}</section>;
}

function GarageDoorCard({
                            cover,
                            busy,
                            onCommand,
                        }: {
    cover: WallCover | null;
    busy: boolean;
    onCommand: (cover: WallCover, service: 'open_cover' | 'close_cover' | 'stop_cover') => void;
}) {
    const state = String(cover?.state || '').toLowerCase();
    const offline = !cover || state === 'unavailable' || state === 'unknown';
    const open = state === 'open';
    const moving = ['opening', 'closing'].includes(state);
    const status = offline ? 'Offline' : moving ? 'Bewegt sich' : open ? 'Geöffnet' : state === 'closed' ? 'Geschlossen' : garageDoorState(cover);
    const detail = offline ? 'Verbindung nicht verfügbar' : coverPositionDetail(cover);
    return (
        <section className={`wall-metric wall-garage-card ${garageDoorClass(state, offline)}`}>
            <span><Warehouse size={24}/></span>
            <div className="wall-garage-copy">
                <small>Garage</small>
                <strong>{status}</strong>
                <p>{detail}</p>
            </div>
            <div className="wall-garage-actions">
                <button type="button" className="open" disabled={offline || busy || state === 'open'}
                        onClick={() => cover && onCommand(cover, 'open_cover')} aria-label="Garagentor öffnen"
                        title="Öffnen">
                    <ArrowUp size={22}/>
                </button>
                <button type="button" className="close" disabled={offline || busy || state === 'closed'}
                        onClick={() => cover && onCommand(cover, 'close_cover')} aria-label="Garagentor schließen"
                        title="Schließen">
                    <ArrowDown size={22}/>
                </button>
            </div>
        </section>
    );
}

class WallErrorBoundary extends Component<{ children: ReactNode }, { message: string; stack: string }> {
    state = {message: '', stack: ''};

    static getDerivedStateFromError(error: Error) {
        return {message: `${error.name}: ${error.message}`, stack: ''};
    }

    componentDidCatch(_error: Error, info: ErrorInfo) {
        this.setState({stack: info.componentStack || ''});
    }

    render() {
        if (this.state.message) {
            return (
                <div className="wall-shell">
                    <main className="wall-main">
                        <section className="wall-error">
                            <strong>Wall-Dashboard Fehler</strong>
                            <p>{this.state.message}</p>
                            {this.state.stack && <pre>{this.state.stack}</pre>}
                        </section>
                    </main>
                </div>
            );
        }
        return this.props.children;
    }
}

function ListPanel({title, items}: {
    title: string;
    items: Array<{ entity_id: string; name: string; state: string; area?: string }>
}) {
    return (
        <section className="wall-panel wall-list-panel">
            <div className="wall-section-title"><span>{title}</span><strong>{items.length}</strong></div>
            {items.length === 0 ? <p>Alles ruhig.</p> : items.slice(0, 8).map((item) => (
                <article key={item.entity_id}>
                    <strong>{item.name}</strong>
                    <span>{item.area || 'Haus'} · {labelState(item.state)}</span>
                </article>
            ))}
        </section>
    );
}


function InternetStatusPill({info}: { info: FritzboxInfo }) {
    return <span className={`wall-internet-pill ${info.status}`}/>;
}

function unknownFritzboxInfo(): FritzboxInfo {
    return {
        status: 'unknown',
        pillLabel: 'Unbekannt',
        cardValue: 'Unbekannt',
        cardDetail: 'Fritzbox-Daten nicht geladen',
        routerName: 'Fritzbox',
    };
}

function fritzboxInfo(data: WallDashboardData): FritzboxInfo {
    const source = data as unknown as Record<string, unknown>;
    const explicit = firstRecord(source.fritzbox, source.fritz_box, source.internet, source.network);
    const entities = allWallEntities(data);
    const fritzEntities = entities.filter((entity) => {
        const text = `${entity.entity_id} ${entity.name} ${entity.area || ''}`.toLowerCase();
        return text.includes('fritz') || text.includes('wan') || text.includes('internet') || text.includes('dsl');
    });
    const connectionDetail = fritzboxConnectionDetail(explicit, fritzEntities);
    const infrastructure = firstRecord(data.household?.infrastructure);
    if (infrastructure && hasInfrastructureSignal(infrastructure)) {
        const status = internetStatusFromText(stringValue(infrastructure.status), []);
        const connectedDevices = stringValue(infrastructure.connected_devices);
        const wifi = stringValue(infrastructure.wifi);
        const detail = stringValue(
            infrastructure.detail,
            connectedDevices ? `${connectedDevices} Geräte` : '',
            wifi ? `WLAN ${wifi}` : '',
        );
        return {
            status,
            pillLabel: internetStatusLabel(status),
            cardValue: status === 'ok' ? 'Internet OK' : status === 'down' ? 'Gestört' : status === 'unstable' ? 'Instabil' : 'Unbekannt',
            cardDetail: connectionDetail || detail || stringValue(infrastructure.router, 'Fritzbox'),
            routerName: stringValue(infrastructure.router, 'Fritzbox'),
        };
    }

    const explicitStatus = explicit ? stringValue(explicit.status, explicit.internet_status, explicit.connection, explicit.state) : '';
    const relevantState = stringValue(
        explicitStatus,
        findEntityValue(fritzEntities, ['internet', 'connection']),
        findEntityValue(fritzEntities, ['wan']),
        findEntityValue(fritzEntities, ['dsl']),
    );
    const status = internetStatusFromText(relevantState, fritzEntities);
    const routerName = stringValue(explicit?.name, explicit?.model, findEntityName(fritzEntities, ['fritz']), 'Fritzbox');
    return {
        status,
        pillLabel: internetStatusLabel(status),
        cardValue: status === 'ok' ? 'Internet OK' : status === 'down' ? 'Gestört' : status === 'unstable' ? 'Instabil' : 'Unbekannt',
        cardDetail: connectionDetail || routerName,
        routerName,
    };
}

function fritzboxConnectionDetail(explicit: Record<string, unknown> | null, fritzEntities: WallEntity[]) {
    const down = stringValue(
        explicit?.downstream,
        explicit?.download,
        explicit?.rx_rate,
        findEntityValue(fritzEntities, ['downstream']),
        findEntityValue(fritzEntities, ['download']),
    );
    const up = stringValue(
        explicit?.upstream,
        explicit?.upload,
        explicit?.tx_rate,
        findEntityValue(fritzEntities, ['upstream']),
        findEntityValue(fritzEntities, ['upload']),
    );
    const ip = stringValue(explicit?.external_ip, explicit?.ip, explicit?.wan_ip, findEntityValue(fritzEntities, ['external', 'ip']));
    const uptime = stringValue(explicit?.uptime, findEntityValue(fritzEntities, ['uptime']));
    const detailParts = [
        down || up ? `↓ ${down || '--'} · ↑ ${up || '--'}` : '',
        ip ? `IP ${ip}` : '',
        uptime ? `Uptime ${uptime}` : '',
    ].filter(Boolean);
    return detailParts[0] || '';
}

function hasInfrastructureSignal(infrastructure: Record<string, unknown>) {
    const status = stringValue(infrastructure.status).toLowerCase();
    if (status && status !== 'unknown') return true;
    const checks = firstRecord(infrastructure.checks);
    if (!checks) return false;
    return Object.values(checks).some((value) => {
        const check = firstRecord(value);
        if (!check) return false;
        return check.configured === true || check.discovered === true;
    });
}

function internetStatusFromText(value: string, entities: WallEntity[]): InternetStatus {
    const text = value.toLowerCase();
    if (['unavailable', 'unknown', ''].includes(text)) {
        const states = entities.map((entity) => String(entity.state || '').toLowerCase());
        const hasOnline = states.some((state) => /(connected|online|ok|on|up|available|verbunden)/i.test(state));
        const hasUnavailable = states.some((state) => ['unavailable', 'unknown', 'off', 'down'].includes(state));
        if (hasOnline) return 'ok';
        return hasUnavailable ? 'down' : 'unknown';
    }
    if (/(critical|disconnect|offline|down|gestört|stoer|fehler|failed|problem|not connected)/i.test(text)) return 'down';
    if (/(instabil|unstable|reconnect|packet|loss|warning|warn|limited)/i.test(text)) return 'unstable';
    if (/(connected|online|ok|on|up|available|verbunden)/i.test(text)) return 'ok';
    return 'unknown';
}

function internetStatusLabel(status: InternetStatus) {
    if (status === 'ok') return 'Internet OK';
    if (status === 'down') return 'Internet gestört';
    if (status === 'unstable') return 'Instabil';
    return 'Unbekannt';
}

function internetMetricTone(status: InternetStatus): MetricTone {
    if (status === 'ok') return 'ok';
    if (status === 'down') return 'critical';
    if (status === 'unstable') return 'warn';
    return 'neutral';
}

function firstRecord(...values: unknown[]): Record<string, unknown> | null {
    return values.find((value): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)) ?? null;
}

function stringValue(...values: unknown[]) {
    for (const value of values) {
        if (value === null || value === undefined) continue;
        const text = String(value).trim();
        if (text) return text;
    }
    return '';
}

function allWallEntities(data: WallDashboardData): WallEntity[] {
    return [
        ...(data.sensors ?? []),
        ...(data.lights ?? []),
        ...(data.security?.openings ?? []),
        ...(data.security?.problems ?? []),
        ...(data.health?.unavailable ?? []),
        ...(data.health?.batteries ?? []),
        ...(data.switches ?? []),
        ...(data.fans ?? []),
        ...(data.media_players ?? []),
        ...(data.temperature_sensors ?? []),
    ] as WallEntity[];
}

function findEntityValue(entities: WallEntity[], needles: string[]) {
    const entity = entities.find((item) => {
        const text = `${item.entity_id} ${item.name}`.toLowerCase();
        return needles.every((needle) => text.includes(needle));
    });
    return entity ? deviceValue(entity) : '';
}

function findEntityName(entities: WallEntity[], needles: string[]) {
    const entity = entities.find((item) => {
        const text = `${item.entity_id} ${item.name}`.toLowerCase();
        return needles.every((needle) => text.includes(needle));
    });
    return entity?.name || '';
}

function titleFor(section: WallSection) {
    if (section === 'lights') return 'Lampen';
    if (section === 'climate') return 'Klima';
    if (section === 'security') return 'Sicherheit';
    if (section === 'agents') return 'Agenten';
    if (section === 'batteries') return 'Batterien';
    return 'Zuhause';
}

function subtitleFor(section: WallSection, activeLights: number, totalLights: number, problemCount: number, data?: WallDashboardData | null) {
    if (section === 'lights') return `${activeLights} von ${totalLights} aktiv`;
    if (section === 'floor') return 'Etage wählen und Räume öffnen';
    if (section === 'room') return 'Geräte in diesem Raum';
    if (section === 'batteries') return 'Batteriestände und Status aller Batterie-Geräte';
    if (section === 'security') return problemCount ? `${problemCount} Geräte prüfen` : 'Keine Geräte auffällig';
    if (section === 'agents') return 'Lokale Automationen und Agentenstatus';
    if (section === 'climate') return 'Temperaturen, Luftfeuchte und Thermostate';
    if (section === 'home' && data) return `Aktualisiert ${formatTime(data.updated_at)} · ${data.home_assistant.entity_count} Home-Assistant-Entities`;
    return 'Hausstatus, Geräte und Agenten auf einen Blick';
}

function formatBatteryLevel(battery: WallEntity & { level?: number | null }) {
    if (battery.level !== null && battery.level !== undefined) return `${Math.round(battery.level)}%`;
    return labelState(battery.state);
}

function homeBatterySummary(data: WallDashboardData): { tone: MetricTone; icon: ReactNode } {
    const batteries = wallBatteryEntities(data.health.batteries ?? []);
    const hasUnknown = batteries.some((battery) => battery.level === null || battery.level === undefined || ['unknown', 'unavailable'].includes(String(battery.state).toLowerCase()));
    const levels = batteries
        .map((battery) => battery.level)
        .filter((level): level is number => level !== null && level !== undefined && Number.isFinite(Number(level)));
    const minLevel = levels.length ? Math.min(...levels) : null;
    if (batteries.some((battery) => String(battery.state).toLowerCase() === 'low') || (minLevel !== null && minLevel < LOW_BATTERY_THRESHOLD)) {
        return {tone: 'critical', icon: <BatteryWarning size={24}/>};
    }
    if (minLevel !== null && minLevel <= 60) {
        return {tone: 'warn', icon: <BatteryMedium size={24}/>};
    }
    if (hasUnknown) {
        return {tone: 'neutral', icon: <Battery size={24}/>};
    }
    return {tone: 'ok', icon: <BatteryFull size={24}/>};
}

function wallBatteryEntities(items: Array<WallEntity & { level?: number | null }>) {
    return items.filter((item) => isWallBatteryEntity(item));
}

function wallLowBatteryEntities(items: Array<WallEntity & { level?: number | null }>) {
    return wallBatteryEntities(items).filter((battery) => {
        const level = battery.level;
        return String(battery.state || '').toLowerCase() === 'low'
            || (level !== null && level !== undefined && Number.isFinite(Number(level)) && Number(level) < LOW_BATTERY_THRESHOLD);
    });
}

function isWallBatteryEntity(item: WallEntity) {
    const entityId = String(item.entity_id || '').toLowerCase();
    if (!entityId.startsWith('sensor.')) return false;
    const objectId = entityId.split('.', 2)[1] || entityId;
    return objectId.endsWith('_battery') || objectId.endsWith('_batterie');
}

function garageCover(data: WallDashboardData): WallCover | null {
    const covers = data.covers ?? [];
    return covers.find((cover) => {
        const haystack = `${cover.entity_id} ${cover.name} ${cover.area} ${cover.device_class || ''}`.toLowerCase();
        return haystack.includes('garage') || haystack.includes('garagen') || haystack.includes('garagentor');
    }) ?? covers.find((cover) => {
        const haystack = `${cover.entity_id} ${cover.name} ${cover.area}`.toLowerCase();
        return haystack.includes('tor');
    }) ?? null;
}

function garageDoorState(cover: WallCover) {
    const state = String(cover.state || '').toLowerCase();
    if (state === 'open') return 'Offen';
    if (state === 'closed') return 'Geschlossen';
    if (state === 'opening') return 'Öffnet';
    if (state === 'closing') return 'Schließt';
    if (state === 'unavailable' || state === 'unknown') return 'Nicht verfügbar';
    return labelState(cover.state);
}

function garageDoorClass(state: string, offline: boolean) {
    if (offline) return 'offline';
    if (state === 'open') return 'open';
    if (state === 'opening' || state === 'closing') return 'moving';
    return 'closed';
}

function coverPositionDetail(cover: WallCover) {
    if (cover.position !== null && cover.position !== undefined && Number.isFinite(Number(cover.position))) {
        return `${formatNumber(cover.position)}% offen`;
    }
    return labelState(cover.state);
}

function batteryBarWidth(battery: WallEntity & { level?: number | null }) {
    if (battery.level === null || battery.level === undefined || !Number.isFinite(Number(battery.level))) {
        return battery.state?.toLowerCase() === 'low' ? 12 : 100;
    }
    return Math.max(0, Math.min(100, Math.round(Number(battery.level))));
}

function batteryTone(battery: WallEntity & { level?: number | null }) {
    const level = battery.level;
    if (battery.state?.toLowerCase() === 'low') return 'warn';
    if (level === null || level === undefined) return 'unknown';
    if (level <= 15) return 'danger';
    if (level < LOW_BATTERY_THRESHOLD) return 'warn';
    return 'ok';
}

function findRoom(data: WallDashboardData, floor: string, room: string): WallLightRoom | undefined {
    const group = data.light_groups.find((item) => item.area === floor);
    return group?.rooms?.find((item) => sameArea(item.area, room));
}

function floorRooms(data: WallDashboardData, floor: string) {
    const group = data.light_groups.find((item) => item.area === floor);
    if (!group) return [];
    return group.rooms?.length ? group.rooms : [{
        area: group.area,
        total: group.total,
        on: group.on,
        items: group.items
    }];
}

function floorTemperature(data: WallDashboardData, floor: string) {
    const roomNames = new Set(floorRooms(data, floor).map((room) => normalizeArea(room.area)));
    if (!roomNames.size) return null;
    const values = [
        ...(data.temperature_sensors ?? [])
            .filter((sensor) => roomNames.has(normalizeArea(sensor.area)))
            .map((sensor) => sensor.temperature),
        ...data.climate
            .filter((item) => roomNames.has(normalizeArea(item.area)))
            .map((item) => item.current_temperature),
    ].filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value)));

    return avg(values.map(Number));
}

function roomDevices(data: WallDashboardData, room: string, exclude: Set<string>) {
    const devices: WallEntity[] = [
        ...(data.switches ?? []).filter((device) => !isOutletDevice(device)),
        ...(data.media_players ?? []),
    ];
    const unique = new Map<string, WallEntity>();
    for (const device of devices) {
        if (exclude.has(device.entity_id) || !sameArea(device.area, room)) continue;
        unique.set(device.entity_id, device);
    }
    return [...unique.values()].sort((left, right) => left.name.localeCompare(right.name));
}

function roomOutlets(data: WallDashboardData, room: string) {
    return (data.switches ?? [])
        .filter((device) => sameArea(device.area, room) && isOutletDevice(device))
        .sort((left, right) => left.name.localeCompare(right.name));
}

function isOutletDevice(device: WallEntity) {
    const deviceClass = String(device.device_class || '').toLowerCase();
    const text = `${device.entity_id} ${device.name}`.toLowerCase();
    return deviceClass === 'outlet' || [
        'steckdose',
        'mehrfachsteckdose',
        'zwischenstecker',
        'socket',
        'outlet',
        'plug',
        'power strip',
        'powerstrip',
    ].some((needle) => text.includes(needle));
}

function groupRoomOutlets(outlets: WallEntity[], room: string, data: WallDashboardData): OutletGroup[] {
    const buckets = new Map<string, OutletEntity[]>();
    for (const outlet of outlets) {
        const key = outletGroupKey(outlet, room);
        buckets.set(key, [...(buckets.get(key) ?? []), {...outlet, outlet_power: outletPower(data, room, outlet)}]);
    }
    return [...buckets.entries()]
        .map(([key, items]) => {
            const sorted = items.sort((left, right) => outletSortValue(left) - outletSortValue(right) || left.name.localeCompare(right.name));
            const itemPowers = sorted.map((item) => item.outlet_power).filter((power): power is OutletPower => Boolean(power));
            const groupPower = itemPowers.length
                ? outletPowerFromWatts(itemPowers.reduce((sum, power) => sum + power.watts, 0))
                : outletGroupPower(data, room, key, sorted);
            return {
                id: key,
                name: sorted.length > 1 ? outletGroupName(sorted[0], room) : sorted[0].name,
                items: sorted,
                power: groupPower,
            };
        })
        .sort((left, right) => left.name.localeCompare(right.name));
}

function outletGroupKey(outlet: WallEntity, room: string) {
    const normalized = normalizeOutletName(outlet.name, room);
    const base = normalized
        .replace(/\b(steckdose|mehrfachsteckdose|zwischenstecker|socket|outlet|plug|power strip|powerstrip)\b/g, ' ')
        .replace(/\b(port|kanal|channel|gang|outlet|socket)?\s*\d+$/g, ' ')
        .replace(/\b(l|r|left|right|links|rechts)$/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    return base || 'steckdosen';
}

function outletGroupName(outlet: WallEntity, room: string) {
    const normalized = normalizeOutletName(outlet.name, room);
    const base = normalized
        .replace(/\b(steckdose|socket|outlet|plug)\b/g, ' ')
        .replace(/\b(port|kanal|channel|gang|outlet|socket)?\s*\d+$/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    return titleCase(base || 'Mehrfachsteckdose');
}

function outletDisplayName(outlet: WallEntity, groupName: string) {
    const name = outlet.name.trim();
    const group = groupName.trim();
    if (group && normalizeOutletName(name, '') !== normalizeOutletName(group, '')) {
        const shortened = name.replace(new RegExp(escapeRegExp(group), 'i'), '').replace(/^[-–—:\s]+|[-–—:\s]+$/g, '').trim();
        if (shortened && shortened.length >= 2) return shortened;
    }
    const suffix = name.match(/(?:^|[\s_-])(?:port|kanal|channel|gang|outlet|socket)?\s*(\d+)\s*$/i);
    if (suffix) return `Ausgang ${suffix[1]}`;
    return name;
}

function outletSortValue(outlet: WallEntity) {
    const match = `${outlet.name} ${outlet.entity_id}`.match(/(?:^|[\s_-])(\d+)(?:\D*)$/);
    return match ? Number(match[1]) : 999;
}

function outletStateLabel(outlet: WallEntity) {
    return deviceActive(outlet) ? 'Eingeschaltet' : labelState(outlet.state);
}

function outletPowerLabel(outlet: OutletEntity) {
    return outlet.outlet_power?.label || '';
}

function outletPower(data: WallDashboardData, room: string, outlet: WallEntity): OutletPower | null {
    const outletTokens = outletMatchTokens(outlet, room);
    if (!outletTokens.length) return null;
    const candidates = roomPowerSensors(data, room)
        .map((sensor) => {
            const sensorTokens = powerSensorMatchTokens(sensor, room);
            const overlap = sensorTokens.filter((token) => outletTokens.includes(token));
            const contains = normalizedEntityBase(sensor).includes(normalizedEntityBase(outlet))
                || normalizedEntityBase(outlet).includes(normalizedEntityBase(sensor));
            return {
                sensor,
                score: overlap.length * 4 + (contains ? 6 : 0) + (sameArea(sensor.area, outlet.area) ? 2 : 0),
            };
        })
        .filter((item) => item.score >= 6)
        .sort((left, right) => right.score - left.score);
    return candidates[0] ? powerFromSensor(candidates[0].sensor) : null;
}

function outletGroupPower(data: WallDashboardData, room: string, groupKey: string, outlets: OutletEntity[]): OutletPower | null {
    const sensors = roomPowerSensors(data, room)
        .filter((sensor) => !outlets.some((outlet) => outlet.outlet_power && outletPower(data, room, outlet)?.label === outlet.outlet_power?.label));
    const match = sensors
        .map((sensor) => {
            const tokens = powerSensorMatchTokens(sensor, room);
            const score = tokens.includes(groupKey) ? 10 : tokens.filter((token) => groupKey.includes(token) || token.includes(groupKey)).length * 3;
            return {sensor, score};
        })
        .filter((item) => item.score > 0)
        .sort((left, right) => right.score - left.score)[0];
    return match ? powerFromSensor(match.sensor) : null;
}

function roomPowerSensors(data: WallDashboardData, room: string) {
    return (data.sensors ?? []).filter((sensor) => sameArea(sensor.area, room) && isPowerSensor(sensor));
}

function isPowerSensor(sensor: WallEntity) {
    const deviceClass = String(sensor.device_class || '').toLowerCase();
    const unit = String(sensor.unit || '').trim().toLowerCase();
    const text = `${sensor.entity_id} ${sensor.name}`.toLowerCase();
    return _numericWallState(sensor) !== null && (
        deviceClass === 'power' ||
        unit === 'w' ||
        unit === 'kw' ||
        text.includes('leistung') ||
        text.includes('power')
    );
}

function powerFromSensor(sensor: WallEntity): OutletPower | null {
    const raw = _numericWallState(sensor);
    if (raw === null) return null;
    const unit = String(sensor.unit || '').trim().toLowerCase();
    const watts = unit === 'kw' ? raw * 1000 : raw;
    return outletPowerFromWatts(watts);
}

function outletPowerFromWatts(watts: number): OutletPower | null {
    if (!Number.isFinite(watts)) return null;
    const clean = Math.max(0, watts);
    return {
        watts: clean,
        label: clean >= 1000 ? `${formatNumber(clean / 1000)} kW` : `${formatNumber(clean)} W`,
    };
}

function outletMatchTokens(outlet: WallEntity, room: string) {
    return uniqueTokens(`${normalizeOutletName(outlet.name, room)} ${normalizedEntityBase(outlet)}`)
        .filter((token) => !outletNoiseTokens().has(token));
}

function powerSensorMatchTokens(sensor: WallEntity, room: string) {
    return uniqueTokens(`${normalizeOutletName(sensor.name, room)} ${normalizedEntityBase(sensor)}`)
        .filter((token) => !outletNoiseTokens().has(token) && !new Set(['leistung', 'power', 'energy', 'verbrauch', 'watt', 'w']).has(token));
}

function normalizedEntityBase(entity: WallEntity) {
    return normalizeArea(String(entity.entity_id || '').split('.', 2)[1] || entity.entity_id);
}

function uniqueTokens(value: string) {
    return Array.from(new Set(normalizeArea(value).split(/\s+/).filter((token) => token.length >= 2)));
}

function outletNoiseTokens() {
    return new Set(['switch', 'sensor', 'steckdose', 'mehrfachsteckdose', 'zwischenstecker', 'socket', 'outlet', 'plug', 'powerstrip', 'power', 'strip']);
}

function _numericWallState(entity: WallEntity) {
    const value = Number.parseFloat(String(entity.state || '').replace(',', '.'));
    return Number.isFinite(value) ? value : null;
}

function normalizeOutletName(value: string, room: string) {
    let text = normalizeArea(value)
        .replace(/\./g, ' ')
        .replace(/\b(switch)\b/g, ' ');
    const roomText = normalizeArea(room);
    if (roomText) text = text.replace(new RegExp(`\\b${escapeRegExp(roomText)}\\b`, 'g'), ' ');
    return text.replace(/\s+/g, ' ').trim();
}

function titleCase(value: string) {
    return value.split(' ').filter(Boolean).map((part) => part.slice(0, 1).toUpperCase() + part.slice(1)).join(' ');
}

function escapeRegExp(value: string) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function roomOverviewDeviceCount(data: WallDashboardData, room: string) {
    const lights = data.lights.filter((light) => sameArea(light.area, room));
    const covers = (data.covers ?? []).filter((cover) => sameArea(cover.area, room));
    const climates = data.climate.filter((item) => sameArea(item.area, room));
    const fans = (data.fans ?? []).filter((fan) => sameArea(fan.area, room));
    const outlets = roomOutlets(data, room);
    const sensors = roomSensorChips(data, room);
    const excluded = new Set([
        ...lights.map((light) => light.entity_id),
        ...covers.map((cover) => cover.entity_id),
        ...climates.map((item) => item.entity_id),
        ...fans.map((fan) => fan.entity_id),
        ...outlets.map((outlet) => outlet.entity_id),
        ...sensors.map((sensor) => sensor.entity_id),
    ]);
    return lights.length + covers.length + climates.length + fans.length + outlets.length + sensors.length + roomDevices(data, room, excluded).length;
}

function roomMood(data: WallDashboardData, room: string, climates: WallDashboardData['climate']) {
    const classes: string[] = [];
    const chips: Array<{ label: string; tone: string }> = [];
    const hasOpenContact = data.security.openings.some((item) => sameArea(item.area, room) && item.state === 'on');
    const playing = (data.media_players ?? []).some((item) => sameArea(item.area, room) && String(item.state).toLowerCase() === 'playing');
    const vacation = vacationStatus(data);
    const climateMode = climates.map((item) => String(item.state || '').toLowerCase()).find((mode) => mode && mode !== 'off');

    if (climateMode === 'cool') {
        classes.push('mood-cool');
        chips.push({label: 'Klima kühlt', tone: 'cool'});
    } else if (climateMode === 'heat') {
        classes.push('mood-heat');
        chips.push({label: 'Klima heizt', tone: 'heat'});
    } else if (climateMode === 'auto' || climateMode === 'dry') {
        classes.push('mood-auto');
        chips.push({label: climateMode === 'dry' ? 'Entfeuchtet' : 'Klima Auto', tone: 'auto'});
    }

    if (hasOpenContact) {
        classes.push('mood-open');
        chips.push({label: 'Fenster offen', tone: 'open'});
    }

    if (playing) {
        classes.push('mood-music');
        chips.push({label: 'Musik läuft', tone: 'music'});
    }

    if (vacation) {
        classes.push('mood-vacation');
        chips.push({label: 'Urlaub aktiv', tone: 'vacation'});
    }

    return {classes, chips};
}

function roomTemperatureClass(value: number | null) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'temp-neutral';
    if (value < 18) return 'temp-cold';
    if (value < 21) return 'temp-cool';
    if (value < 24) return 'temp-comfort';
    if (value < 26) return 'temp-warm';
    return 'temp-hot';
}

function roomSensorChips(data: WallDashboardData, room: string) {
    const chips = new Map<string, {
        entity_id: string;
        label: string;
        value: string;
        tone: string;
        battery?: BatteryBadge | null
    }>();
    const add = (entity_id: string, label: string, value: string, tone = 'neutral', battery?: BatteryBadge | null) => {
        chips.set(entity_id, {entity_id, label, value, tone, battery});
    };

    for (const sensor of data.temperature_sensors ?? []) {
        if (!sameArea(sensor.area, room)) continue;
        if (sensor.temperature !== null && sensor.temperature !== undefined) {
            add(`${sensor.entity_id}:temperature`, 'Temperatur', `${formatNumber(sensor.temperature)}°C`, 'climate');
        }
        if (sensor.humidity !== null && sensor.humidity !== undefined) {
            add(`${sensor.entity_id}:humidity`, 'Luftfeuchte', `${formatNumber(sensor.humidity)}%`, 'climate');
        }
    }

    for (const sensor of data.sensors ?? []) {
        if (!sameArea(sensor.area, room)) continue;
        const deviceClass = String(sensor.device_class || '').toLowerCase();
        if (deviceClass === 'temperature' || deviceClass === 'humidity' || deviceClass === 'battery' || isPowerSensor(sensor)) continue;
        const label = sensorLabel(sensor);
        add(sensor.entity_id, label, sensorValue(sensor), sensorTone(sensor), batteryForDeviceName(data, room, sensor.name));
    }

    for (const opening of data.security.openings ?? []) {
        if (!sameArea(opening.area, room)) continue;
        add(
            opening.entity_id,
            opening.device_class === 'door' ? 'Tür' : 'Fenster',
            opening.state === 'on' ? 'Offen' : 'Geschlossen',
            opening.state === 'on' ? 'warn' : 'ok',
            batteryForDeviceName(data, room, opening.name),
        );
    }

    return [...chips.values()].sort((left, right) => left.label.localeCompare(right.label));
}

function batteryForDeviceName(data: WallDashboardData, room: string, deviceName: string): BatteryBadge | null {
    const deviceTokens = batteryMatchTokens(deviceName, room);
    if (!deviceTokens.length) return null;
    const candidates = (data.health.batteries ?? []).map((battery) => {
        const sameRoom = sameArea(battery.area, room);
        const batteryTokens = batteryMatchTokens(battery.name, room);
        const overlap = batteryTokens.filter((token) => deviceTokens.includes(token));
        const contains = normalizeBatteryName(battery.name, room).includes(normalizeBatteryName(deviceName, room))
            || normalizeBatteryName(deviceName, room).includes(normalizeBatteryName(battery.name, room));
        return {
            battery,
            score: overlap.length * 10 + (contains ? 8 : 0) + (sameRoom ? 5 : 0),
        };
    }).filter(({score}) => score >= 15);
    const match = candidates.sort((left, right) => right.score - left.score)[0]?.battery;
    if (!match) return null;
    const tone = batteryTone(match);
    return {
        label: `Batterie ${formatBatteryLevel(match)}`,
        tone: tone === 'danger' ? 'critical' : tone,
    };
}

function normalizeBatteryName(value: string, room = '') {
    return normalizeArea(value)
        .replace(normalizeArea(room), '')
        .replace(/\b(battery|batterie|batteriestand|akku|level|status|sensor|power|battery level|batterie level)\b/g, '')
        .replace(/\s+/g, ' ')
        .trim();
}

function batteryMatchTokens(value: string, room: string) {
    return normalizeBatteryName(value, room)
        .split(/\s+/)
        .map((token) => token.trim())
        .filter((token) => token.length >= 3 && !['the', 'and', 'mit', 'von', 'der', 'die', 'das'].includes(token));
}

function sensorLabel(sensor: WallEntity) {
    const deviceClass = String(sensor.device_class || '').toLowerCase();
    if (deviceClass === 'battery') return 'Batterie';
    if (deviceClass === 'motion') return 'Bewegung';
    if (deviceClass === 'illuminance') return 'Helligkeit';
    if (deviceClass === 'power') return 'Leistung';
    if (deviceClass === 'energy') return 'Energie';
    return sensor.name;
}

function sensorValue(sensor: WallEntity) {
    const deviceClass = String(sensor.device_class || '').toLowerCase();
    const state = String(sensor.state || '').toLowerCase();
    if (deviceClass === 'motion') return state === 'on' ? 'Bewegung' : 'Keine Bewegung';
    if (sensor.unit) return `${sensor.state} ${sensor.unit}`;
    return labelState(sensor.state);
}

function sensorTone(sensor: WallEntity) {
    const state = String(sensor.state || '').toLowerCase();
    if (state === 'unavailable' || state === 'unknown') return 'neutral';
    if (state === 'on' || state === 'open') return 'warn';
    return 'ok';
}

function coverStatus(cover: WallCover) {
    const position = cover.position;
    if (cover.state === 'opening' || cover.state === 'closing') return 'Bewegt sich';
    if (position !== null && position !== undefined) {
        if (position <= 5) return 'Geschlossen';
        if (position >= 95) return 'Offen';
        return 'Teilweise';
    }
    if (cover.state === 'open') return 'Offen';
    if (cover.state === 'closed') return 'Geschlossen';
    return labelState(cover.state);
}

function labelClimateMode(mode: string) {
    if (mode === 'off') return 'Aus';
    if (mode === 'heat') return 'Heizen';
    if (mode === 'cool') return 'Kühlen';
    if (mode === 'auto') return 'Auto';
    if (mode === 'dry') return 'Entfeuchten';
    return labelState(mode);
}

function fanStatusLabel(fan: WallFan) {
    if (!deviceActive(fan)) return 'Aus';
    return 'Aktiv';
}

function labelFanPreset(mode: string) {
    const normalized = String(mode || '').toLowerCase();
    const labels: Record<string, string> = {
        normal: 'Normal',
        nature: 'Natur',
        sleep: 'Schlaf',
        favorite: 'Favorit',
        auto: 'Auto',
        silent: 'Leise',
    };
    return labels[normalized] || labelState(mode);
}

function labelFanDirection(direction: string) {
    const normalized = String(direction || '').toLowerCase();
    if (normalized === 'forward') return 'Vorwärts';
    if (normalized === 'reverse') return 'Rückwärts';
    return labelState(direction);
}

function fanSupportsOscillation(fan: WallFan) {
    return fan.oscillating !== null && fan.oscillating !== undefined || fanHasFeature(fan, 2);
}

function fanSupportsDirection(fan: WallFan) {
    return Boolean(fan.direction) || fanHasFeature(fan, 4);
}

function fanHasFeature(fan: WallFan, feature: number) {
    return typeof fan.supported_features === 'number' && (fan.supported_features & feature) === feature;
}

function climateToneClass(mode: string) {
    if (mode === 'heat') return 'heat';
    if (mode === 'cool') return 'cool';
    if (mode === 'auto') return 'auto';
    if (mode === 'dry') return 'dry';
    return 'off';
}
function isRoomTemperatureSensor(item: { name?: string; entity_id?: string }) {
    const text = `${item.name || ''} ${item.entity_id || ''}`.toLowerCase();
    return !/cpu|prozessor|processor|soc|chip|fritz/.test(text);
}
function isRealRoomTemperatureSensorName(name?: string) {
    return !/cpu|prozessor|processor|device temperature|gerätetemperatur|geraetetemperatur|soc|chip|fritz/i.test(String(name || ''));
}

function roomTemperature(data: WallDashboardData, room: string) {
    const values = [
        ...(data.temperature_sensors ?? [])
            .filter((sensor) => sameArea(sensor.area, room))
            .filter((sensor) => isRealRoomTemperatureSensorName(sensor.name))
            .map((sensor) => sensor.temperature),
        ...data.climate
            .filter((item) => sameArea(item.area, room))
            .map((item) => item.current_temperature),
    ].filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value)));
    return avg(values.map(Number));
}

function roomHumidity(data: WallDashboardData, room: string) {
    const values = [
        ...(data.temperature_sensors ?? [])
            .filter((sensor) => sameArea(sensor.area, room))
            .map((sensor) => sensor.humidity)
            .filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value))),
        ...data.climate
            .filter((item) => sameArea(item.area, room))
            .map((item) => item.humidity)
            .filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value))),
    ];
    return avg(values.map(Number));
}

function roomClimateLine(data: WallDashboardData, room: string) {
    const temp = roomTemperature(data, room);
    const humidity = roomHumidity(data, room);
    if (temp === null && humidity === null) return '';
    if (temp !== null && humidity !== null) return `${formatNumber(temp)}°C · ${formatNumber(humidity)}%`;
    if (temp !== null) return `${formatNumber(temp)}°C`;
    return `${formatNumber(humidity)}%`;
}

function deviceActive(device: WallEntity) {
    const state = String(device.state || '').toLowerCase();
    if (state === 'on' || state === 'open' || state === 'opening') return true;
    return false;
}

function isFanEntity(device: WallEntity) {
    return String(device.entity_id || '').startsWith('fan.');
}

function deviceValue(device: WallEntity) {
    const item = device as WallEntity & {
        position?: number | null;
        current_temperature?: number | null;
        target_temperature?: number | null;
        humidity?: number | null;
        temperature?: number | null;
    };
    if (item.current_temperature !== undefined && item.current_temperature !== null) {
        const target = item.target_temperature !== undefined && item.target_temperature !== null
            ? ` · Ziel ${formatNumber(item.target_temperature)}°C`
            : '';
        return `${formatNumber(item.current_temperature)}°C${target}`;
    }
    if (item.temperature !== undefined && item.temperature !== null) {
        return `${formatNumber(item.temperature)}°C`;
    }
    if (item.position !== undefined && item.position !== null) {
        return `${labelState(device.state)} · ${formatNumber(item.position)}%`;
    }
    if (device.unit) return `${device.state} ${device.unit}`;
    return labelState(device.state);
}

function sameArea(left?: string, right?: string) {
    return normalizeArea(left) === normalizeArea(right);
}

function normalizeArea(value?: string) {
    return String(value || '').trim().toLowerCase().replace(/[_-]+/g, ' ');
}

function labelState(state: string) {
    const normalized = String(state || '').toLowerCase();
    const labels: Record<string, string> = {
        on: 'An',
        off: 'Aus',
        open: 'Offen',
        closed: 'Geschlossen',
        opening: 'Öffnet',
        closing: 'Schließt',
        unavailable: 'Nicht verfügbar',
        unknown: 'Unbekannt',
        playing: 'Aktiv',
        idle: 'Bereit',
        paused: 'Pausiert',
    };
    return labels[normalized] || state.replace(/_/g, ' ');
}

function formatNumber(value?: number | null) {
    if (value === null || value === undefined) return '--';
    const number = Number(value);
    if (!Number.isFinite(number)) return '--';
    return `${Math.round(number * 10) / 10}`.replace('.', ',');
}

function temperatureRooms(data: WallDashboardData, selectedFloor: string) {
    const roomToFloor = new Map<string, string>();
    for (const group of data.light_groups) {
        for (const room of floorRooms(data, group.area)) {
            roomToFloor.set(normalizeArea(room.area), group.area);
        }
    }

    const areas = new Set<string>();
    for (const sensor of data.temperature_sensors ?? []) {
        if (sensor.temperature !== null && sensor.temperature !== undefined) areas.add(sensor.area || 'Haus');
    }
    for (const item of data.climate) {
        if (item.current_temperature !== null && item.current_temperature !== undefined) areas.add(item.area || 'Haus');
    }

    return [...areas]
        .map((area) => {
            const floor = roomToFloor.get(normalizeArea(area)) || 'Haus';
            const items = (data.temperature_sensors ?? [])
                .filter((sensor) =>
    sameArea(sensor.area, area) &&
    sensor.temperature !== null &&
    sensor.temperature !== undefined &&
    isRoomTemperatureSensor(sensor)
)
                .sort((left, right) => left.name.localeCompare(right.name));
            const climate = data.climate
                .filter((item) => sameArea(item.area, area) && item.current_temperature !== null && item.current_temperature !== undefined)
                .sort((left, right) => left.name.localeCompare(right.name));
            const temperatures = [
                ...items.map((item) => item.temperature),
                ...climate.map((item) => item.current_temperature),
            ].filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value)));
            const humidityValues = [
                ...items.map((item) => item.humidity),
                ...climate.map((item) => item.humidity),
            ].filter((value): value is number => value !== null && value !== undefined && Number.isFinite(Number(value)));
            return {
                area,
                floor,
                items,
                climate,
                temperature: avg(temperatures.map(Number)),
                humidity: avg(humidityValues.map(Number)),
            };
        })
        .filter((room) => selectedFloor === 'Alle Etagen' || room.floor === selectedFloor)
        .sort((left, right) => left.floor.localeCompare(right.floor) || left.area.localeCompare(right.area));
}

function formatTime(value: string) {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return '--:--';
    return formatClock(date);
}

function formatDateTime(value: string) {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return 'nicht geplant';
    return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()} ${formatClock(date)}`;
}

function formatAgentNextRun(value?: string | null, schedule: string[] = []) {
    if (schedule.length) return schedule.map((item) => item.slice(0, 5)).join(', ');
    return value ? formatDateTime(value) : 'nicht geplant';
}

function formatWellnessNextRun(wellness: Partial<AgentStatus> & { status?: string; error?: string }) {
    const action = nextWellnessAction(wellness);
    if (action === 'book' && wellness.booking_time) return wellness.booking_time.slice(0, 5);
    if (action === 'prepare' && wellness.prepare_time) return wellness.prepare_time.slice(0, 5);
    if (action === 'health_sync' && wellness.health_sync_time) return wellness.health_sync_time.slice(0, 5);
    return wellness.next_scheduled_run ? formatDateTime(wellness.next_scheduled_run) : 'nicht geplant';
}

function nextWellnessAction(wellness: Partial<AgentStatus>) {
    if (wellness.next_scheduled_action) return wellness.next_scheduled_action;
    if (!wellness.next_scheduled_run) return null;
    if (wellness.health_sync_enabled !== false && wellness.prepare_enabled === false && wellness.booking_enabled === false) return 'health_sync';
    if (wellness.prepare_enabled !== false && wellness.booking_enabled === false) return 'prepare';
    if (wellness.booking_enabled !== false && wellness.prepare_enabled === false) return 'book';
    const planned = new Date(wellness.next_scheduled_run);
    if (!Number.isFinite(planned.getTime())) return null;
    const plannedTime = `${pad(planned.getHours())}:${pad(planned.getMinutes())}`;
    if (wellness.prepare_time?.slice(0, 5) === plannedTime) return 'prepare';
    if (wellness.booking_time?.slice(0, 5) === plannedTime) return 'book';
    if (wellness.health_sync_time?.slice(0, 5) === plannedTime) return 'health_sync';
    return null;
}

function clampPercent(value: number) {
    if (!Number.isFinite(value)) return 0;
    return Math.max(0, Math.min(100, Math.round(value)));
}

function formatClock(date: Date) {
    return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatWallDate(date: Date) {
    const weekdays = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'];
    const months = ['Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
    return `${weekdays[date.getDay()]}, ${pad(date.getDate())}. ${months[date.getMonth()]}`;
}

function pad(value: number) {
    return String(value).padStart(2, '0');
}

function patchWallLights(
    current: WallDashboardData | null,
    entityIds: string[],
    patch: Partial<Pick<WallLight, 'on' | 'brightness_pct'>>,
): WallDashboardData | null {
    if (!current) return current;
    const ids = new Set(entityIds);
    const patchLight = (light: WallLight): WallLight => {
        if (!ids.has(light.entity_id)) return light;
        const next = {...light, ...patch};
        next.state = next.on ? 'on' : 'off';
        return next;
    };
    const countOn = (items: WallLight[]) => items.filter((item) => item.on).length;
    const lights = current.lights.map(patchLight);
    const light_groups = current.light_groups.map((group) => {
        const rooms = (group.rooms ?? []).map((room) => {
            const items = room.items.map(patchLight);
            return {...room, items, on: countOn(items), total: items.length};
        });
        const items = group.items.map(patchLight);
        return {
            ...group,
            items,
            rooms,
            on: rooms.length ? rooms.reduce((sum, room) => sum + room.on, 0) : countOn(items),
            total: rooms.length ? rooms.reduce((sum, room) => sum + room.total, 0) : items.length,
        };
    });
    return {...current, lights, light_groups};
}

function patchWallCover(
    current: WallDashboardData | null,
    entityId: string,
    patch: Partial<WallCover>,
): WallDashboardData | null {
    if (!current) return current;
    return {
        ...current,
        covers: (current.covers ?? []).map((cover) => (
            cover.entity_id === entityId ? {...cover, ...patch} : cover
        )),
    };
}

function patchWallClimate(
    current: WallDashboardData | null,
    entityId: string,
    patch: Record<string, unknown>,
): WallDashboardData | null {
    if (!current) return current;
    return {
        ...current,
        climate: current.climate.map((item) => {
            if (item.entity_id !== entityId) return item;
            return {
                ...item,
                state: typeof patch.hvac_mode === 'string' ? patch.hvac_mode : item.state,
                target_temperature: typeof patch.temperature === 'number' ? patch.temperature : item.target_temperature,
            };
        }),
    };
}

function patchWallFan(
    current: WallDashboardData | null,
    entityId: string,
    patch: Partial<WallFan>,
): WallDashboardData | null {
    if (!current) return current;
    return {
        ...current,
        fans: (current.fans ?? []).map((item) => (
            item.entity_id === entityId ? {...item, ...patch} : item
        )),
    };
}

function patchWallSwitch(
    current: WallDashboardData | null,
    entityId: string,
    patch: Partial<WallEntity>,
): WallDashboardData | null {
    if (!current) return current;
    return {
        ...current,
        switches: (current.switches ?? []).map((item) => (
            item.entity_id === entityId ? {...item, ...patch} : item
        )),
    };
}
