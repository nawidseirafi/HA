import {request, apiUrl} from '@shared/api/client';
export type MusicSettings = {lights: string[]; player: string; profile: 'ambient' | 'dynamic' | 'party'; intensity: number};
export type MusicStatus = {status: string; is_running: boolean; session: string; settings: MusicSettings; active_lights: string[]; released: string[]; error?: string; reason?: string; diagnostic?: string; telemetry?: {audio_seq: number; commands: number; level: number | null; bass: number | null; last_command: {entity_id: string; brightness: number; hs_color?: number[]} | null}};
export type MusicDevice = {entity_id: string; name: string; state: string; area: string; floor: string; selectable: boolean};
export type MusicInventory = {lights: MusicDevice[]; players: MusicDevice[]};
export const defaults: MusicSettings = {lights: [], player: '', profile: 'ambient', intensity: .5};
export const musicStatus = () => request<MusicStatus>('/api/music/status');
export const musicInventory = () => request<MusicInventory>('/api/music/inventory');
export async function musicControl(action: string, payload = {}) {
    const result = await request<{ok: boolean; message: string; data: MusicStatus}>(`/api/orchestrator/agents/music/control/${action}`, {method: 'POST', body: JSON.stringify(payload)});
    if (!result.ok) throw new Error(result.message);
    return result.data;
}
export const musicTicket = () => request<{ticket: string}>('/api/music/ticket', {method: 'POST'});
export function socketUrl() {
    const url = new URL(apiUrl('/api/music/audio'), window.location.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.toString();
}
