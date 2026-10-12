import { Trans } from "@lingui/react/macro";
import { useEffect, useMemo, useState } from "react";
import type { Agent, Resource } from "../../lib/api";
import { resources } from "../../lib/rpc";
import { userError } from "../../lib/user_error";
import { AgentPicker } from "../../pages/shell/bot-picker";
import { useClient } from "../../providers/ClientProvider";
export function MarketWatch({
  accountId,
  symbol,
  agents,
}: {
  accountId: string;
  symbol: string;
  agents: Agent[];
}) {
  const { revision, refresh } = useClient();
  const [rows, setRows] = useState<Resource[]>([]);
  const [agent, setAgent] = useState(agents[0]?.id ?? "");
  const [kind, setKind] = useState("price");
  const [metric, setMetric] = useState("equity");
  const [indicator, setIndicator] = useState("rsi");
  const [period, setPeriod] = useState(14);
  const [timeframe, setTimeframe] = useState("1h");
  const [positionId, setPositionId] = useState("");
  const [integrationId, setIntegrationId] = useState("");
  const [calendarSources, setCalendarSources] = useState<Resource[]>([]);
  const [condition, setCondition] = useState("cross_above");
  const [level, setLevel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState<unknown>();
  const service = useMemo(() => resources("/watches"), []);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    void service.list().then(setRows).catch(setError);
  }, [revision, service]);
  useEffect(() => {
    void resources("/integrations")
      .list()
      .then((rows) =>
        setCalendarSources(rows.filter((row) => row.payload.type === "economic_calendar")),
      )
      .catch(setError);
  }, []);
  return (
    <details className="card">
      <summary>
        <Trans>Market watches</Trans>
      </summary>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await service.create(
              {
                kind,
                metric,
                indicator,
                period,
                timeframe,
                position_id: positionId || null,
                integration_id: integrationId || null,
                account_id: accountId,
                symbol,
                condition,
                level: level || "0",
                prompt,
                enabled: true,
                cooldown_seconds: 300,
                interval_seconds: 30,
              },
              agent,
            );
            refresh();
            setPrompt("");
          } catch (err) {
            setError(err);
          }
        }}
      >
        <label>
          <Trans>Watch source</Trans>
          <select
            value={kind}
            onChange={(e) => {
              const next = e.target.value;
              setKind(next);
              setCondition(
                next === "calendar"
                  ? "due"
                  : next === "position"
                    ? "closed"
                    : next === "account"
                      ? "changed"
                      : "cross_above",
              );
              setMetric(next === "position" ? "profit" : "equity");
            }}
          >
            <option value="price">
              <Trans>Price</Trans>
            </option>
            <option value="indicator">
              <Trans>Indicator</Trans>
            </option>
            <option value="position">
              <Trans>Position</Trans>
            </option>
            <option value="account">
              <Trans>Account changes</Trans>
            </option>
            <option value="calendar">
              <Trans>Economic calendar</Trans>
            </option>
          </select>
        </label>
        {kind === "indicator" && (
          <div className="form-grid">
            <label>
              <Trans>Indicator</Trans>
              <select value={indicator} onChange={(e) => setIndicator(e.target.value)}>
                {["sma", "ema", "rsi", "macd", "atr", "bollinger"].map((name) => (
                  <option key={name} value={name}>
                    {name.toUpperCase()}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <Trans>Period</Trans>
              <input
                type="number"
                min={2}
                max={500}
                value={period}
                onChange={(e) => setPeriod(Number(e.target.value))}
              />
            </label>
            <label>
              <Trans>Timeframe</Trans>
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                {["1m", "5m", "15m", "1h", "4h", "1d"].map((frame) => (
                  <option key={frame}>{frame}</option>
                ))}
              </select>
            </label>
          </div>
        )}
        {kind === "position" && (
          <label>
            <Trans>Position ID</Trans>
            <input
              value={positionId}
              required
              dir="ltr"
              onChange={(e) => setPositionId(e.target.value)}
            />
          </label>
        )}
        {(kind === "account" || kind === "position") && (
          <label>
            <Trans>Metric</Trans>
            <select value={metric} onChange={(e) => setMetric(e.target.value)}>
              {kind === "account" ? (
                <>
                  <option value="equity">
                    <Trans>Equity</Trans>
                  </option>
                  <option value="balance">
                    <Trans>Balance</Trans>
                  </option>
                  <option value="margin">
                    <Trans>Margin</Trans>
                  </option>
                  <option value="free_margin">
                    <Trans>Free margin</Trans>
                  </option>
                </>
              ) : (
                <>
                  <option value="profit">
                    <Trans>Profit</Trans>
                  </option>
                  <option value="volume">
                    <Trans>Volume</Trans>
                  </option>
                </>
              )}
            </select>
          </label>
        )}
        {kind === "calendar" && (
          <label>
            <Trans>Economic calendar feed</Trans>
            <select
              required
              value={integrationId}
              onChange={(e) => setIntegrationId(e.target.value)}
            >
              <option value="">
                <Trans>Choose a feed</Trans>
              </option>
              {calendarSources.map((row) => (
                <option key={row.id} value={row.id}>
                  {String(row.payload.name)}
                </option>
              ))}
            </select>
          </label>
        )}
        <AgentPicker agents={agents} value={agent} onChange={setAgent} />
        <label>
          <Trans>Condition</Trans>
          <select value={condition} onChange={(e) => setCondition(e.target.value)}>
            {kind === "calendar" && (
              <option value="due">
                <Trans>Event is due</Trans>
              </option>
            )}
            {(kind === "account" || kind === "position") && (
              <option value="changed">
                <Trans>Changes</Trans>
              </option>
            )}
            {kind === "position" && (
              <>
                <option value="closed">
                  <Trans>Closes</Trans>
                </option>
                <option value="opened">
                  <Trans>Opens</Trans>
                </option>
              </>
            )}
            <option value="cross_above">
              <Trans>Crosses above</Trans>
            </option>
            <option value="cross_below">
              <Trans>Crosses below</Trans>
            </option>
            <option value="above">
              <Trans>Above</Trans>
            </option>
            <option value="below">
              <Trans>Below</Trans>
            </option>
          </select>
        </label>
        <label>
          <Trans>Price level</Trans>
          <input
            required={["above", "below", "cross_above", "cross_below"].includes(condition)}
            dir="ltr"
            type="number"
            step="any"
            min={kind === "price" ? "0.00000001" : undefined}
            value={level}
            onChange={(e) => setLevel(e.target.value)}
          />
        </label>
        <label>
          <Trans>Task when triggered</Trans>
          <textarea required value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        </label>
        <button
          type="submit"
          disabled={
            !agent ||
            (kind !== "calendar" && !accountId) ||
            (["price", "indicator"].includes(kind) && !symbol) ||
            (kind === "position" && !positionId) ||
            (kind === "calendar" && !integrationId)
          }
        >
          <Trans>Create watch</Trans>
        </button>
      </form>
      {error != null && <p role="alert">{userError(error)}</p>}
      {rows.map((w) => (
        <div className="row" key={w.id}>
          <bdi>
            {String(w.payload.symbol)} · {String(w.payload.level)}
          </bdi>
          <button
            type="button"
            onClick={() =>
              void service
                .update(w, { ...w.payload, enabled: !w.payload.enabled })
                .then(refresh)
                .catch(setError)
            }
          >
            {w.payload.enabled ? <Trans>Pause</Trans> : <Trans>Resume</Trans>}
          </button>
          <button
            type="button"
            className="danger"
            onClick={() => void service.delete(w.id).then(refresh).catch(setError)}
          >
            <Trans>Delete</Trans>
          </button>
        </div>
      ))}
    </details>
  );
}
