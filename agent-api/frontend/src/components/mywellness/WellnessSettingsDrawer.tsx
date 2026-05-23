import { X } from 'lucide-react';
import type { AgentStatus, MyWellnessSettingsPayload } from '../../api/client';
import { WellnessSettingsPanel } from './WellnessSettingsPanel';

interface Props {
  open: boolean;
  status: AgentStatus | null;
  loading: boolean;
  onClose: () => void;
  onSave: (payload: MyWellnessSettingsPayload) => void;
}

export function WellnessSettingsDrawer({ open, status, loading, onClose, onSave }: Props) {
  if (!open) return null;
  return (
    <div className="wellness-drawer-layer">
      <button className="wellness-drawer-backdrop" type="button" onClick={onClose} aria-label="Einstellungen schließen" />
      <aside className="wellness-settings-drawer" role="dialog" aria-modal="true" aria-label="MyWellness Einstellungen">
        <header>
          <div>
            <span className="eyebrow">MyWellness</span>
            <h2>Einstellungen</h2>
            <p>Automationen und Kursauswahl feinjustieren.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Schließen"><X size={18} /></button>
        </header>
        <WellnessSettingsPanel status={status} loading={loading} onSave={onSave} />
        <p className="wellness-ha-note">Home Assistant läuft aktuell noch parallel.</p>
      </aside>
    </div>
  );
}
