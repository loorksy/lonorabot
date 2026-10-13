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
          {["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"].map((f) => (
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
