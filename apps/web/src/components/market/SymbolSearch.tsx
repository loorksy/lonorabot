import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { Instrument } from "../../lib/api";
export function SymbolSearch({
  instruments,
  value,
  onChange,
}: {
  instruments: Instrument[];
  value: string;
  onChange: (symbol: string) => void;
}) {
  return (
    <label>
      <Trans>Broker symbol</Trans>
      <select
        dir="ltr"
        aria-label={t`Exact broker symbol`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{t`Choose an instrument`}</option>
        {instruments.map((i) => (
          <option key={i.symbol} value={i.symbol}>
            {i.symbol} · {i.description}
          </option>
        ))}
      </select>
    </label>
  );
}
