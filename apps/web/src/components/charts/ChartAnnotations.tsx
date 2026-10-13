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
          {String(a.label)} · {String(a.price)} ×
        </button>
      ))}
    </details>
  );
}
