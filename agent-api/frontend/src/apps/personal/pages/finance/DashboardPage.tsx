import { useEffect, useRef, useState } from 'react';
import { Activity, AlertTriangle, BrainCircuit, CalendarClock, CheckCircle2, Database, Euro, FileText, Play, Power, QrCode, Save, Server, Settings, ShieldCheck, Upload, WalletCards, X } from 'lucide-react';
import { api } from '@shared/api/client';
import type { AgentStatus } from '@shared/api/client';
import type { Route } from '../../App';
import type { FinanceSummary, Invoice, MonthSummary, Summary } from '@shared/types/invoice';
import { currency, monthNames, shortDate } from '@shared/utils/format';
import { InvoiceTable } from '../../components/finance/InvoiceTable';
import { ExportButtons } from '../../components/finance/ExportButtons';

export function DashboardPage({ navigate }: { navigate: (route: Route) => void }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [finance, setFinance] = useState<FinanceSummary | null>(null);
  const [months, setMonths] = useState<MonthSummary[]>([]);
  const [yearInvoices, setYearInvoices] = useState<Invoice[]>([]);
  const [invoiceAgent, setInvoiceAgent] = useState<AgentStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [agentStatus, setAgentStatus] = useState('');
  const [agentError, setAgentError] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [ebonOpen, setEbonOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const currentYear = new Date().getFullYear();
  const currentMonth = new Date().getMonth() + 1;
  const greeting = getGreeting();

  const load = async () => {
    const [summaryData, financeData, yearData, monthResults, nextAgentStatus] = await Promise.all([
      api.summary(),
      api.financeSummary().catch(() => null),
      api.year(currentYear).catch(() => ({ year: currentYear, months: [] })),
      Promise.all(
        Array.from({ length: 12 }, (_, index) =>
          api.month(currentYear, index + 1, new URLSearchParams()).catch(() => ({ year: currentYear, month: index + 1, invoices: [] })),
        ),
      ),
      api.invoiceAgentStatus().catch(() => null),
    ]);
    setSummary(summaryData);
    setFinance(financeData);
    setMonths(yearData.months);
    setYearInvoices(monthResults.flatMap((result) => result.invoices));
    setInvoiceAgent(nextAgentStatus);
  };
  useEffect(() => { load(); }, []);

  const run = async () => {
    setBusy(true);
    setAgentError('');
    setAgentStatus('Invoice Agent startet. Inbox, E-Mail und vorhandene Belege werden geprüft...');
    try {
      setAgentStatus('Invoice Agent läuft. Dokumente werden gescannt und Metadaten ermittelt...');
      const result = await api.runAgent();
      setAgentStatus('Scan abgeschlossen. Dashboard wird aktualisiert...');
      await load();
      setAgentStatus(`Invoice Agent fertig. ${lastAgentLine(result.stdout) || 'Neue Belege wurden einsortiert oder zur Prüfung markiert.'}`);
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : 'Invoice Agent konnte nicht gestartet werden.');
      setAgentStatus('');
    } finally {
      setBusy(false);
    }
  };

  const toggleAgent = async () => {
    setBusy(true);
    setAgentError('');
    try {
      const active = invoiceAgent?.enabled !== false;
      const next = active ? await api.disableInvoiceAgent() : await api.enableInvoiceAgent();
      setInvoiceAgent(next);
      setAgentStatus(active ? 'Automatischer Invoice-Agent pausiert.' : 'Automatischer Invoice-Agent aktiviert.');
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : 'Invoice Agent konnte nicht umgeschaltet werden.');
      setAgentStatus('');
    } finally {
      setBusy(false);
    }
  };

  const saveInvoiceSettings = async (payload: { enabled: boolean }) => {
    setBusy(true);
    setAgentError('');
    try {
      const next = await api.updateInvoiceAgentSettings(payload);
      setInvoiceAgent(next);
      setSettingsOpen(false);
      setAgentStatus('Invoice-Agent Einstellungen gespeichert.');
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : 'Invoice Einstellungen konnten nicht gespeichert werden.');
      setAgentStatus('');
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file?: File) => {
    if (!file) return;
    setBusy(true);
    setAgentError('');
    try {
      await api.upload(file);
      await load();
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : 'Upload fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  };

  const uploadEbon = async (payload: { content: string; filename?: string }) => {
    setBusy(true);
    setAgentError('');
    try {
      await api.uploadEbonContent({ ...payload, source: 'manual_qr' });
      setEbonOpen(false);
      setAgentStatus('E-Bon/QR-Inhalt wurde hochgeladen. Starte den Invoice Agent, um ihn zu verarbeiten.');
      await load();
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : 'E-Bon konnte nicht hochgeladen werden.');
    } finally {
      setBusy(false);
    }
  };

  const cleanup = async () => {
    setBusy(true);
    setAgentError('');
    setAgentStatus('Archiv-Cleanup prüft unreferenzierte Dateien...');
    try {
      const preview = await api.cleanupArchive(false);
      if (preview.unreferenced === 0) {
        setAgentStatus(`Archiv sauber. ${preview.archive_files} Dateien geprüft, keine unreferenzierten Dateien gefunden.`);
        return;
      }
      const apply = confirm(`${preview.unreferenced} unreferenzierte Archivdateien gefunden. In Backup verschieben?`);
      if (!apply) {
        setAgentStatus(`Cleanup abgebrochen. ${preview.unreferenced} unreferenzierte Dateien gefunden.`);
        return;
      }
      const result = await api.cleanupArchive(true);
      setAgentStatus(`Cleanup fertig. ${result.moved} Dateien nach ${result.backup_dir ?? 'Backup'} verschoben.`);
      await load();
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : 'Archiv-Cleanup fehlgeschlagen.');
      setAgentStatus('');
    } finally {
      setBusy(false);
    }
  };

  const invoices = summary?.latest_uploads ?? [];
  const confidence = confidenceRate(invoices);
  const categories = categoryTotals(yearInvoices);

  return (
    <div className="page-stack">
      <header className="dashboard-hero">
        <div>
          <span className="eyebrow">Finance</span>
          <h1>{greeting}, Nawid</h1>
          <p>Rechnungen, Verträge, Versicherungen, Abos und laufende Verpflichtungen an einem Ort.</p>
        </div>
        <div className="invoice-hero-actions">
          <button className="icon-button" type="button" onClick={() => setSettingsOpen(true)} aria-label="Einstellungen öffnen">
            <Settings size={19} />
          </button>
        </div>
      </header>

      <section className="kpi-grid">
        <Kpi icon={WalletCards} label="Monatliche Verpflichtungen" value={currency(finance?.monthly_obligations)} note={`${finance?.active_contracts ?? 0} aktive Verträge`} tone="blue" />
        <Kpi icon={ShieldCheck} label="Versicherungen" value={finance?.active_insurances ?? 0} note={`${finance?.active_subscriptions ?? 0} aktive Abos`} tone="green" />
        <Kpi icon={Euro} label="Ausgaben aktueller Monat" value={currency(summary?.current_month_total)} note={`${monthNames[currentMonth - 1]} ${currentYear}`} tone="blue" />
        <Kpi icon={WalletCards} label="Ausgaben aktuelles Jahr" value={currency(summary?.current_year_total)} note={`${currentYear} laufend`} tone="violet" />
        <Kpi icon={AlertTriangle} label="Nächste Frist" value={finance?.next_cancellation_deadline ? shortDate(finance.next_cancellation_deadline) : 'keine'} note="Kündigung/Verlängerung" tone="yellow" />
      </section>

      {(agentStatus || agentError) && (
        <section className={`panel ${agentError ? 'error-panel' : busy ? 'status-panel' : 'success-panel'}`}>
          <div className="agent-run-status">
            {agentError ? <AlertTriangle size={18} /> : busy ? <Activity size={18} /> : <CheckCircle2 size={18} />}
            <span>{agentError || agentStatus}</span>
          </div>
        </section>
      )}

      <section className="dashboard-grid">
        <div className="panel chart-panel wide-panel spend-trend-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">Ausgabenentwicklung</span>
              <h2>Monate {currentYear}</h2>
            </div>
          </div>
          <BarChart months={months} />
        </div>

        <div className="panel chart-panel category-chart-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">Kategorien</span>
              <h2>Ausgaben nach Kategorie</h2>
            </div>
          </div>
          <DonutChart data={categories} />
        </div>

        <div className="panel invoice-list-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">Neueste Rechnungen & Belege</span>
              <h2>Belegliste</h2>
            </div>
            <button className="button ghost" onClick={() => navigate({ name: 'years' })}>Archiv</button>
          </div>
          <InvoiceTable
            invoices={invoices}
            onOpen={(invoice) => navigate({ name: 'invoice', id: invoice.id })}
            onPreview={(invoice) => navigate({ name: 'invoice', id: invoice.id })}
            onDelete={async (invoice) => {
              if (!confirm(`Beleg ${invoice.vendor} löschen?`)) return;
              await api.deleteInvoice(invoice.id);
              await load();
            }}
          />
        </div>

        <div className="panel finance-obligations-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">Laufende Verpflichtungen</span>
              <h2>Kosten nach Bereich</h2>
            </div>
            <button className="button ghost" onClick={() => navigate({ name: 'contracts' })}>Verträge</button>
          </div>
          <div className="finance-cost-list">
            {(finance?.costs_by_category ?? []).map((row) => (
              <button key={row.category} className="mini-contract-row" onClick={() => navigate({ name: 'contracts', category: row.category })}>
                <WalletCards size={16} />
                <span>{row.label}</span>
                <strong>{currency(row.monthly_cost)}</strong>
              </button>
            ))}
            {!finance?.costs_by_category?.length && <p className="muted-text">Noch keine laufenden Verträge erfasst.</p>}
          </div>
        </div>

        <aside className="quick-stack">
          <div className="panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">Schnellaktionen</span>
                <h2>Aktionen · {monthNames[currentMonth - 1]} {currentYear}</h2>
              </div>
            </div>
            <div className="quick-actions">
              <button className="button primary" onClick={() => fileRef.current?.click()} disabled={busy}><Upload size={16} /> Beleg hochladen</button>
              <button className="button secondary" onClick={() => navigate({ name: 'contracts' })} disabled={busy}><WalletCards size={16} /> Verträge verwalten</button>
              <button className="button secondary" onClick={() => navigate({ name: 'contractAnalysis' })} disabled={busy}><BrainCircuit size={16} /> Analysen öffnen</button>
              <button className="button secondary" onClick={() => setEbonOpen(true)} disabled={busy}><QrCode size={16} /> E-Bon / QR einfügen</button>
              <button className="button secondary" onClick={run} disabled={busy}>
                {busy ? <Activity size={16} /> : <Play size={16} />}
                {busy ? 'Agent läuft...' : 'Invoice Agent starten'}
              </button>
              <button className="button ghost" onClick={toggleAgent} disabled={busy}>
                <Power size={16} /> {invoiceAgent?.enabled === false ? 'Automatik aktivieren' : 'Automatik pausieren'}
              </button>
              <button className="button ghost" onClick={cleanup} disabled={busy}><Database size={16} /> Archiv-Cleanup</button>
              <ExportButtons year={currentYear} month={currentMonth} compact />
              <input ref={fileRef} type="file" hidden onChange={(event) => upload(event.target.files?.[0])} />
            </div>
          </div>

          <div className="panel system-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">Systemstatus</span>
                <h2>RoboterSteve</h2>
              </div>
            </div>
            <StatusRow icon={Activity} label="Invoice Agent" value={agentStatusLabel(invoiceAgent, busy)} tone={busy || invoiceAgent?.is_running ? 'yellow' : invoiceAgent?.enabled === false ? 'blue' : 'green'} />
            <StatusRow icon={Power} label="Nächster Lauf" value={formatNextRun(invoiceAgent)} tone="blue" />
            <StatusRow icon={Database} label="Datenbank" value="verbunden" tone="green" />
            <StatusRow icon={Server} label="Speicherplatz" value="lokal" tone="blue" />
            <StatusRow icon={CheckCircle2} label="Letzter Lauf" value={invoices[0]?.updated_at ? shortDate(invoices[0].updated_at) : 'noch keiner'} tone="blue" />
          </div>
        </aside>

      </section>
      <InvoiceSettingsDrawer
        open={settingsOpen}
        status={invoiceAgent}
        loading={busy}
        onClose={() => setSettingsOpen(false)}
        onSave={saveInvoiceSettings}
        onOpenScheduler={() => {
          setSettingsOpen(false);
          navigate({ name: 'schedulerDashboard' });
        }}
      />
      <EbonUploadDrawer
        open={ebonOpen}
        loading={busy}
        onClose={() => setEbonOpen(false)}
        onSave={uploadEbon}
      />
    </div>
  );
}

function EbonUploadDrawer({
  open,
  loading,
  onClose,
  onSave,
}: {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onSave: (payload: { content: string; filename?: string }) => void;
}) {
  const [content, setContent] = useState('');
  const [filename, setFilename] = useState('e-bon-qr.txt');

  useEffect(() => {
    if (!open) return;
    setContent('');
    setFilename('e-bon-qr.txt');
  }, [open]);

  if (!open) return null;

  return (
    <div className="wellness-drawer-layer">
      <button className="wellness-drawer-backdrop" type="button" onClick={onClose} aria-label="E-Bon Upload schließen" />
      <aside className="wellness-settings-drawer" role="dialog" aria-modal="true" aria-label="E-Bon QR Inhalt hochladen">
        <header>
          <div>
            <span className="eyebrow">E-Bon</span>
            <h2>QR-Inhalt einfügen</h2>
            <p>Füge den ausgelesenen QR-Code- oder E-Bon-Text ein. Der Inhalt wird wie ein Beleg in die Inbox gelegt.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Schließen"><X size={18} /></button>
        </header>
        <div className="panel wellness-settings-panel invoice-settings-panel">
          <form
            className="wellness-settings-form invoice-settings-form"
            onSubmit={(event) => {
              event.preventDefault();
              onSave({ content, filename });
            }}
          >
            <section className="wellness-settings-section invoice-settings-section">
              <div className="wellness-settings-section-head invoice-settings-head">
                <span><QrCode size={18} /></span>
                <div>
                  <h3>QR-/E-Bon-Daten</h3>
                  <p>Geeignet für Text, JSON, CSV oder den rohen QR-Code-Inhalt.</p>
                </div>
              </div>
              <label className="wide">
                Dateiname
                <input value={filename} onChange={(event) => setFilename(event.target.value)} placeholder="e-bon-qr.txt" />
              </label>
              <label className="wide">
                Inhalt
                <textarea
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  rows={10}
                  placeholder="QR-Code-Inhalt oder E-Bon-Text hier einfügen..."
                />
              </label>
            </section>
            <div className="wellness-settings-actions invoice-settings-actions">
              <button className="button ghost" type="button" onClick={onClose}>Abbrechen</button>
              <button className="button primary" type="submit" disabled={loading || !content.trim()}>
                <Save size={16} /> E-Bon hochladen
              </button>
            </div>
          </form>
        </div>
      </aside>
    </div>
  );
}

function InvoiceSettingsDrawer({
  open,
  status,
  loading,
  onClose,
  onSave,
  onOpenScheduler,
}: {
  open: boolean;
  status: AgentStatus | null;
  loading: boolean;
  onClose: () => void;
  onSave: (payload: { enabled: boolean }) => void;
  onOpenScheduler: () => void;
}) {
  const [enabled, setEnabled] = useState(true);
  const [dailyRun, setDailyRun] = useState('22:00');

  useEffect(() => {
    if (!open) return;
    setEnabled(status?.enabled !== false);
    setDailyRun(timeInputValue(status?.schedule?.[0] ?? '22:00:00'));
  }, [open, status]);

  if (!open) return null;

  return (
    <div className="wellness-drawer-layer">
      <button className="wellness-drawer-backdrop" type="button" onClick={onClose} aria-label="Einstellungen schließen" />
      <aside className="wellness-settings-drawer" role="dialog" aria-modal="true" aria-label="Invoice Agent Einstellungen">
        <header>
          <div>
            <span className="eyebrow">Invoice Agent</span>
            <h2>Einstellungen</h2>
            <p>Automatische Mail- und Inbox-Scans planen.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Schließen"><X size={18} /></button>
        </header>
        <div className="panel wellness-settings-panel invoice-settings-panel">
          <form
            className="wellness-settings-form invoice-settings-form"
            onSubmit={(event) => {
              event.preventDefault();
              onSave({
                enabled,
              });
            }}
          >
            <section className="wellness-settings-section invoice-settings-section">
              <div className="wellness-settings-section-head invoice-settings-head">
                <span><CalendarClock size={18} /></span>
                <div>
                  <h3>Automationen</h3>
                  <p>Zeitplan wird über den Scheduler verwaltet. Diese Zeit ist nur der Agent-Default.</p>
                </div>
              </div>
              <div className="wellness-scheduler-note">
                <strong>Aktive Laufzeiten liegen im Scheduler.</strong>
                <span>Änderungen im Scheduler haben Vorrang und werden nicht durch Invoice-Defaults überschrieben.</span>
                <button className="button secondary" type="button" onClick={onOpenScheduler}>
                  Zeitplan bearbeiten
                </button>
              </div>
              <div className="invoice-settings-card">
                <label className="wellness-toggle-line invoice-toggle-line">
                  <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
                  <span />
                  <div>
                    <strong>Automatischer Scan</strong>
                    <small>{enabled ? 'E-Mails und Inbox werden täglich geprüft.' : 'Geplante Scans sind pausiert.'}</small>
                  </div>
                </label>
                <span className={`agent-state-pill invoice-state-pill ${enabled ? 'ok' : 'waiting'}`}>{enabled ? 'Aktiv' : 'Pausiert'}</span>
              </div>
              <div className="invoice-time-card">
                <label className="wellness-field invoice-time-field">
                  <small>Default täglicher Scan</small>
                  <input type="time" value={dailyRun} readOnly disabled aria-label="Täglicher Scan" />
                </label>
                <div>
                  <strong>{dailyRun}</strong>
                  <span>im Scheduler bearbeiten</span>
                </div>
              </div>
            </section>
            <div className="wellness-settings-footer invoice-settings-footer">
              <button className="button primary" type="submit" disabled={loading}>
                <Save size={18} />
                Einstellungen speichern
              </button>
            </div>
          </form>
        </div>
      </aside>
    </div>
  );
}

function lastAgentLine(output: string) {
  return output
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(-1)[0] ?? '';
}

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Guten Morgen';
  if (hour < 18) return 'Guten Tag';
  return 'Guten Abend';
}

function agentStatusLabel(status: AgentStatus | null, busy: boolean) {
  if (busy || status?.is_running) return 'scannt Belege';
  if (status?.enabled === false) return 'pausiert';
  if (status?.last_status === 'error') return 'Fehler';
  return 'automatisch aktiv';
}

function formatNextRun(status: AgentStatus | null) {
  if (!status || status.enabled === false) return 'nicht geplant';
  if (!status.next_scheduled_run) return (status.schedule ?? []).join(', ') || 'nicht geplant';
  const date = new Date(status.next_scheduled_run);
  if (!Number.isFinite(date.getTime())) return status.next_scheduled_run;
  return date.toLocaleString('de-DE', { weekday: 'short', hour: '2-digit', minute: '2-digit' });
}

function timeInputValue(value: string) {
  return value.slice(0, 5) || '22:00';
}

function Kpi({ icon: Icon, label, value, note, tone }: { icon: typeof Euro; label: string; value: string | number; note: string; tone: 'blue' | 'violet' | 'green' | 'yellow' }) {
  return (
    <div className={`kpi-card ${tone}`}>
      <div className="kpi-icon"><Icon size={22} /></div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function BarChart({ months }: { months: MonthSummary[] }) {
  const byMonth = new Map(months.map((month) => [month.month, month]));
  const values = Array.from({ length: 12 }, (_, index) => byMonth.get(index + 1)?.expense_total ?? 0);
  const max = Math.max(...values, 1);
  return (
    <div className="bar-chart">
      {values.map((value, index) => (
        <div className="bar-item" key={monthNames[index]}>
          <div className="bar-track">
            <div className="bar-fill" style={{ height: `${Math.max((value / max) * 100, value ? 8 : 2)}%` }} />
          </div>
          <span>{monthNames[index].slice(0, 3)}</span>
        </div>
      ))}
    </div>
  );
}

function DonutChart({ data }: { data: Array<{ label: string; value: number; color: string }> }) {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  const gradient = total
    ? data.reduce((parts, item) => {
      const start = parts.offset;
      const end = start + (item.value / total) * 100;
      parts.segments.push(`${item.color} ${start}% ${end}%`);
      parts.offset = end;
      return parts;
    }, { offset: 0, segments: [] as string[] }).segments.join(', ')
    : '#26344d 0 100%';
  return (
    <div className="donut-wrap">
      <div className="donut" style={{ background: `conic-gradient(${gradient})` }}>
        <span>{data.length || 0}</span>
      </div>
      <div className="donut-legend">
        {(data.length ? data : [{ label: 'Keine Daten', value: 0, color: '#4d8dff' }]).map((item) => (
          <div key={item.label}>
            <i style={{ background: item.color }} />
            <span>{item.label}</span>
            <b>{currency(item.value)}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusRow({ icon: Icon, label, value, tone }: { icon: typeof Activity; label: string; value: string; tone: 'blue' | 'green' | 'yellow' }) {
  return (
    <div className="status-row">
      <Icon size={18} />
      <span>{label}</span>
      <b className={tone}>{value}</b>
    </div>
  );
}

function confidenceRate(invoices: Invoice[]) {
  const values = invoices.map((invoice) => invoice.ai_confidence ?? invoice.confidence).filter((value): value is number => typeof value === 'number');
  if (!values.length) return 0;
  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  return Math.round(average <= 1 ? average * 100 : average);
}

function categoryTotals(invoices: Invoice[]) {
  const colors = ['#7c5cff', '#4d8dff', '#34d399', '#fbbf24', '#fb7185'];
  const totals = invoices.reduce<Record<string, number>>((acc, invoice) => {
    const label = invoice.category || 'Ohne Kategorie';
    acc[label] = (acc[label] ?? 0) + (invoice.gross_amount ?? invoice.amount ?? 0);
    return acc;
  }, {});
  return Object.entries(totals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([label, value], index) => ({ label, value, color: colors[index % colors.length] }));
}
