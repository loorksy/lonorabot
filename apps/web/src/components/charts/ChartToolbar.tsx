import { Trans } from "@lingui/react/macro";
export function ChartToolbar({
  timeframe,
  onChange,
  onRefresh,
}: {
  timeframe: string;
  onChange: (frame: string) => void;
  onRefresh: () => void;
}) {
  return (
    <div className="row">
      <label>
        <Trans>Timeframe</Trans>
        <select value={timeframe} onChange={(e) => onChange(e.target.value)}>
          {["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"].map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={onRefresh}>
        <Trans>Refresh chart</Trans>
      </button>
    </div>
  );
}
