import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import type { ChartState } from "../../lib/charts";
export function ChartAnnotations({
  annotations,
  onChange,
  disabled = false,
}: {
  annotations: ChartState["annotations"];
  disabled?: boolean;
  onChange: (items: ChartState["annotations"]) => void;
}) {
  const [price, setPrice] = useState("");
  const [label, setLabel] = useState("");
  return (
    <details>
      <summary>
        <Trans>Price annotations</Trans> ({annotations.length})
      </summary>
      <div className="inline-form">
        <label>
          <Trans>Price</Trans>
          <input
            type="number"
            step="any"
            min={0}
            value={price}
            onChange={(e) => setPrice(e.target.value)}
          />
        </label>
        <label>
          <Trans>Label</Trans>
          <input value={label} onChange={(e) => setLabel(e.target.value)} />
        </label>
        <button
          type="button"
          disabled={
            disabled ||
            !price ||
            !Number.isFinite(Number(price)) ||
            Number(price) <= 0 ||
            annotations.length >= 100
          }
          onClick={() => {
            onChange([
              ...annotations,
              { id: crypto.randomUUID(), type: "price", price: Number(price), label },
            ]);
            setPrice("");
          }}
        >
          <Trans>Add line</Trans>
        </button>
      </div>
      {annotations.map((a, i) => (
        <button
          disabled={disabled}
          type="button"
          key={String(a.id ?? JSON.stringify(a))}
          onClick={() => onChange(annotations.filter((_, n) => n !== i))}
        >
          {String(
            a.label ??
              a.text ??
              {
                price: t`Price level`,
                horizontal_line: t`Price level`,
                trend_line: t`Trend line`,
                note: t`Note`,
                price_zone: t`Price zone`,
                ray: t`Ray`,
                channel: t`Channel`,
                fibonacci: t`Fibonacci`,
                arrow: t`Arrow`,
                scenario: t`Scenario`,
              }[String(a.type)] ??
              a.type,
          )}
          {a.price != null && <span dir="ltr"> · {String(a.price)}</span>} ·{" "}
          {a.source === "agent" ? <Trans>Agent</Trans> : <Trans>You</Trans>} ×
        </button>
      ))}
    </details>
  );
}
