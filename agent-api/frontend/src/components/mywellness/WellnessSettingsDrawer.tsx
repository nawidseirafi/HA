import { X } from 'lucide-react';
import type { AgentStatus, MyWellnessSettingsPayload } from '../../api/client';
import { WellnessSettingsPanel } from './WellnessSettingsPanel';

interface Props {
  open: boolean;
  status: AgentStatus | null;
  loading: boolean;
  mode?: 'booking' | 'health' | 'all';
  onClose: () => void;
  onSave: (payload: MyWellnessSettingsPayload) => void;
}

export function WellnessSettingsDrawer({ open, status, loading, mode = 'all', onClose, onSave }: Props) {
  if (!open) return null;
  const copy = mode === 'health'
    ? 'Health, Withings und Home Assistant konfigurieren.'
    : mode === 'booking'
      ? 'Automationen und Kursauswahl feinjustieren.'
      : 'Automationen, Kursauswahl und Health-Daten konfigurieren.';
  return (
    <div className="wellness-drawer-layer">
      <button className="wellness-drawer-backdrop" type="button" onClick={onClose} aria-label="Einstellungen schließen" />
      <aside className="wellness-settings-drawer" role="dialog" aria-modal="true" aria-label="MyWellness Einstellungen">
        <header>
          <div>
            <span className="eyebrow">MyWellness</span>
            <h2>Einstellungen</h2>
            <p>{copy}</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Schließen"><X size={18} /></button>
        </header>
        <WellnessSettingsPanel status={status} loading={loading} mode={mode} onSave={onSave} />
        {mode !== 'booking' && <p className="wellness-ha-note">Health-Daten werden nur aus Home Assistant gelesen und lokal in SQLite gespeichert.</p>}
      </aside>
    </div>
  );
}
