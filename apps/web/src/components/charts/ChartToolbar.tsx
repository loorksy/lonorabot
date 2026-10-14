import { Trans } from "@lingui/react/macro";
export function ChartToolbar({
  timeframe,
  disabled = false,
  onChange,
  onRefresh,
}: {
  timeframe: string;
  disabled?: boolean;
  onChange: (frame: string) => void;
  onRefresh: () => void;
}) {
  return (
    <div className="row">
      <label>
        <Trans>Timeframe</Trans>
        <select disabled={disabled} value={timeframe} onChange={(e) => onChange(e.target.value)}>
          {[
            "1m",
            "2m",
            "3m",
            "4m",
            "5m",
            "6m",
            "10m",
            "12m",
            "15m",
            "20m",
            "30m",
            "1h",
            "2h",
            "3h",
            "4h",
            "6h",
            "8h",
            "12h",
            "1d",
            "1w",
            "1mn",
          ].map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </label>
      <button disabled={disabled} type="button" onClick={onRefresh}>
        <Trans>Refresh chart</Trans>
      </button>
    </div>
  );
}
