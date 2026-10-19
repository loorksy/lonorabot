import { Trans } from "@lingui/react/macro";
import { errorCode } from "@lonora/core";
import { useCharts } from "../../hooks/useCharts";
import { userError } from "../../lib/user_error";
import { ChartAnnotations } from "./ChartAnnotations";
import { ChartIndicators } from "./ChartIndicators";
import { ChartLiveFeed } from "./ChartLiveFeed";
import { ChartToolbar } from "./ChartToolbar";
import { TradingChart } from "./TradingChart";

export function ChartWorkspace({
  accountId,
  symbol,
  initialChartId,
}: {
  accountId: string;
  symbol: string;
  initialChartId?: string;
}) {
  const workspace = useCharts(accountId, symbol, initialChartId);
  const { row, scene, loading, initializing, busy, error } = workspace;
  return (
    <section
      className="card chart-workspace"
      data-chart-id={row?.id}
      data-chart-scene-version={scene?.scene_version}
    >
      <h2 dir="ltr">{scene?.symbol ?? symbol}</h2>
      {workspace.rows.length > 0 && (
        <label>
          <Trans>Saved chart</Trans>
          <select
            value={row?.id ?? ""}
            disabled={busy}
            onChange={(event) => workspace.select(event.target.value)}
          >
            {workspace.rows.map((item) => (
              <option value={item.id} key={item.id}>
                {item.payload.symbol} · {item.payload.timeframe} · {item.id.slice(-8)}
              </option>
            ))}
          </select>
        </label>
      )}
      {!loading && !row && (
        <button type="button" disabled={busy} onClick={() => void workspace.create()}>
          <Trans>Open chart</Trans>
        </button>
      )}
      {row && (
        <ChartToolbar
          timeframe={row.payload.timeframe}
          disabled={busy}
          onChange={(timeframe) => void workspace.update({ ...row.payload, timeframe })}
          onRefresh={() => void workspace.refresh()}
        />
      )}
      {error != null && (
        <p role="alert" data-error-code={errorCode(error)}>
          {userError(error)} <code>{errorCode(error)}</code>
        </p>
      )}
      {(loading || initializing) && (
        <p role="status">
          <Trans>Loading chart…</Trans>
        </p>
      )}
      {scene && scene.candles.length > 0 ? (
        <TradingChart scene={scene} accountId={accountId} />
      ) : (
        row &&
        !loading &&
        !initializing &&
        error == null && (
          <div className="empty">
            <Trans>No candles available for this instrument and timeframe.</Trans>
          </div>
        )
      )}
      {row && (
        <details>
          <summary>
            <Trans>Indicators and drawings</Trans>
          </summary>
          <ChartIndicators
            disabled={busy}
            indicators={row.payload.indicators}
            onChange={(indicators) => void workspace.update({ ...row.payload, indicators })}
          />
          <ChartAnnotations
            disabled={busy}
            annotations={row.payload.annotations}
            onChange={(annotations) => void workspace.update({ ...row.payload, annotations })}
          />
        </details>
      )}
      {scene && (
        <ChartLiveFeed
          observedAt={scene.updated_at}
          status={scene.status}
          errorCode={scene.error_code}
        />
      )}
    </section>
  );
}
