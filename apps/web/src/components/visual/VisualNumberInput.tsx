/** Keep an editable numeric draft separate from bounded calculator state.
 * Adapted from Open Intelligent UI Input's draft/commit pattern (MIT).
 */
import type { VisualNode, VisualScalar } from "@lonora/contracts";
import { parseVisualNumberDraft } from "@lonora/core";
import { useState } from "react";

export function VisualNumberInput({
  id,
  node,
  value,
  onChange,
}: {
  id: string;
  node: VisualNode;
  value: VisualScalar;
  onChange: (value: VisualScalar) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? (typeof value === "number" ? String(value) : "");
  return (
    <input
      id={id}
      type="text"
      role="spinbutton"
      inputMode="decimal"
      autoComplete="off"
      maxLength={2000}
      aria-valuemin={node.minimum ?? 0}
      aria-valuemax={node.maximum ?? 100}
      aria-valuenow={typeof value === "number" ? value : undefined}
      aria-valuetext={shown || undefined}
      value={shown}
      onChange={(event) => {
        const next = event.target.value;
        setDraft(next);
        const parsed = parseVisualNumberDraft(next);
        // Intermediate digits must not silently clamp the calculator while the
        // owner is still typing ("2" is the start of "250" for a minimum of 100).
        if (
          parsed === null ||
          (parsed !== undefined && parsed >= (node.minimum ?? 0) && parsed <= (node.maximum ?? 100))
        )
          onChange(parsed);
      }}
      onBlur={() => {
        if (draft !== null) {
          const parsed = parseVisualNumberDraft(draft);
          if (parsed !== undefined) onChange(parsed);
        }
        setDraft(null);
      }}
      onKeyDown={(event) => {
        if (event.nativeEvent.isComposing) return;
        if (event.key === "Escape") {
          setDraft(null);
          return;
        }
        if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
        event.preventDefault();
        const direction = event.key === "ArrowUp" ? 1 : -1;
        const next =
          (typeof value === "number" ? value : (node.minimum ?? 0)) + direction * (node.step ?? 1);
        onChange(Number(next.toPrecision(12)));
        setDraft(null);
      }}
    />
  );
}
