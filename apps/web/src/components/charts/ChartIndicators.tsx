import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import type { ChartState } from "../../lib/charts";
export function ChartIndicators({
  indicators,
  onChange,
}: {
  indicators: ChartState["indicators"];
  onChange: (items: ChartState["indicators"]) => void;
}) {
  const [name, setName] = useState("EMA");
  const [period, setPeriod] = useState(14);
  return (
    <details>
      <summary>
        <Trans>Indicators</Trans> ({indicators.length})
      </summary>
      <div className="inline-form">
        <label>
          <Trans>Indicator</Trans>
          <select value={name} onChange={(e) => setName(e.target.value)}>
            {["SMA", "EMA", "RSI", "BOLLINGER", "MACD", "ATR"].map((n) => (
              <option key={n} value={n}>
                {n}
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
        <button
          type="button"
          disabled={
            indicators.length >= 12 ||
            indicators.some((i) => i.name === name && i.period === period)
          }
          onClick={() => onChange([...indicators, { name, period }])}
        >
          <Trans>Add indicator</Trans>
        </button>
      </div>
      <div className="chips">
        {indicators.map((i, index) => (
          <button
            type="button"
            key={`${i.name}:${i.period}`}
            onClick={() => onChange(indicators.filter((_, n) => n !== index))}
          >
            {i.name} {i.period} ×
          </button>
        ))}
      </div>
    </details>
  );
}
