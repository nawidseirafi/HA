import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import type { MarketReport, MarketSummary, MarketWatchlistItem } from '../../api/client';
import { api } from '../../api/client';
import type { Route } from '../../App';
import { formatPercent, formatPrice } from '../../components/market/MarketReportCard';
import { MarketRunButton } from '../../components/market/MarketRunButton';
import { MarketSignalBadge } from '../../components/market/MarketSignalBadge';
import { MarketSummaryCards } from '../../components/market/MarketSummaryCards';
import { AlertTriangle, ArrowDownRight, ArrowUpRight, TrendingUp } from 'lucide-react';

export function MarketDashboardPage({ navigate }: { navigate: (route: Route) => void }) {
  const [summary, setSummary] = useState<MarketSummary | null>(null);
  const [watchlistItems, setWatchlistItems] = useState<MarketWatchlistItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    try {
      const [nextSummary, nextWatchlist] = await Promise.all([
        api.marketSummary(),
        api.marketWatchlist(),
      ]);
      setSummary(nextSummary);
      setWatchlistItems(nextWatchlist);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Marktdaten konnten nicht geladen werden.');
    }
  };

  useEffect(() => { load(); }, []);

  const run = async () => {
    setBusy(true);
    setError('');
    try {
      await api.runMarketAgent();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Marktanalyse fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  };

  const setAgentEnabled = async (enabled: boolean) => {
    setBusy(true);
    setError('');
    try {
      await (enabled ? api.enableMarketAgent() : api.disableMarketAgent());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'MarketAgent konnte nicht geschaltet werden.');
    } finally {
      setBusy(false);
    }
  };

  const agentEnabled = summary?.agent?.enabled ?? true;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">MarketAgent</span>
          <h1>Marktanalyse</h1>
          <p className="market-disclaimer">Keine Finanzberatung.</p>
        </div>
        <div className="button-row">
          <button className={agentEnabled ? 'button secondary' : 'button primary'} onClick={() => setAgentEnabled(!agentEnabled)} disabled={busy}>
            {agentEnabled ? 'Agent deaktivieren' : 'Agent aktivieren'}
          </button>
          <button className="button secondary" onClick={() => navigate({ name: 'marketWatchlist' })}>Watchlist</button>
          <MarketRunButton busy={busy || !agentEnabled} onRun={run} />
        </div>
      </header>

      {error && <section className="panel error-panel">{error}</section>}
      <MarketSummaryCards summary={summary} reports={summary?.latest_reports ?? []} watchlistItems={watchlistItems} />
      <MarketInsightCards summary={summary} onOpen={(symbol) => navigate({ name: 'marketSymbol', symbol })} />
      <MarketDiscoveryPanel reports={summary?.discovery_reports ?? []} onOpen={(symbol) => navigate({ name: 'marketSymbol', symbol })} />
      <MarketIntelTable
        reports={summary?.latest_reports ?? []}
        watchlistItems={watchlistItems}
        onOpen={(symbol) => navigate({ name: 'marketSymbol', symbol })}
      />
    </div>
  );
}

function MarketIntelTable({
  reports,
  watchlistItems,
  onOpen,
}: {
  reports: MarketReport[];
  watchlistItems: MarketWatchlistItem[];
  onOpen: (symbol: string) => void;
}) {
  const reportBySymbol = new Map(reports.map((report) => [report.symbol.toUpperCase(), report]));
  const rows = watchlistItems.map((item) => ({
    item,
    report: reportBySymbol.get(item.symbol.toUpperCase()),
  }));
  return (
    <section className="panel market-intel-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Watchlist</span>
          <h2>Signale</h2>
        </div>
      </div>
      <div className="market-intel-table">
        {rows.map(({ item, report }) => (
          <button className="market-intel-card" key={item.id} onClick={() => onOpen(item.symbol)}>
            <div className="market-intel-card-head">
              <strong>{item.symbol}</strong>
              {report ? <MarketSignalBadge signal={report.recommendation || report.signal} /> : <span className="market-signal watch">Offen</span>}
            </div>
            <div className="market-intel-card-price">
              <b>{report ? formatPrice(report.price) : '-'}</b>
              <span className={!report || (report.change_percent ?? 0) >= 0 ? 'market-positive' : 'market-negative'}>{report ? formatPercent(report.change_percent) : '-'}</span>
            </div>
            <div className="market-intel-card-meta">
              <span>{report ? `${Math.round(report.confidence || 0)}% Conf.` : 'Keine Analyse'}</span>
              <span>{report ? `Risiko ${riskLabel(report.risk_level)}` : item.asset_type}</span>
              {report && <em className={`market-quality ${report.data_quality ?? 'unknown'}`}>{qualityLabel(report)}</em>}
            </div>
            <p>{report ? oneSentence(report.summary, 110) : 'Noch keine Analyse vorhanden. Manuellen Run starten oder Scheduler abwarten.'}</p>
          </button>
        ))}
        {rows.length === 0 && <p className="muted">Noch keine Watchlist-Einträge vorhanden.</p>}
      </div>
    </section>
  );
}

function riskLabel(value: string | undefined) {
  if (value === 'low') return 'Low';
  if (value === 'high') return 'High';
  return 'Medium';
}

function MarketInsightCards({ summary, onOpen }: { summary: MarketSummary | null; onOpen: (symbol: string) => void }) {
  const reports = summary?.latest_reports ?? [];
  const topBuy = reports
    .filter((report) => (report.recommendation || report.signal) === 'buy')
    .sort((a, b) => (b.confidence || 0) - (a.confidence || 0))[0];
  const topRisk = selectTopRisk(reports);
  const topGainer = summary?.top_gainers?.[0] ?? reports.slice().sort((a, b) => (b.change_percent ?? -999) - (a.change_percent ?? -999))[0];
  const topLoser = summary?.top_losers?.[0] ?? reports.slice().sort((a, b) => (a.change_percent ?? 999) - (b.change_percent ?? 999))[0];

  return (
    <section className="market-insight-grid" aria-label="Market Insights">
      <InsightCard
        icon={<TrendingUp size={20} />}
        tone="buy"
        title="Top Buy"
        report={topBuy}
        main={topBuy?.symbol}
        value={topBuy ? `${Math.round(topBuy.confidence || 0)}%` : undefined}
        detail={topBuy ? oneSentence(topBuy.summary, 120) : undefined}
        onOpen={onOpen}
      />
      <InsightCard
        icon={<AlertTriangle size={20} />}
        tone="risk"
        title="Top Risiko"
        report={topRisk}
        main={topRisk?.symbol}
        value={topRisk ? (topRisk.recommendation || topRisk.signal).toUpperCase() : undefined}
        detail={topRisk ? oneSentence(topRisk.summary, 120) : undefined}
        onOpen={onOpen}
      />
      <InsightCard
        icon={<ArrowUpRight size={20} />}
        tone="winner"
        title="Top Gewinner"
        report={topGainer}
        main={topGainer?.symbol}
        value={topGainer ? formatPercent(topGainer.change_percent) : undefined}
        detail={topGainer ? 'Staerkste Tagesperformance.' : undefined}
        onOpen={onOpen}
      />
      <InsightCard
        icon={<ArrowDownRight size={20} />}
        tone="loser"
        title="Top Verlierer"
        report={topLoser}
        main={topLoser?.symbol}
        value={topLoser ? formatPercent(topLoser.change_percent) : undefined}
        detail={topLoser ? 'Schwaechste Tagesperformance.' : undefined}
        onOpen={onOpen}
      />
    </section>
  );
}

function InsightCard({
  icon,
  tone,
  title,
  report,
  main,
  value,
  detail,
  onOpen,
}: {
  icon: ReactNode;
  tone: 'buy' | 'risk' | 'winner' | 'loser';
  title: string;
  report?: MarketReport;
  main?: string;
  value?: string;
  detail?: string;
  onOpen: (symbol: string) => void;
}) {
  const content = (
    <>
      <div className="market-insight-head">
        <span>{icon}</span>
        <strong>{title}</strong>
      </div>
      <div className="market-insight-body">
        <b>{main || 'Keine Daten'}</b>
        <em>{value || '-'}</em>
        <p>{detail || 'Keine Daten'}</p>
      </div>
    </>
  );
  if (!report || !main) {
    return <article className={`market-insight-card ${tone}`}>{content}</article>;
  }
  return (
    <button className={`market-insight-card ${tone}`} type="button" onClick={() => onOpen(report.symbol)}>
      {content}
    </button>
  );
}

function selectTopRisk(reports: MarketReport[]) {
  const nonBuyReports = reports.filter((report) => (report.recommendation || report.signal) !== 'buy');
  const sellReports = nonBuyReports.filter((report) => (report.recommendation || report.signal) === 'sell');
  if (sellReports.length) {
    return sellReports
      .slice()
      .sort((a, b) => sellRiskScore(b) - sellRiskScore(a))[0];
  }
  return nonBuyReports
    .slice()
    .sort((a, b) => riskScore(b) - riskScore(a))[0];
}

function sellRiskScore(report: MarketReport) {
  const confidenceRisk = 100 - Number(report.confidence || 0);
  const trendRisk = Math.max(0, -(report.change_percent ?? 0)) * 4;
  return confidenceRisk + trendRisk;
}

function riskScore(report: MarketReport) {
  const signal = report.recommendation || report.signal;
  const risk = report.risk_level === 'high' ? 40 : report.risk_level === 'medium' ? 20 : 0;
  const signalRisk = signal === 'sell' ? 60 : signal === 'watch' ? 35 : signal === 'hold' ? 12 : -100;
  const confidenceRisk = Math.max(0, 100 - Number(report.confidence || 0)) / 2;
  const trendRisk = Math.max(0, -(report.change_percent ?? 0)) * 3;
  return risk + signalRisk + confidenceRisk + trendRisk;
}

function qualityLabel(report: MarketReport) {
  if (report.data_quality === 'real') return 'LIVE + KI';
  if (report.analysis_source === 'llm') return 'KI';
  if (report.data_quality === 'error') return 'ERROR';
  return 'TEILDATEN';
}

function MarketDiscoveryPanel({ reports, onOpen }: { reports: MarketReport[]; onOpen: (symbol: string) => void }) {
  const topReports = reports.slice(0, 5);
  return (
    <section className="panel market-intel-panel">
      <div className="section-title">
        <div>
          <span className="eyebrow">Discovery</span>
          <h2>Top Chancen</h2>
        </div>
      </div>
      <div className="market-intel-table">
        {topReports.map((report) => (
          <button className="market-intel-card" key={`${report.symbol}-${report.created_at}`} onClick={() => onOpen(report.symbol)}>
            <div className="market-intel-card-head">
              <strong>{report.symbol}</strong>
              <MarketSignalBadge signal={report.recommendation || report.signal} />
            </div>
            <div className="market-intel-card-price">
              <b>{Math.round(report.confidence || 0)}%</b>
              <span>{riskLabel(report.risk_level)} Risiko</span>
            </div>
            <div className="market-intel-card-meta">
              <span>{reportName(report)}</span>
              <em className={`market-quality ${report.data_quality ?? 'unknown'}`}>{qualityLabel(report)}</em>
            </div>
            <p>{oneSentence(report.summary)}</p>
          </button>
        ))}
        {reports.length === 0 && <p className="muted">Noch keine Marktideen. Analyse starten.</p>}
      </div>
    </section>
  );
}

function reportName(report: MarketReport) {
  const raw = report.ai_raw_json as { quote?: { name?: string } } | undefined;
  return raw?.quote?.name || report.symbol;
}

function oneSentence(value: string, maxLength = 150) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return 'Kurzes Marktsignal ohne langen Bericht.';
  const firstSentence = text.match(/^[^.!?]+[.!?]?/)?.[0] || text;
  return firstSentence.length > maxLength ? `${firstSentence.slice(0, maxLength - 3).trim()}...` : firstSentence;
}
