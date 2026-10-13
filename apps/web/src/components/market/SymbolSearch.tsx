import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
export function SymbolSearch({
  symbols,
  value,
  onChange,
}: {
  symbols: string[];
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
        {symbols.map((symbol) => (
          <option key={symbol} value={symbol}>
            {symbol}
          </option>
        ))}
      </select>
    </label>
  );
}
