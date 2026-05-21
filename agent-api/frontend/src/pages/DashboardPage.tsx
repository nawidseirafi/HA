import { useEffect, useRef, useState } from 'react';
import { Activity, AlertTriangle, Bell, BrainCircuit, CheckCircle2, Database, Euro, FileText, Moon, Play, Server, Upload, WalletCards } from 'lucide-react';
import { api } from '../api/client';
import type { Route } from '../App';
import type { Invoice, MonthSummary, Summary } from '../types/invoice';
import { currency, monthNames, shortDate } from '../lib/format';
import { InvoiceTable } from '../components/InvoiceTable';
import { ExportButtons } from '../components/ExportButtons';

export function DashboardPage({ navigate }: { navigate: (route: Route) => void }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [months, setMonths] = useState<MonthSummary[]>([]);
  const [yearInvoices, setYearInvoices] = useState<Invoice[]>([]);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const currentYear = new Date().getFullYear();
  const currentMonth = new Date().getMonth() + 1;
  const greeting = getGreeting();

  const load = async () => {
    const [summaryData, yearData, monthResults] = await Promise.all([
      api.summary(),
      api.year(currentYear).catch(() => ({ year: currentYear, months: [] })),
      Promise.all(
        Array.from({ length: 12 }, (_, index) =>
          api.month(currentYear, index + 1, new URLSearchParams()).catch(() => ({ year: currentYear, month: index + 1, invoices: [] })),
        ),
      ),
    ]);
    setSummary(summaryData);
    setMonths(yearData.months);
    setYearInvoices(monthResults.flatMap((result) => result.invoices));
  };
  useEffect(() => { load(); }, []);

  const run = async () => {
    setBusy(true);
    await api.runAgent();
    await load();
    setBusy(false);
  };

  const upload = async (file?: File) => {
    if (!file) return;
    setBusy(true);
    await api.upload(file);
    await load();
    setBusy(false);
  };

  const invoices = summary?.latest_uploads ?? [];
  const confidence = confidenceRate(invoices);
  const categories = categoryTotals(yearInvoices);

  return (
    <div className="page-stack">
      <header className="dashboard-hero">
        <div>
          <span className="eyebrow">Invoice Manager</span>
          <h1>{greeting}, Nawid</h1>
          <p>Hier ist die Übersicht deiner Finanzen und Belege.</p>
        </div>
        <div className="top-tools">
          <button className="icon-button" title="Dark Mode"><Moon size={18} /></button>
          <button className="icon-button" title="Benachrichtigungen"><Bell size={18} /></button>
        </div>
      </header>

      <section className="kpi-grid">
        <Kpi icon={Euro} label="Ausgaben aktueller Monat" value={currency(summary?.current_month_total)} note="Live aus FastAPI" tone="blue" />
        <Kpi icon={WalletCards} label="Ausgaben aktuelles Jahr" value={currency(summary?.current_year_total)} note={`${currentYear} laufend`} tone="violet" />
        <Kpi icon={FileText} label="Belege gesamt" value={summary?.total_invoices ?? 0} note="Archivierte Dokumente" tone="green" />
        <Kpi icon={AlertTriangle} label="Offene Prüfungen" value={summary?.needs_review_count ?? 0} note="Manuelle Kontrolle" tone="yellow" />
        <Kpi icon={BrainCircuit} label="KI-Erkennungsrate" value={`${confidence}%`} note={`${summary?.ai_error_count ?? 0} KI-Fehler`} tone="blue" />
      </section>

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

        <aside className="quick-stack">
          <div className="panel latest-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">Uploads</span>
                <h2>Letzte Uploads</h2>
              </div>
              <button className="button ghost" onClick={() => navigate({ name: 'years' })}>Archiv</button>
            </div>
            <div className="upload-list">
              {invoices.slice(0, 5).map((invoice) => (
                <button key={invoice.id} onClick={() => navigate({ name: 'invoice', id: invoice.id })}>
                  <span className={`status-dot ${invoice.review_status}`} />
                  <div>
                    <strong>{invoice.vendor || 'Unbekannter Beleg'}</strong>
                    <small>{shortDate(invoice.invoice_date)} · {invoice.category || 'Ohne Kategorie'}</small>
                  </div>
                  <b>{currency(invoice.gross_amount ?? invoice.amount, invoice.currency)}</b>
                </button>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">Schnellaktionen</span>
                <h2>Aktionen · {monthNames[currentMonth - 1]} {currentYear}</h2>
              </div>
            </div>
            <div className="quick-actions">
              <button className="button primary" onClick={() => fileRef.current?.click()} disabled={busy}><Upload size={16} /> Beleg hochladen</button>
              <button className="button secondary" onClick={run} disabled={busy}><Play size={16} /> Invoice Agent starten</button>
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
            <StatusRow icon={Activity} label="Invoice Agent" value={busy ? 'aktiv' : 'bereit'} tone={busy ? 'yellow' : 'green'} />
            <StatusRow icon={Database} label="Datenbank" value="verbunden" tone="green" />
            <StatusRow icon={Server} label="Speicherplatz" value="lokal" tone="blue" />
            <StatusRow icon={CheckCircle2} label="Letzter Lauf" value={invoices[0]?.updated_at ? shortDate(invoices[0].updated_at) : 'noch keiner'} tone="blue" />
          </div>
        </aside>

      </section>
    </div>
  );
}

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Guten Morgen';
  if (hour < 18) return 'Guten Tag';
  return 'Guten Abend';
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
