import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import type { Resource } from "../../lib/api";
import { type ChartState, charts } from "../../lib/charts";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { ChartWorkspace } from "./ChartWorkspace";

/** The conversation side panel hosts real durable charts, never a simulated computer. */
export function ConversationCharts({
  agentId,
  threadId,
  onOpenMarket,
}: {
  agentId?: string;
  threadId?: string;
  onOpenMarket: () => void;
}) {
  const { events, connected } = useClient();
  const [rows, setRows] = useState<Resource<ChartState>[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>();
  const cursor =
    events.filter((event) => event.kind.startsWith("cloud_charts.")).at(-1)?.cursor ?? 0;
  useEffect(() => {
    void connected;
    void cursor;
    let live = true;
    void charts
      .list()
      .then((all) => {
        if (!live) return;
        const matching = all.filter(
          (row) =>
            (!row.agent_id && !row.thread_id) ||
            (agentId && row.agent_id === agentId) ||
            (threadId && row.thread_id === threadId),
        );
        setRows(matching);
        setSelected((id) => (matching.some((row) => row.id === id) ? id : (matching[0]?.id ?? "")));
        setError(undefined);
      })
      .catch((caught: unknown) => {
        if (live) setError(caught);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [agentId, threadId, connected, cursor]);
  const row = rows.find((item) => item.id === selected);
  return (
    <div className="conversation-charts">
      {error != null && <p role="alert">{userError(error)}</p>}
      {loading && (
        <p role="status">
          <Trans>Loading chart…</Trans>
        </p>
      )}
      {rows.length > 1 && (
        <label>
          <Trans>Saved chart</Trans>
          <select value={selected} onChange={(event) => setSelected(event.target.value)}>
            {rows.map((item) => (
              <option key={item.id} value={item.id}>
                {item.payload.symbol} · {item.payload.timeframe}
              </option>
            ))}
          </select>
        </label>
      )}
      {row ? (
        <ChartWorkspace
          key={row.id}
          initialChartId={row.id}
          accountId={row.payload.account_id}
          symbol={row.payload.symbol}
        />
      ) : (
        !loading &&
        error == null && (
          <div className="workspace-empty">
            <p>
              <Trans>No saved chart in this conversation</Trans>
            </p>
            <button type="button" onClick={onOpenMarket}>
              <Trans>Market and charts</Trans>
            </button>
          </div>
        )
      )}
    </div>
  );
}
