import { useMemo, useState } from 'react';
import { SelectableOptionCard } from './Cards';
import { setupOptions } from '../data/mockSeniorCareData';

const steps = [
  { title: 'Willkommen', text: 'SeniorCare ist ein beruhigendes Fenster in den Alltag eines Menschen, der Ihnen wichtig ist.' },
  { title: 'Wen begleiten wir?', text: 'Name, Alter und optional ein Foto koennen spaeter ergaenzt werden.', fields: ['Name', 'Alter', 'Foto optional'] },
  { title: 'Das Zuhause', text: 'Welche Raeume gehoeren zum Alltag?', options: ['Wohnzimmer', 'Kueche', 'Bad', 'Schlafzimmer'] },
  { title: 'Sensoren verbinden', text: 'Waehlen Sie aus, welche Alltagssignale SeniorCare behutsam beruecksichtigen darf.', options: setupOptions.sensors },
  { title: 'Welche Hinweise moechten Sie erhalten?', text: 'Waehlen Sie nur, was wirklich hilfreich ist.', options: setupOptions.hints },
  { title: 'Wer soll informiert werden?', text: 'Eine Vertrauensperson reicht fuer den Anfang.', fields: ['Name', 'Beziehung', 'E-Mail-Adresse'] },
  { title: 'Fertig', text: 'SeniorCare ist bereit. Sie sehen ab jetzt nur die Hinweise, die wirklich wichtig sind.' },
];

export function SetupWizard({ onFinish }: { onFinish: () => void }) {
  const [stepIndex, setStepIndex] = useState(0);
  const [selected, setSelected] = useState<Record<number, string>>({});
  const step = steps[stepIndex];
  const progress = useMemo(() => ((stepIndex + 1) / steps.length) * 100, [stepIndex]);

  return (
    <section className="sc-setup-page">
      <SetupStepHeader current={stepIndex + 1} total={steps.length} progress={progress} onBack={stepIndex > 0 ? () => setStepIndex((value) => value - 1) : undefined} />
      <div className="sc-setup-card">
        <p className="sc-kicker">Einrichtung</p>
        <h1>{step.title}</h1>
        <p>{step.text}</p>
        {step.options && (
          <div className="sc-option-grid">
            {step.options.map((option) => (
              <SelectableOptionCard key={option} label={option} active={selected[stepIndex] === option} onClick={() => setSelected((state) => ({ ...state, [stepIndex]: option }))} />
            ))}
          </div>
        )}
        {step.fields && (
          <div className="sc-setup-fields">
            {step.fields.map((field) => <input key={field} placeholder={field} />)}
          </div>
        )}
        <button className="sc-primary-action" type="button" onClick={() => (stepIndex === steps.length - 1 ? onFinish() : setStepIndex((value) => value + 1))}>
          {stepIndex === steps.length - 1 ? 'Zur Uebersicht' : 'Weiter'}
        </button>
      </div>
    </section>
  );
}

export function SetupStepHeader({ current, total, progress, onBack }: { current: number; total: number; progress: number; onBack?: () => void }) {
  return (
    <header className="sc-setup-header">
      <div className="sc-progress"><span style={{ width: `${progress}%` }} /></div>
      <div>
        <button type="button" onClick={onBack} disabled={!onBack}>Zurueck</button>
        <span>Schritt {current} / {total}</span>
      </div>
    </header>
  );
}
