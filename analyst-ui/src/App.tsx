import React, { useState, useRef, useCallback } from 'react';
import {
  Bot, Play, CheckCircle2, Loader2, AlertTriangle,
  FileText, Mail, Sparkles, TrendingUp, ShoppingBag,
  DollarSign, Download, Users, BarChart3, RefreshCw,
  ImageIcon, ChevronDown, ChevronUp, Zap, Globe, Package,
} from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────

interface KPIResult {
  total_revenue?: number;
  total_orders?: number;
  average_order_value?: number;
  unique_customers?: number;
  unique_products?: number;
  date_start?: string;
  date_end?: string;
  returns_value?: number;
}

interface InsightItem {
  category?: string;
  text?: string;
}

interface AgentEvent {
  node: string;
  message: string;
}

interface AnalysisResult {
  status: string;
  kpis: KPIResult;
  insights: Array<InsightItem | string>;
  report_summary: string;
  email_draft: string;
  pdf_path: string;
  chart_urls: string[];
  artifacts: Record<string, unknown>;
  warnings: string[];
  error?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function fmtCurrency(v?: number): string {
  if (v == null || isNaN(Number(v))) return '$0.00';
  const n = Number(v);
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
}

function fmtNumber(v?: number): string {
  if (!v || isNaN(Number(v))) return '0';
  return Number(v).toLocaleString();
}

/** Strip query params and extension, return a clean key like "chart_1_monthly_revenue" */
function chartKey(url: string): string {
  const raw = url.split('/').pop() ?? '';        // "chart_1_monthly_revenue.png?t=123"
  const noQs = raw.split('?')[0];                // "chart_1_monthly_revenue.png"
  return noQs.replace(/\.png$/i, '');            // "chart_1_monthly_revenue"
}

// ── Chart meta ────────────────────────────────────────────────────────────

const CHART_META: Record<string, { label: string; emoji: string }> = {
  chart_1_monthly_revenue: { label: 'Monthly Revenue Trend',   emoji: '📈' },
  chart_2_top_countries:   { label: 'Top 10 Countries',        emoji: '🌍' },
  chart_3_monthly_orders:  { label: 'Monthly Orders',          emoji: '📦' },
  chart_4_top_products:    { label: 'Top Products by Revenue', emoji: '🏆' },
  chart_5_revenue_dist:    { label: 'Revenue Distribution',    emoji: '📊' },
  chart_6_kpi_summary:     { label: 'KPI Summary Table',       emoji: '📋' },
  chart_7_daily_revenue:   { label: 'Daily Rolling Revenue',   emoji: '📅' },
};

function getChartMeta(url: string) {
  const key = chartKey(url);
  return CHART_META[key] ?? { label: key.replace(/_/g, ' '), emoji: '🖼️' };
}

// ── Prompt chips ──────────────────────────────────────────────────────────

const PROMPT_CHIPS = [
  { label: 'Revenue Overview',         icon: <DollarSign className="chip-icon" />,  text: 'Analyze total sales revenue, AOV, and monthly growth trends with executive recommendations' },
  { label: 'Top Products & Returns',   icon: <Package className="chip-icon" />,     text: 'Identify top-selling products by revenue and analyze return order patterns and their financial impact' },
  { label: 'Regional Distribution',    icon: <Globe className="chip-icon" />,       text: 'Break down revenue and order volume by country and identify the highest-performing geographic markets' },
  { label: 'AOV Optimization',         icon: <TrendingUp className="chip-icon" />,  text: 'Analyze average order value trends and provide strategic upsell and bundle recommendations to increase AOV' },
  { label: 'Customer Segmentation',    icon: <Users className="chip-icon" />,       text: 'Segment unique customers by purchase frequency and revenue contribution using Pareto analysis' },
  { label: 'Anomaly Detection',        icon: <Zap className="chip-icon" />,         text: 'Detect revenue anomalies, outlier transactions, and statistically significant deviations in the sales data' },
];

// ── KPI Card ─────────────────────────────────────────────────────────────

interface KPICardProps {
  label: string; value: string; sub?: string;
  icon: React.ReactNode; color: string; glow: string; loading?: boolean;
}
function KPICard({ label, value, sub, icon, color, glow, loading }: KPICardProps) {
  return (
    <div
      className={`kpi-card${loading ? ' kpi-card--pulse' : ''}`}
      style={{ '--accent-card': color, '--glow-card': glow } as React.CSSProperties}
    >
      <div className="kpi-card__icon-wrap">{icon}</div>
      <div className="kpi-card__body">
        <span className="kpi-card__label">{label}</span>
        <p className="kpi-card__value">{value}</p>
        {sub && <p className="kpi-card__sub">{sub}</p>}
      </div>
    </div>
  );
}

// ── Step Badge ────────────────────────────────────────────────────────────

function StepBadge({ step }: { step: AgentEvent }) {
  return (
    <div className="step-badge">
      <div className="step-badge__dot" />
      <div>
        <span className="step-badge__node">{step.node.replace(/_/g, ' ')}</span>
        <p className="step-badge__msg">{step.message}</p>
      </div>
    </div>
  );
}

// ── Chart Gallery ─────────────────────────────────────────────────────────

function ChartGallery({ urls, loading }: { urls: string[]; loading: boolean }) {
  const [expanded, setExpanded] = useState(true);
  const [zoom, setZoom]         = useState<string | null>(null);

  if (!loading && urls.length === 0) return null;

  return (
    <section className="card chart-gallery">
      <div className="card__row" style={{ marginBottom: expanded ? 16 : 0 }}>
        <h2 className="card__title m-0">
          <ImageIcon className="w-4 h-4 text-accent" />
          Analytics Charts
          <span className="chart-badge">
            {urls.length > 0 ? `${urls.length} generated` : 'rendering…'}
          </span>
        </h2>
        <button
          className="btn btn--ghost btn--icon"
          onClick={() => setExpanded(e => !e)}
          title={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {expanded && (
        <>
          {loading && urls.length === 0 && (
            <div className="chart-grid">
              {[1,2,3,4,5,6].map(i => (
                <div key={i} className="chart-item chart-item--skeleton">
                  <div className="chart-img-wrap">
                    <div className="chart-skeleton-img" />
                  </div>
                  <div className="chart-skeleton-label" />
                </div>
              ))}
            </div>
          )}

          {urls.length > 0 && (
            <div className="chart-grid">
              {urls.map(url => {
                const meta = getChartMeta(url);
                return (
                  <div
                    key={url}
                    className="chart-item"
                    onClick={() => setZoom(zoom === url ? null : url)}
                    title={`${meta.label} — click to zoom`}
                  >
                    <div className="chart-img-wrap">
                      <img
                        src={url}
                        alt={meta.label}
                        className="chart-img"
                        loading="lazy"
                        onError={e => {
                          const t = e.currentTarget;
                          if (!t.dataset.retried) {
                            t.dataset.retried = '1';
                            // Retry with cache-bust but strip any existing ?t= first
                            const clean = url.split('?')[0];
                            setTimeout(() => { t.src = `${clean}?t=${Date.now()}`; }, 1200);
                          }
                        }}
                      />
                    </div>
                    <p className="chart-label">
                      <span className="chart-label__emoji">{meta.emoji}</span>
                      {meta.label}
                    </p>
                  </div>
                );
              })}
            </div>
          )}

          {zoom && (
            <div className="chart-lightbox" onClick={() => setZoom(null)}>
              <div className="chart-lightbox__inner" onClick={e => e.stopPropagation()}>
                <img src={zoom} alt={getChartMeta(zoom).label} className="chart-lightbox__img" />
                <p className="chart-lightbox__label">
                  {getChartMeta(zoom).emoji} {getChartMeta(zoom).label}
                </p>
                <button className="chart-lightbox__close" onClick={() => setZoom(null)}>
                  ✕ Close
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────

export default function App() {
  const [query, setQuery]           = useState('Analyze total sales revenue, order trends, and present key executive recommendations');
  const [loading, setLoading]       = useState(false);
  const [agentSteps, setAgentSteps] = useState<AgentEvent[]>([]);
  const [activeNode, setActiveNode] = useState<string>('');
  const [result, setResult]         = useState<AnalysisResult | null>(null);
  const [error, setError]           = useState<string>('');
  const abortRef = useRef<AbortController | null>(null);

  const handleReset = useCallback(() => {
    abortRef.current?.abort();
    setLoading(false); setAgentSteps([]); setActiveNode('');
    setResult(null); setError('');
  }, []);

  const handleRunAnalysis = useCallback(async () => {
    if (!query.trim()) return;
    handleReset();

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);

    try {
      const resp = await fetch('http://127.0.0.1:8000/api/v1/analyze/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_query: query }),
        signal: ctrl.signal,
      });
      if (!resp.ok) throw new Error(`Server ${resp.status}: ${resp.statusText}`);

      const reader  = resp.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error('No body stream');

      let buf = '';
      const processFrame = (frame: string) => {
        for (const line of frame.split('\n')) {
          const t = line.trim();
          if (!t.startsWith('data:')) continue;
          const json = t.slice(5).trim();
          if (!json) continue;
          try {
            const evt = JSON.parse(json);
            if (evt.type === 'node_start') {
              setActiveNode(evt.node);
              setAgentSteps(p => [...p, { node: evt.node, message: evt.message }]);
            } else if (evt.type === 'complete') {
              setResult(evt.data as AnalysisResult);
              setActiveNode('');
              if (evt.data?.error) setError(evt.data.error);
            } else if (evt.type === 'error') {
              setError(evt.message ?? 'Pipeline error');
            }
          } catch { /* ignore partial frames */ }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop() ?? '';
        for (const p of parts) if (p.trim()) processFrame(p);
      }
      if (buf.trim()) processFrame(buf);

    } catch (e: unknown) {
      if ((e as Error)?.name !== 'AbortError') setError((e as Error)?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }, [query, handleReset]);

  const kpis        = result?.kpis ?? {};
  const hasPdf      = !!result?.pdf_path;
  const chartUrls   = result?.chart_urls ?? [];
  const showCharts  = loading || chartUrls.length > 0;
  const hasResult   = !!result;
  const progressPct = agentSteps.length ? Math.min((agentSteps.length / 8) * 100, 100) : 0;

  return (
    <div className="app-shell">

      {/* ── Hero Header ────────────────────────────────────────────────── */}
      <header className="hero">
        <div className="hero__bg" />
        <div className="hero__content">
          <div className="hero__brand">
            <div className="hero__logo">
              <Bot className="w-6 h-6" />
            </div>
            <div>
              <h1 className="hero__title">Enterprise Multi-Agent Business Analyst</h1>
              <p className="hero__sub">LangGraph · FastAPI · ReportLab · Parallel Chart Engine</p>
            </div>
          </div>

          <div className="hero__right">
            {/* Live KPI ticker (shows after result) */}
            {result && (
              <div className="hero__ticker">
                <span className="ticker__item">
                  <DollarSign className="w-3.5 h-3.5" />
                  {fmtCurrency(kpis.total_revenue)}
                </span>
                <span className="ticker__sep">·</span>
                <span className="ticker__item">
                  <ShoppingBag className="w-3.5 h-3.5" />
                  {fmtNumber(kpis.total_orders)} orders
                </span>
                <span className="ticker__sep">·</span>
                <span className="ticker__item">
                  <Users className="w-3.5 h-3.5" />
                  {fmtNumber(kpis.unique_customers)} customers
                </span>
              </div>
            )}
            <div className="hero__badge">
              <span className="hero__dot" />
              Engine Online
            </div>
          </div>
        </div>
      </header>

      {/* ── Main ──────────────────────────────────────────────────────── */}
      <main className="app-main">

        {/* Sidebar */}
        <aside className="sidebar">

          {/* Query panel */}
          <section className="card">
            <h2 className="card__title">
              <Sparkles className="w-4 h-4 text-accent" />
              Analysis Prompt
            </h2>
            <textarea
              id="analysis-query"
              value={query}
              onChange={e => setQuery(e.target.value)}
              rows={4}
              className="query-input"
              placeholder="Ask the agents to analyse sales, trends, or anomalies…"
            />

            {/* Prompt chips */}
            <div className="chip-grid">
              {PROMPT_CHIPS.map(c => (
                <button
                  key={c.label}
                  className="chip"
                  onClick={() => { setQuery(c.text); }}
                  title={c.text}
                >
                  {c.icon}
                  {c.label}
                </button>
              ))}
            </div>

            <div className="btn-row">
              <button
                id="run-analysis-btn"
                onClick={handleRunAnalysis}
                disabled={loading}
                className="btn btn--primary"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                {loading ? 'Agents Running…' : 'Execute Multi-Agent Analysis'}
              </button>
              {(hasResult || error) && (
                <button onClick={handleReset} className="btn btn--ghost btn--icon" title="Reset">
                  <RefreshCw className="w-4 h-4" />
                </button>
              )}
            </div>
          </section>

          {/* Agent pipeline */}
          <section className="card card--flex">
            <h2 className="card__title">
              <BarChart3 className="w-4 h-4 text-accent" />
              Agent Pipeline
              {loading && (
                <span className="pipeline-pct">{progressPct.toFixed(0)}%</span>
              )}
            </h2>
            {loading && (
              <div className="pipeline-bar">
                <div className="pipeline-bar__fill" style={{ width: `${progressPct}%` }} />
              </div>
            )}
            <div className="pipeline-log">
              {agentSteps.length === 0 && !loading && (
                <div className="pipeline-log__empty">
                  Run an analysis to observe LangGraph agent execution step-by-step.
                </div>
              )}
              {agentSteps.map((s, i) => <StepBadge key={i} step={s} />)}
              {loading && (
                <div className="step-badge step-badge--active">
                  <Loader2 className="step-badge__spin" />
                  <div>
                    <span className="step-badge__node">
                      {activeNode.replace(/_/g, ' ') || 'Initialising'}
                    </span>
                    <p className="step-badge__msg">Processing…</p>
                  </div>
                </div>
              )}
            </div>
          </section>
        </aside>

        {/* Dashboard */}
        <div className="dashboard">

          {error && (
            <div className="error-banner">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {(result?.warnings?.length ?? 0) > 0 && (
            <div className="warnings-banner">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <div>
                <strong>Pipeline Warnings:</strong>
                <ul className="warnings-list">
                  {result!.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            </div>
          )}

          {/* KPI Grid */}
          <div className="kpi-grid">
            <KPICard
              label="Total Revenue"
              value={fmtCurrency(kpis.total_revenue)}
              sub={kpis.date_start ? `${kpis.date_start} – ${kpis.date_end}` : undefined}
              icon={<DollarSign className="w-5 h-5" />}
              color="#a78bfa"  glow="rgba(167,139,250,0.25)"
              loading={loading}
            />
            <KPICard
              label="Total Orders"
              value={fmtNumber(kpis.total_orders)}
              icon={<ShoppingBag className="w-5 h-5" />}
              color="#38bdf8"  glow="rgba(56,189,248,0.25)"
              loading={loading}
            />
            <KPICard
              label="Avg. Order Value"
              value={fmtCurrency(kpis.average_order_value)}
              icon={<TrendingUp className="w-5 h-5" />}
              color="#34d399"  glow="rgba(52,211,153,0.25)"
              loading={loading}
            />
            <KPICard
              label="Unique Customers"
              value={fmtNumber(kpis.unique_customers)}
              icon={<Users className="w-5 h-5" />}
              color="#fbbf24"  glow="rgba(251,191,36,0.25)"
              loading={loading}
            />
          </div>

          {/* Chart Gallery */}
          {showCharts && <ChartGallery urls={chartUrls} loading={loading} />}

          {/* Executive Summary */}
          <section className="card">
            <h2 className="card__title">
              <FileText className="w-4 h-4 text-accent" />
              Executive Summary
            </h2>
            <div className="prose-box">
              {result?.report_summary
                ? result.report_summary
                : 'No analysis yet — click "Execute Multi-Agent Analysis" to begin.'}
            </div>
          </section>

          {/* Email + PDF */}
          <section className="card">
            <div className="card__row">
              <h2 className="card__title m-0">
                <Mail className="w-4 h-4 text-accent" />
                Email Summary Draft
              </h2>
              {hasPdf && (
                <a
                  id="download-pdf-btn"
                  href="http://127.0.0.1:8000/api/v1/download-pdf"
                  download="multi_agent_business_report.pdf"
                  className="btn btn--download"
                >
                  <Download className="w-3.5 h-3.5" />
                  Download PDF
                </a>
              )}
            </div>
            <pre className="email-pre">
              {result?.email_draft
                ? result.email_draft
                : 'Email draft will appear here after pipeline completes.'}
            </pre>
          </section>

        </div>
      </main>
    </div>
  );
}