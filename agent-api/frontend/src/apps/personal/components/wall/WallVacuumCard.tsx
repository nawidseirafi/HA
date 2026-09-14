import {useEffect, useRef, useState} from 'react';
import {BatteryCharging, BatteryFull, Bot, ChevronDown, Clock3, Home, Loader2, Map, MapPin, Pause, Play, Radar, RefreshCw, Square, SquareDashed, TriangleAlert, Wind} from 'lucide-react';
import {api, type WallVacuum} from '@shared/api/client';
import './wall-vacuum.css';

const labels: Record<string, string> = {
  docked: 'In der Station', charging: 'Lädt', charging_complete: 'Voll geladen', cleaning: 'Reinigt',
  returning: 'Fährt zur Station', returning_home: 'Fährt zur Station', idle: 'Bereit', paused: 'Pausiert',
  error: 'Braucht Aufmerksamkeit', unavailable: 'Nicht erreichbar', unknown: 'Status unbekannt',
  washing_the_mop: 'Wäscht den Mopp', emptying_the_bin: 'Leert den Staubbehälter',
  quiet: 'Leise', balanced: 'Standard', turbo: 'Turbo', max: 'Max', max_plus: 'Max+', off: 'Aus',
  low: 'Niedrig', medium: 'Mittel', high: 'Hoch', custom: 'Individuell', custom_water_flow: 'Individuell',
  standard: 'Standard', deep: 'Intensiv', deep_plus: 'Intensiv+', fast: 'Schnell',
  vacuum: 'Saugen', vac_and_mop: 'Saugen & Wischen', mop: 'Wischen',
};
const label = (value: string) => labels[value] ?? value.replace(/_/g, ' ');
const usable = (value?: string) => !!value && !['unknown', 'unavailable', 'none'].includes(value);
function metric(value?: string, unit?: string | null) {
  if (!usable(value)) return '—';
  const number = Number(value);
  return Number.isFinite(number) ? `${new Intl.NumberFormat('de-DE', {maximumFractionDigits: 1}).format(number)}${unit ? ` ${unit}` : ''}` : value;
}
function dateLabel(value?: string) {
  if (!value || Number.isNaN(new Date(value).getTime())) return 'Zeitpunkt unbekannt';
  return new Intl.DateTimeFormat('de-DE', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}).format(new Date(value));
}

function FittedMapImage({src, alt, onError}: {src: string; alt: string; onError: () => void}) {
  const frame = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({width:0, height:0});
  const [image, setImage] = useState<{width:number; height:number; x:number; y:number; cropWidth:number; cropHeight:number} | null>(null);
  useEffect(() => {
    const observer = new ResizeObserver(entries => {
      const {width, height} = entries[0].contentRect;
      setSize({width, height});
    });
    if (frame.current) observer.observe(frame.current);
    return () => observer.disconnect();
  }, []);
  const scale = image ? Math.min(size.width/image.cropWidth, size.height/image.cropHeight) : 1;
  return <div className="wall-vacuum-map-image" ref={frame}><img src={src} alt={alt} onError={onError}
    style={image ? {position:'absolute', maxWidth:'none', width:image.width*scale, height:image.height*scale,
      left:(size.width-image.cropWidth*scale)/2-image.x*scale, top:(size.height-image.cropHeight*scale)/2-image.y*scale} : undefined}
    onLoad={event => {
      const img = event.currentTarget;
      // Fit the real floor plan, ignoring the transparent margin in Roborock's map image.
      const ratio = Math.min(1, 1024/Math.max(img.naturalWidth,img.naturalHeight));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1,Math.round(img.naturalWidth*ratio)); canvas.height = Math.max(1,Math.round(img.naturalHeight*ratio));
      const context = canvas.getContext('2d');
      if (!context) return;
      context.drawImage(img,0,0,canvas.width,canvas.height);
      const pixels = context.getImageData(0,0,canvas.width,canvas.height).data;
      let left=canvas.width, top=canvas.height, right=0, bottom=0;
      for (let y=0;y<canvas.height;y++) for (let x=0;x<canvas.width;x++) {
        if (pixels[(y*canvas.width+x)*4+3]>16) {left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x);bottom=Math.max(bottom,y);}
      }
      if (right<left || bottom<top) {left=0;top=0;right=canvas.width-1;bottom=canvas.height-1;}
      const padding=Math.max(right-left,bottom-top)*.06;
      setImage({width:img.naturalWidth,height:img.naturalHeight,x:(left-padding)/ratio,y:(top-padding)/ratio,
        cropWidth:(right-left+1+2*padding)/ratio,cropHeight:(bottom-top+1+2*padding)/ratio});
    }}/></div>;
}

export function WallVacuumCard({vacuum, onUpdated}: {vacuum: WallVacuum; onUpdated?: () => void}) {
  const activeMap = vacuum.selects.find(s => /ausgewahlte_karte|selected_map/.test(s.entity_id))?.state.trim();
  const [mapId, setMapId] = useState(() => vacuum.maps.find(m => m.name.trim() === activeMap)?.entity_id ?? vacuum.maps[0]?.entity_id ?? '');
  const [mapUrl, setMapUrl] = useState('');
  const [mapError, setMapError] = useState('');
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [routine, setRoutine] = useState('');
  const selectedMap = vacuum.maps.find(m => m.entity_id === mapId);
  const offline = ['unknown', 'unavailable'].includes(vacuum.state);
  const cleaning = vacuum.state === 'cleaning';
  const configurable = ['docked', 'idle', 'paused'].includes(vacuum.state);
  const rawStatus = usable(vacuum.metrics.status?.state) && !offline && vacuum.state !== 'error' ? vacuum.metrics.status.state : vacuum.state;
  const charging = vacuum.metrics.charging?.state === 'on';
  const progress = Number(vacuum.metrics.progress?.state);
  const fault = vacuum.metrics.error?.state;
  const waterLow = vacuum.metrics.water_low?.state === 'on';

  useEffect(() => {
    if (!vacuum.maps.some(m => m.entity_id === mapId)) setMapId(vacuum.maps[0]?.entity_id ?? '');
  }, [vacuum.maps, mapId]);
  useEffect(() => {
    const controller = new AbortController();
    let url = '';
    setMapUrl(''); setMapError('');
    if (mapId) api.vacuumMap(vacuum.entity_id, mapId, controller.signal).then(blob => {
      if (controller.signal.aborted) return;
      url = URL.createObjectURL(blob); setMapUrl(url);
    }).catch(err => {if (!controller.signal.aborted) setMapError(err.message);});
    return () => {controller.abort(); if (url) URL.revokeObjectURL(url);};
  }, [vacuum.entity_id, mapId, selectedMap?.state, revision]);

  async function run(action: string, target?: string, option?: string) {
    if (busy || offline) return;
    setBusy(target ?? action); setError(''); setNotice('');
    try {
      const result = await api.vacuumCommand(vacuum.entity_id, action, target, option);
      if (!result.ok) throw new Error('Auftrag wurde nicht angenommen.');
      setNotice('Auftrag übermittelt'); onUpdated?.();
    } catch (err) {setError(err instanceof Error ? err.message : 'Auftrag fehlgeschlagen.');}
    finally {setBusy('');}
  }
  const controls = [
    {action:'start', name: vacuum.state === 'paused' ? 'Fortsetzen' : 'Reinigung starten', icon:Play, disabled:!configurable},
    {action:'pause', name:'Pausieren', icon:Pause, disabled:!cleaning},
    {action:'return_to_base', name:'Zur Station', icon:Home, disabled:['docked','returning'].includes(vacuum.state)},
    {action:'stop', name:'Stoppen', icon:Square, disabled:!['cleaning','paused','returning'].includes(vacuum.state)},
    {action:'locate', name:'Roboter finden', icon:Radar, disabled:false},
  ];

  return <article className={`wall-vacuum ${cleaning ? 'is-cleaning' : ''}`} aria-label={`Saugroboter ${vacuum.name}`}>
    <header className="wall-vacuum-header">
      <span className="wall-vacuum-emblem"><Bot size={26}/></span>
      <div className="wall-vacuum-title"><small>Saugroboter · {vacuum.area || 'Zuhause'}</small><h3>{vacuum.manufacturer || vacuum.name}</h3></div>
      <span className={`wall-vacuum-state ${offline ? 'is-offline' : ''}`}><i/>{label(rawStatus)}</span>
    </header>
    <div className="wall-vacuum-content">
      <div className="wall-vacuum-map-column">
        <div className="wall-vacuum-map-tabs" role="tablist" aria-label="Roboterkarten">
          {vacuum.maps.map(map => <button type="button" key={map.entity_id} role="tab" aria-selected={mapId === map.entity_id} onClick={()=>setMapId(map.entity_id)}>{map.name}</button>)}
        </div>
        <div className="wall-vacuum-map">
          {mapUrl ? <FittedMapImage key={mapUrl} src={mapUrl} alt={`Reinigungskarte ${selectedMap?.name || ''}`} onError={()=>{setMapError('Karte konnte nicht angezeigt werden.'); setMapUrl('');}}/> :
            <div className="wall-vacuum-map-empty">{mapId && !mapError ? <Loader2 className="vacuum-spin" size={24}/> : <Map size={32}/>}<span>{mapError || (mapId ? 'Karte wird geladen' : 'Keine Karte verfügbar')}</span></div>}
          {mapId && <button type="button" className="wall-vacuum-map-refresh" title="Karte aktualisieren" aria-label="Karte aktualisieren" onClick={()=>setRevision(n=>n+1)}><RefreshCw size={17}/></button>}
        </div>
        <small className="wall-vacuum-map-date">{selectedMap ? `Kartenstand ${dateLabel(selectedMap.state)}` : vacuum.metadata_available ? 'Keine Bild-Entity vorhanden' : 'Gerätezuordnung nicht verfügbar'}</small>
      </div>
      <div className="wall-vacuum-overview">
        <div className="wall-vacuum-battery">{charging ? <BatteryCharging size={23}/> : <BatteryFull size={23}/>}<strong>{vacuum.battery_level === null ? '—' : `${vacuum.battery_level}%`}</strong><span>{charging ? 'Lädt' : 'Akku'}</span></div>
        <div className="wall-vacuum-location"><MapPin size={16}/>{usable(vacuum.metrics.room?.state) ? vacuum.metrics.room.state : activeMap || vacuum.area || 'Raum unbekannt'}</div>
        <div className="wall-vacuum-session"><small>{cleaning ? 'Aktuelle Reinigung' : 'Letzte Reinigungswerte'}</small>
          <div className="wall-vacuum-metrics"><span><SquareDashed size={18}/><strong>{metric(vacuum.metrics.area?.state, vacuum.metrics.area?.unit)}</strong></span><span><Clock3 size={18}/><strong>{metric(vacuum.metrics.duration?.state, vacuum.metrics.duration?.unit)}</strong></span></div>
          {!cleaning && <small>{dateLabel(vacuum.metrics.last_end?.state)}</small>}
          {cleaning && Number.isFinite(progress) && <div className="wall-vacuum-progress"><progress value={Math.max(0, Math.min(100, progress))} max={100}/><span>{Math.round(Math.max(0,Math.min(100,progress)))}%</span></div>}
        </div>
        <div className="wall-vacuum-controls">{controls.filter(c=>vacuum.actions.includes(c.action)).map(({action,name,icon:Icon,disabled}) =>
          <button type="button" key={action} className={action==='start'?'primary':''} title={name} aria-label={name} disabled={!!busy || offline || disabled} onClick={()=>run(action)}>{busy===action ? <Loader2 size={20} className="vacuum-spin"/> : <Icon size={20}/>}</button>)}</div>
        <div className="wall-vacuum-feedback" aria-live="polite">{error ? <span role="alert">{error}</span> : notice}</div>
      </div>
    </div>
    {(offline || (usable(fault) && fault !== '0') || waterLow) && <div className="wall-vacuum-alert" role="status"><TriangleAlert size={18}/>{offline ? 'Roboter nicht erreichbar' : waterLow ? 'Wasser nachfüllen' : `Roboter meldet: ${label(fault!)}`}</div>}
    <details className="wall-vacuum-details"><summary><Wind size={17}/> Reinigung & Pflege <ChevronDown size={17}/></summary>
      <div className="wall-vacuum-settings">
        {vacuum.actions.includes('set_fan_speed') && <label>Saugstärke<select aria-label="Saugstärke" value={vacuum.fan_speed ?? ''} disabled={!!busy || offline} onChange={e=>run('set_fan_speed',undefined,e.target.value)}>{vacuum.fan_speed_list.map(option=><option key={option} value={option}>{label(option)}</option>)}</select></label>}
        {vacuum.selects.map(control=><label key={control.entity_id}>{control.name}<select aria-label={control.name} value={control.state} disabled={!!busy || offline || !configurable || control.state==='unavailable'} onChange={e=>run('select_option',control.entity_id,e.target.value)}>{!control.options.includes(control.state) && <option value={control.state} disabled>{label(control.state)}</option>}{control.options.map(option=><option key={option} value={option}>{label(option)}</option>)}</select></label>)}
        {vacuum.routines.length>0 && <div className="wall-vacuum-routine"><label>Programm<select aria-label="Reinigungsprogramm" value={routine} disabled={!!busy || offline || !configurable} onChange={e=>setRoutine(e.target.value)}><option value="">Programm auswählen</option>{vacuum.routines.map(r=><option key={r.entity_id} value={r.entity_id}>{r.name}</option>)}</select></label><button type="button" title="Programm starten" aria-label="Programm starten" disabled={!routine || !!busy || offline || !configurable} onClick={()=>run('press',routine)}><Play size={20}/></button></div>}
        {vacuum.switches.map(control=><label className="wall-vacuum-toggle" key={control.entity_id}>{control.name}<input type="checkbox" role="switch" aria-label={control.name} checked={control.state==='on'} disabled={!!busy || offline || !['on','off'].includes(control.state)} onChange={e=>run(e.target.checked?'turn_on':'turn_off',control.entity_id)}/></label>)}
      </div>
      {vacuum.maintenance.length>0 && <dl className="wall-vacuum-maintenance">{vacuum.maintenance.map(m=><div key={m.entity_id}><dt>{m.name}</dt><dd>{metric(m.state,m.unit)}</dd></div>)}</dl>}
      <small className="wall-vacuum-device-name">{vacuum.name} · {vacuum.model || vacuum.entity_id}</small>
    </details>
  </article>;
}
