import { t } from "@lingui/core/macro";
import { useLingui } from "@lingui/react";
import { Trans } from "@lingui/react/macro";
import type {
  UsageFigures,
  UsagePeriod,
  UsagePoint,
  UsageRank,
  UsageSeries,
} from "@lonora/contracts";
import { Icon } from "@lonora/ui-web";
import { type KeyboardEvent, type PointerEvent, type ReactNode, useRef, useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { useNavigation } from "../navigation";
import { useLoad } from "./ui";

/* «الاستهلاك» (usagePage 8986-9000 and its helpers 8945-9020), bound to WP-I (GET /usage/series,
   /usage/rank, /usage/export.csv). No spend cap (D4, Q22): the budget card shows month-to-date
   usage and its projection, never a limit; nothing here blocks a request. */

const usd = (value: number | null | undefined) => {
  const v = value ?? 0;
  return `$${
    v >= 1000
      ? Math.round(v).toLocaleString("en")
      : v >= 100
        ? v.toFixed(0)
        : v >= 0.1 || !v
          ? v.toFixed(2)
          : v >= 0.01
            ? v.toFixed(3)
            : Math.max(v, 1e-4).toFixed(4)
  }`;
};
const num = (v: number) =>
  v < 1e4
    ? Math.round(v).toLocaleString("en")
    : new Intl.NumberFormat("en", {
        notation: "compact",
        maximumFractionDigits: v >= 1e6 ? 2 : v >= 1e5 ? 0 : 1,
      }).format(v);
function nice(v: number) {
  if (!(v > 0)) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const f = v / p;
  return ([1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((n) => f <= n + 1e-9) ?? 10) * p;
}
function tick(v: number) {
  if (!v) return "$0";
  let d = 0;
  while (d < 6 && Math.abs(+v.toFixed(d) - v) > v * 1e-6) d++;
  if (d === 1) d = 2;
  return `$${v.toFixed(d)}`;
}

function Delta({ current, previous }: { current: number; previous: number }) {
  if (!(previous > 0)) return null;
  const change = (current - previous) / previous;
  const pct = Math.round(Math.abs(change) * 100);
  if (pct < 1)
    return (
      <span className="u-delta d-flat">
        <Icon name="minus" />
        <span>
          <Trans>No change</Trans>
        </span>
      </span>
    );
  return (
    <span
      className={`u-delta ${change > 0 ? "d-up" : "d-down"}`}
      role="img"
      aria-label={change > 0 ? t`Up ${pct}%` : t`Down ${pct}%`}
    >
      <Icon name={change > 0 ? "arrowUp" : "arrowDown"} />
      <span className="ltr">{pct}%</span>
    </span>
  );
}

const periods = (): [UsagePeriod, string, string, string][] => [
  ["day", t`Today`, t`today so far`, t`the same time yesterday`],
  ["week", t`7 days`, t`the last 7 days`, t`the previous seven days`],
  ["month", t`30 days`, t`the last 30 days`, t`the previous thirty days`],
];

function PeriodFilter({
  period,
  onChange,
}: {
  period: UsagePeriod;
  onChange: (p: UsagePeriod) => void;
}) {
  return (
    <div className="tabs u-period" role="tablist" aria-label={t`Period`}>
      {periods().map(([value, label]) => (
        <button
          key={value}
          type="button"
          role="tab"
          aria-selected={period === value}
          className={period === value ? "active" : ""}
          onClick={() => onChange(value)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Hero({ series, lead }: { series: UsageSeries; lead?: ReactNode }) {
  const [, , window, compare] =
    periods().find(([value]) => value === series.period) ?? periods()[2];
  return (
    <section className="card u-hero">
      {lead}
      <div className="u-eyebrow">
        <Trans>Cost · {window}</Trans>
      </div>
      <div className="u-hero-row">
        <span className="u-figure ltr">{usd(series.totals.cost_usd)}</span>
        <Delta current={series.totals.cost_usd} previous={series.previous.cost_usd} />
      </div>
      <div className="u-sub">
        <Trans>
          Compared with {compare} · <span className="ltr">{usd(series.previous.cost_usd)}</span>
        </Trans>
      </div>
    </section>
  );
}

/** The month card: month-to-date spend and its projection. No limit exists (D4). */
function MonthCard({ series, locale }: { series: UsageSeries; locale: string }) {
  const start = new Date(series.month.start);
  const month = start.toLocaleDateString(`${locale}-u-nu-latn`, {
    month: "long",
    timeZone: series.timezone,
  });
  // The month's last day from its calendar parts in the owner's zone: adding days to an
  // instant drifts across a DST change.
  const parts = new Intl.DateTimeFormat("en", {
    year: "numeric",
    month: "numeric",
    timeZone: series.timezone,
  }).formatToParts(start);
  const part = (type: string) => Number(parts.find((item) => item.type === type)?.value);
  const end = new Date(Date.UTC(part("year"), part("month") - 1, series.month.days_in_month, 12));
  const endText = end.toLocaleDateString(`${locale}-u-nu-latn`, {
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
  const fraction = series.month.day_of_month / series.month.days_in_month;
  return (
    <section className="card u-budget">
      <div className="u-card-head">
        <div>
          <div className="u-eyebrow">
            <Trans>{month} so far</Trans>
          </div>
          <div className="u-budget-fig">
            <strong className="ltr">{usd(series.month.spent_usd)}</strong>
            <span>
              <Trans>
                projected <span className="ltr">{usd(series.month.projected_usd)}</span>
              </Trans>
            </span>
          </div>
        </div>
      </div>
      {/* biome-ignore lint/a11y/useSemanticElements: the reference's styled meter */}
      <div
        className="u-meter ok"
        role="meter"
        aria-label={t`Days of ${month} elapsed`}
        aria-valuemin={0}
        aria-valuemax={series.month.days_in_month}
        aria-valuenow={series.month.day_of_month}
        style={{ "--p": `${(fraction * 100).toFixed(1)}%`, "--q": "100%" } as React.CSSProperties}
      >
        <i />
      </div>
      <div className="u-meter-legend">
        <span>
          <Trans>
            Day {series.month.day_of_month} of {series.month.days_in_month}
          </Trans>
        </span>
        <span>
          <Trans>
            Projected to {endText} <span className="ltr">{usd(series.month.projected_usd)}</span>
          </Trans>
        </span>
      </div>
      <div className="u-status good">
        <Icon name="check" />
        <span>
          <Trans>No spending cap: usage never stops a request.</Trans>
        </span>
      </div>
    </section>
  );
}

function Chart({ series, locale }: { series: UsageSeries; locale: string }) {
  const points = series.points;
  const last = points.reduce((at, point, index) => (point.cost_usd != null ? index : at), 0);
  const [selected, setSelected] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const scrub = useRef<number | null>(null);
  const bars = useRef<HTMLDivElement>(null);
  const sel = selected != null && selected <= last ? selected : last;
  const top = 2 * nice((Math.max(...points.map((p) => p.cost_usd ?? 0)) * 1.08) / 2);
  const date = (point: UsagePoint, options: Intl.DateTimeFormatOptions) =>
    new Date(point.start).toLocaleDateString(`${locale}-u-nu-latn`, {
      ...options,
      timeZone: series.timezone,
    });
  const hour = (point: UsagePoint) =>
    new Date(point.start).toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: series.timezone,
    });
  const label = (point: UsagePoint, index: number) =>
    series.bucket === "hour"
      ? `${hour(point)}${index === last ? ` · ${t`now`}` : ""}`
      : `${index === points.length - 1 ? `${t`Today`} · ` : index === points.length - 2 ? `${t`Yesterday`} · ` : ""}${date(point, { weekday: "long", day: "numeric", month: "long" })}`;
  const at = (x: number) => {
    const slots = bars.current?.children;
    if (!slots) return sel;
    let best = 0;
    let distance = Number.POSITIVE_INFINITY;
    [...slots].forEach((slot, index) => {
      const box = slot.getBoundingClientRect();
      const d = x < box.left ? box.left - x : x > box.right ? x - box.right : 0;
      if (d < distance) {
        distance = d;
        best = index;
      }
    });
    return Math.min(best, last);
  };
  const pick = (index: number) => setSelected(Math.max(0, Math.min(last, index)));
  const keys = (event: KeyboardEvent<HTMLDivElement>) => {
    const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
    let index = sel;
    if (event.key === "ArrowLeft") index += rtl ? 1 : -1;
    else if (event.key === "ArrowRight") index += rtl ? -1 : 1;
    else if (event.key === "Home") index = 0;
    else if (event.key === "End") index = last;
    else return;
    event.preventDefault();
    pick(index);
  };
  const head = (
    <div className="u-card-head">
      <div className="u-readout" aria-live="polite">
        <strong className="u-r-value ltr">{usd(points[sel]?.cost_usd)}</strong>
        <span className="u-r-label">{points[sel] ? label(points[sel], sel) : ""}</span>
      </div>
      <button
        type="button"
        className="icon u-view"
        aria-pressed={table}
        aria-label={table ? t`Show as a chart` : t`Show as a table`}
        onClick={() => setTable(!table)}
      >
        <Icon name={table ? "chart" : "table"} />
      </button>
    </div>
  );
  if (table)
    return (
      <section className="card u-chart">
        {head}
        <div className="u-table-wrap">
          <table className="u-table">
            <thead>
              <tr>
                <th scope="col">{series.bucket === "hour" ? t`Hour` : t`Day`}</th>
                <th scope="col">
                  <Trans>Cost</Trans>
                </th>
                <th scope="col">
                  <Trans>Tokens</Trans>
                </th>
              </tr>
            </thead>
            <tbody>
              {points
                .map((point, index) => [point, index] as const)
                .filter(([point]) => point.cost_usd != null)
                .reverse()
                .map(([point, index]) => (
                  <tr key={point.start}>
                    <th scope="row">{label(point, index)}</th>
                    <td className="ltr">{usd(point.cost_usd)}</td>
                    <td className="ltr">{num(point.tokens ?? 0)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>
    );
  const axis =
    series.bucket === "hour"
      ? ["00:00", "12:00", "23:00"]
      : [
          date(points[0], { day: "numeric", month: "long" }),
          date(points[Math.floor((points.length - 1) / 2)], { day: "numeric", month: "long" }),
          t`Today`,
        ];
  return (
    <section className="card u-chart">
      {head}
      <div className="u-plot">
        <div className="u-yaxis" aria-hidden="true">
          <span style={{ top: 0 }}>{tick(top)}</span>
          <span style={{ top: "50%" }}>{tick(top / 2)}</span>
          <span style={{ top: "100%" }}>$0</span>
        </div>
        <div className="u-area">
          <div className="u-grid" aria-hidden="true">
            <i style={{ top: 0 }} />
            <i style={{ top: "50%" }} />
            <i className="base" style={{ top: "100%" }} />
          </div>
          {/* biome-ignore lint/a11y/useSemanticElements: the reference's column group */}
          <div
            ref={bars}
            className="u-bars"
            // biome-ignore lint/a11y/noNoninteractiveTabindex: the reference's arrow-key readout
            tabIndex={0}
            role="group"
            aria-label={`${series.bucket === "hour" ? t`Cost per hour today` : t`Daily cost`}. ${t`Use the arrows to move between the columns.`}`}
            onKeyDown={keys}
            onPointerDown={(event: PointerEvent<HTMLDivElement>) => {
              scrub.current = event.pointerId;
              pick(at(event.clientX));
            }}
            onPointerMove={(event: PointerEvent<HTMLDivElement>) => {
              if (scrub.current === event.pointerId || event.pointerType === "mouse")
                pick(at(event.clientX));
            }}
            onPointerUp={() => {
              scrub.current = null;
            }}
            onPointerCancel={() => {
              scrub.current = null;
            }}
          >
            {points.map((point, index) => (
              <span
                key={point.start}
                className={`u-slot${index === sel ? " on" : ""}${point.cost_usd == null ? " future" : ""}`}
                style={
                  {
                    "--h": `${point.cost_usd == null ? 0 : Math.max(0.8, (point.cost_usd / top) * 100).toFixed(2)}%`,
                  } as React.CSSProperties
                }
              >
                <i />
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="u-xaxis" aria-hidden="true">
        {axis.map((text) => (
          <span key={text}>{text}</span>
        ))}
      </div>
    </section>
  );
}

function Kpis({ totals }: { totals: UsageFigures }) {
  const input = totals.tokens ? Math.round((totals.input_tokens / totals.tokens) * 100) : 0;
  const cached = totals.input_tokens
    ? Math.round((totals.cached_tokens / totals.input_tokens) * 100)
    : 0;
  const perRequest = totals.requests ? Math.round(totals.tokens / totals.requests) : 0;
  const priced = totals.requests - totals.unpriced_requests;
  return (
    <div className="u-kpis">
      <div className="u-kpi">
        <span className="u-k-label">
          <Trans>Tokens</Trans>
        </span>
        <strong className="ltr">{num(totals.tokens)}</strong>
        <span className="u-split" aria-hidden="true">
          <i style={{ width: `${input}%` }} />
          <i />
        </span>
        <small>
          <Trans>
            Input {input}% · output {100 - input}%
          </Trans>
        </small>
      </div>
      <div className="u-kpi">
        <span className="u-k-label">
          <Trans>Requests</Trans>
        </span>
        <strong className="ltr">{num(totals.requests)}</strong>
        <small>
          <Trans>About {perRequest} tokens per request</Trans>
        </small>
      </div>
      <div className="u-kpi">
        <span className="u-k-label">
          <Trans>From the cache</Trans>
        </span>
        <strong className="ltr">{cached}%</strong>
        <small>
          <Trans>
            <span className="ltr">{num(totals.cached_tokens)}</span> tokens reused
          </Trans>
        </small>
      </div>
      <div className="u-kpi">
        <span className="u-k-label">
          <Trans>Average cost per request</Trans>
        </span>
        <strong className="ltr">{usd(priced > 0 ? totals.cost_usd / priced : 0)}</strong>
        <small>
          {totals.unpriced_requests ? (
            <Trans>{totals.unpriced_requests} requests have no list price</Trans>
          ) : (
            <Trans>Per completed request</Trans>
          )}
        </small>
      </div>
    </div>
  );
}

type RankRow = { key: string; name: string; value: number; lead: ReactNode; to?: string };
function Ranked({
  title,
  rows,
  total,
  note,
}: {
  title: string;
  rows: RankRow[];
  total: number;
  note?: string;
}) {
  const nav = useNavigation();
  return (
    <section className="card u-rank">
      <div className="u-card-head">
        <h3>{title}</h3>
        {note && <span className="u-eyebrow">{note}</span>}
      </div>
      {rows.length === 0 && (
        <p className="pad muted small">
          <Trans>No usage in this period.</Trans>
        </p>
      )}
      {rows.map((row) => {
        const pct = total ? (row.value / total) * 100 : 0;
        const inner = (
          <>
            {row.lead}
            <span className="u-rank-body">
              <span className="u-rank-top">
                <strong>
                  <bdi>{row.name}</bdi>
                </strong>
                <span className="ltr">{usd(row.value)}</span>
              </span>
              <span className="u-rank-bar" aria-hidden="true">
                <i style={{ width: `${Math.max(0.6, pct).toFixed(1)}%` }} />
              </span>
            </span>
            <span className="u-rank-pct ltr">{pct > 0 && pct < 1 ? "<1" : Math.round(pct)}%</span>
            {row.to && (
              <span className="chevron">
                <Icon name="chev" />
              </span>
            )}
          </>
        );
        return row.to ? (
          <button
            type="button"
            className="u-rank-row"
            key={row.key}
            onClick={() => row.to && nav.go(row.to)}
          >
            {inner}
          </button>
        ) : (
          <div className="u-rank-row" key={row.key}>
            {inner}
          </div>
        );
      })}
    </section>
  );
}

function useUsage(period: UsagePeriod, agentId?: string) {
  const query = `period=${period}${agentId ? `&agent_id=${encodeURIComponent(agentId)}` : ""}`;
  const series = useLoad(() => api.get<UsageSeries>(`/usage/series?${query}`), [query]);
  const rank = useLoad(() => api.get<UsageRank>(`/usage/rank?${query}`), [query]);
  return { series, rank, csv: `/api/usage/export.csv?${query}` };
}

function Actions({ csv }: { csv: string }) {
  return (
    <div className="u-actions">
      <a className="btn outline" href={csv} download>
        <Trans>Export CSV</Trans>
      </a>
    </div>
  );
}

const modelIcon = (
  <span className="u-ico">
    <Icon name="cpu" />
  </span>
);

export function UsagePage() {
  const { i18n } = useLingui();
  const data = useShellData();
  const [period, setPeriod] = useState<UsagePeriod>("month");
  const { series, rank, csv } = useUsage(period);
  const error = series.error ?? rank.error;
  return (
    <>
      <PeriodFilter period={period} onChange={setPeriod} />
      {error != null && (
        <p className="note" role="alert">
          {userError(error)}
        </p>
      )}
      {series.value && (
        <>
          <Hero series={series.value} />
          <MonthCard series={series.value} locale={i18n.locale} />
          <Chart key={`${period}`} series={series.value} locale={i18n.locale} />
          <Kpis totals={series.value.totals} />
        </>
      )}
      {rank.value && (
        <>
          <Ranked
            title={t`By agent`}
            note={t`of the total cost`}
            total={rank.value.totals.cost_usd}
            rows={rank.value.agents.map((row) => {
              const agent = data.agents.find((item) => item.id === row.agent_id);
              return {
                key: row.agent_id ?? "none",
                name: row.agent_name ?? t`Lonora`,
                value: row.cost_usd,
                lead: agent ? <AgentAvatar agent={agent} /> : modelIcon,
                to: row.agent_id ? `/app/usage-detail/${row.agent_id}` : undefined,
              };
            })}
          />
          <Ranked
            title={t`By model`}
            total={rank.value.totals.cost_usd}
            rows={rank.value.models.map((row) => ({
              key: `${row.provider}/${row.model}`,
              name: row.model,
              value: row.cost_usd ?? 0,
              lead: modelIcon,
            }))}
          />
        </>
      )}
      <Actions csv={csv} />
    </>
  );
}

export function UsageDetailPage({ agentId }: { agentId: string }) {
  const { i18n } = useLingui();
  const data = useShellData();
  const [period, setPeriod] = useState<UsagePeriod>("month");
  const { series, rank, csv } = useUsage(period, agentId);
  const all = useLoad(() => api.get<UsageSeries>(`/usage/series?period=${period}`), [period]);
  const agent = data.agents.find((item) => item.id === agentId);
  const share =
    series.value && all.value?.totals.cost_usd
      ? Math.round((series.value.totals.cost_usd / all.value.totals.cost_usd) * 100)
      : 0;
  const lead = agent ? (
    <div className="u-agent">
      <AgentAvatar agent={agent} />
      <span>
        <strong>
          <bdi>{agent.name}</bdi>
        </strong>
        {agent.title && <small>{agent.title}</small>}
      </span>
      <span className="u-share">
        <Trans>
          <span className="ltr">{share}%</span> of the total
        </Trans>
      </span>
    </div>
  ) : null;
  const error = series.error ?? rank.error;
  return (
    <>
      <PeriodFilter period={period} onChange={setPeriod} />
      {error != null && (
        <p className="note" role="alert">
          {userError(error)}
        </p>
      )}
      {series.value && (
        <>
          <Hero series={series.value} lead={lead} />
          <Chart key={period} series={series.value} locale={i18n.locale} />
          <Kpis totals={series.value.totals} />
        </>
      )}
      {rank.value && (
        <Ranked
          title={t`Usage breakdown`}
          total={rank.value.totals.cost_usd}
          rows={rank.value.models.map((row) => ({
            key: `${row.provider}/${row.model}`,
            name: row.model,
            value: row.cost_usd ?? 0,
            lead: modelIcon,
          }))}
        />
      )}
      <Actions csv={csv} />
    </>
  );
}
