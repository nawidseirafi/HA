import {useEffect, useRef, useState} from 'react';
import {AudioLines, ChevronDown, Lightbulb, Mic, Play, Square, Sparkles, Waves, Zap} from 'lucide-react';
import {defaults, musicControl, musicInventory, MusicInventory, MusicSettings} from '../../features/music/musicClient';
import {useMusicSession} from '../../features/music/useMusicSession';
import './wall-music.css';

type Session = ReturnType<typeof useMusicSession>;
const labels: Record<string, string> = {offline: 'Dienst nicht erreichbar', idle: 'Bereit', preparing: 'Warte auf Audiodaten', running: 'Musiklicht aktiv', stopping: 'Lichtzustände werden wiederhergestellt', recovery_pending: 'Wiederherstellung prüfen'};
function Spectrum({music}: {music: Session}) {
    const bars = useRef<HTMLDivElement>(null);
    useEffect(() => {
        const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
        const timer = window.setInterval(() => {
            const values = music.microphone ? music.spectrum.current : [];
            Array.from(bars.current?.children || []).forEach((bar, i) => {
                (bar as HTMLElement).style.transform = 'scaleY(' + Math.max(.025, values[i] || 0) + ')';
            });
        }, reduced.matches ? 500 : 50);
        return () => window.clearInterval(timer);
    }, [music.microphone, music.spectrum]);
    return <div className="studio-spectrum" aria-label={music.microphone ? 'Frequenzanzeige des lokalen Mikrofons' : 'Frequenzanzeige inaktiv'}>
        <div className="studio-bars" ref={bars} aria-hidden="true">{Array.from({length: 48}, (_, i) => <i key={i} style={{transform: 'scaleY(.025)'}}/>)}</div>
        <div className="studio-frequency"><span>40 Hz · BASS</span><span>MITTEN</span><span>12 kHz · HÖHEN</span></div>
    </div>;
}
export function WallMusicSection({music}: {music: Session}) {
    const [inventory, setInventory] = useState<MusicInventory>({lights: [], players: []});
    const [settings, setSettings] = useState<MusicSettings>(defaults);
    const [dirty, setDirty] = useState(false);
    const [saving, setSaving] = useState(false);
    const [filter, setFilter] = useState('Alle Etagen');
    const [loaded, setLoaded] = useState(false);
    useEffect(() => {
        let active = true;
        musicInventory().then(data => { if (active) { setInventory(data); setLoaded(true); } }).catch(e => music.setError(String(e)));
        return () => { active = false; };
    }, []);
    useEffect(() => {
        if (!dirty && music.status?.settings?.lights) setSettings(music.status.settings);
    }, [music.status, dirty]);
    const locked = !!music.status?.is_running || saving || music.busy || music.status?.status === 'recovery_pending';
    const change = (patch: Partial<MusicSettings>) => { setSettings(s => ({...s, ...patch})); setDirty(true); };
    const visible = inventory.lights.filter(l => filter === 'Alle Etagen' || l.floor === filter);
    const rooms = [...new Set(visible.map(l => `${l.floor} · ${l.area}`))];
    const save = async () => {
        setSaving(true); music.setError('');
        try { await musicControl('run', {action: 'configure', ...settings}); setDirty(false); await music.refresh(); }
        catch (e) { music.setError(String(e)); }
        finally { setSaving(false); }
    };
    return <section className="wall-music" aria-label="Musiklicht">
        <div className="wall-music-summary">
            <div><span className="studio-eyebrow"><AudioLines size={16}/> STEVE MUSIC LAB</span><h2>DJ Studio<span>.</span></h2><p>Dein Sound. Dein Licht. Dein Moment.</p></div>
            <span className={'studio-status' + (music.microphone ? ' is-live' : '')} role="status"><i/>{labels[music.status?.status || 'offline'] || music.status?.status}</span>
        </div>
        <div className="studio-stage">
            <div className="studio-stage-top"><span><Mic size={14}/>{music.microphone ? 'MIKROFON LIVE' : 'AUDIO STANDBY'}</span><span>{settings.profile.toUpperCase()} / {Math.round(settings.intensity * 100)} %</span></div>
            <Spectrum music={music}/>
            <div className="studio-transport">
                <div><strong>{music.microphone ? 'Der Raum wird zur Bühne.' : 'Bereit für deinen nächsten Track?'}</strong><span>{music.microphone ? 'Die Lichtshow folgt der Musik im Raum.' : 'Player und Lampen wählen. Speichern. Show starten.'}</span></div>
                <div className="music-buttons"><button className="music-start" onClick={() => void music.start()} disabled={locked || dirty || !settings.lights.length || !settings.player || music.status?.status !== 'idle'}><Play size={18}/>{music.busy ? 'Verbinden …' : 'Show starten'}</button><button className="music-stop" onClick={() => void music.stop()} disabled={!music.status?.is_running && !music.busy && !music.microphone}><Square size={16}/>Stoppen</button></div>
            </div>
        </div>
        {(music.error || music.status?.error) && <p role="alert" className="wall-error">{music.error || music.status?.error}</p>}
        {music.status?.telemetry && <details className="studio-room-details"><summary>Signal & Lichtausgabe <ChevronDown size={16}/></summary><p>Audiosequenz: {music.status.telemetry.audio_seq} · Pegel: {music.status.telemetry.level === null ? '–' : Math.round(music.status.telemetry.level * 100) + ' %'} · Bass: {music.status.telemetry.bass === null ? '–' : Math.round(music.status.telemetry.bass * 100) + ' %'}</p><p>Von HA angenommene Lichtbefehle: {music.status.telemetry.commands} · Aktive Lampen: {music.status.active_lights.length}</p>{music.status.telemetry.last_command && <p>Letzter Befehl: {music.status.telemetry.last_command.entity_id} · Helligkeit: {music.status.telemetry.last_command.brightness}/255 · Farbton: {music.status.telemetry.last_command.hs_color?.[0] ?? '–'}°</p>}</details>}
        {music.status?.diagnostic && <p role="alert">Diagnose: {music.status.diagnostic}</p>}
        {music.status?.reason && <p>Letzter Stopp: {({manual: 'Manuell', audio_timeout: 'Keine Audiodaten', audio_disconnected: 'Audioverbindung beendet', player_paused: 'Wiedergabe pausiert', player_unavailable: 'Player nicht erreichbar', ha_error: 'Fehler bei der Lichtsteuerung', manual_override: 'Manuell übernommen'} as Record<string, string>)[music.status.reason] || music.status.reason}</p>}
        {music.status?.status === 'recovery_pending' && <button onClick={() => void musicControl('run', {action: 'recover'}).then(music.refresh).catch(e => music.setError(String(e)))}>Wiederherstellung erneut prüfen</button>}
        <fieldset disabled={locked} className="studio-mixer">
            <legend><AudioLines size={18}/> Sound & Stimmung</legend>
            <label>Sonos / Media-Player<select value={settings.player} onChange={e => change({player: e.target.value})}><option value="">Player auswählen</option>{inventory.players.map(p => <option key={p.entity_id} value={p.entity_id}>{p.name} ({p.state})</option>)}</select></label>
            <div className="studio-profiles" role="group" aria-label="Musikprofil">{([
                {id: 'ambient', name: 'Ambient', description: 'Weich & atmosphärisch', Icon: Waves},
                {id: 'dynamic', name: 'Dynamic', description: 'Spürbar im Rhythmus', Icon: Sparkles},
                {id: 'party', name: 'Party', description: 'Farbe & Energie', Icon: Zap},
            ] as const).map(({id, name, description, Icon}) => <button key={id} className={'studio-profile profile-' + id} aria-pressed={settings.profile === id} onClick={() => change({profile: id})}><Icon size={23}/><strong>{name}</strong><span>{description}</span></button>)}</div>
            <label>Intensität · {Math.round(settings.intensity * 100)} %<input type="range" min="0" max="1" step="0.05" value={settings.intensity} onChange={e => change({intensity: Number(e.target.value)})}/></label>
        </fieldset>
        <fieldset disabled={locked} className="studio-lightstage">
            <legend><Lightbulb size={18}/> Lichtbühne <span className="studio-count">{settings.lights.length}</span></legend>
            <div className="studio-lights-toolbar">
                <label>Etage<select value={filter} onChange={e => setFilter(e.target.value)}><option>Alle Etagen</option>{[...new Set(inventory.lights.map(l => l.floor))].map(f => <option key={f}>{f}</option>)}</select></label>
                <div><strong>{settings.lights.length} Lampen ausgewählt</strong><button className="studio-clear" disabled={!settings.lights.length} onClick={() => change({lights: []})}>Auswahl leeren</button></div>
            </div>
            <p className="studio-selection-hint">Wähle einen Raum oder öffne ihn für einzelne Lampen.</p>
            {!loaded && <p>Lampen werden geladen …</p>}
            {loaded && !visible.length && <p>Keine Lampen gefunden. Home-Assistant-Verbindung prüfen.</p>}
            <div className="studio-room-grid">{rooms.map(room => {
                const lights = visible.filter(l => `${l.floor} · ${l.area}` === room);
                const eligible = lights.filter(l => l.selectable);
                const selected = lights.filter(l => settings.lights.includes(l.entity_id)).length;
                const allSelected = eligible.length > 0 && eligible.every(l => settings.lights.includes(l.entity_id));
                return <div key={room} className={'studio-room-card' + (selected ? ' has-selection' : '')}>
                    <div className="studio-room-heading"><span className="studio-room-icon"><Lightbulb size={20}/></span><div><strong>{lights[0].area || 'Ohne Raum'}</strong><span>{lights[0].floor || 'Ohne Etage'} · {selected} von {lights.length} ausgewählt</span></div></div>
                    <button className="studio-room-select" aria-pressed={allSelected} disabled={!eligible.length && !selected} onClick={() => change({lights: allSelected || !eligible.length ? settings.lights.filter(id => !lights.some(l => l.entity_id === id)) : [...new Set([...settings.lights, ...eligible.map(l => l.entity_id)])]})}>{allSelected ? 'Raum abwählen' : !eligible.length ? (selected ? 'Auswahl entfernen' : 'Keine verfügbaren Lampen') : 'Raum auswählen'}</button>
                    <details className="studio-room-details"><summary>Einzelne Lampen <ChevronDown size={16}/></summary><div className="studio-room-lamps">{lights.map(l => {
                        const selected = settings.lights.includes(l.entity_id);
                        return <button type="button" className="music-light" key={l.entity_id} disabled={!l.selectable && !selected} aria-pressed={selected} aria-label={l.name + ' für die Lichtshow auswählen'} onClick={() => change({lights: selected ? settings.lights.filter(id => id !== l.entity_id) : [...settings.lights, l.entity_id]})}><span>{l.name}{!l.selectable && <small>Nicht verfügbar, nicht dimmbar oder Lichtgruppe</small>}</span><i className={'wall-switch' + (selected ? ' on' : '')} aria-hidden="true"/></button>;
                    })}</div></details>
                </div>;
            })}</div>
            {settings.lights.filter(id => !inventory.lights.some(l => l.entity_id === id)).map(id => <button type="button" className="music-light" key={id} aria-pressed={true} aria-label={id + ' aus der Lichtshow entfernen'} onClick={() => change({lights: settings.lights.filter(l => l !== id)})}><span>{id}<small>Nicht mehr im Bestand</small></span><i className="wall-switch on" aria-hidden="true"/></button>)}
        </fieldset>
        <div className="music-buttons">
            <button onClick={() => void save()} disabled={locked || !dirty || settings.lights.length > 50}>Auswahl speichern</button>

        </div>
        {dirty && <p>Änderungen vor dem Start speichern.</p>}
        {settings.lights.length > 50 && <p role="alert">V1 unterstützt maximal 50 ausgewählte Lampen.</p>}
        {!!music.status?.released.length && <p>{music.status.released.length} Lampe(n) wurden manuell übernommen und bleiben unverändert.</p>}
        <p className="studio-note">Das Mikrofon startet nur nach deinem Tippen auf „Show starten“. Keine Aufnahme, nur lokale Analyse; übertragen werden ausschließlich Rhythmus- und Lautstärkewerte.</p>
        <p className="studio-note">Manuelles Schalten oder Dimmen hat Vorrang. Sonos-Pause, gesperrtes iPad oder Verbindungsverlust beendet die Show. Bei vielen Lampen werden die Übergänge langsamer.</p>
    </section>;
}
