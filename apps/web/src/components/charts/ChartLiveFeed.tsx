import { Trans } from "@lingui/react/macro";
export function ChartLiveFeed({
  observedAt,
  live,
  onToggle,
}: {
  observedAt: string | null;
  live: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="row muted">
      <label className="check">
        <input type="checkbox" checked={live} onChange={onToggle} />
        <Trans>Refresh live candles</Trans>
      </label>
      {observedAt && <time>{new Date(observedAt).toLocaleTimeString()}</time>}
    </div>
  );
}
