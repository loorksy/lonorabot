// biome-ignore-all lint/suspicious/noArrayIndexKey: Immutable scalar rows do not contain component state.
import type { VisualNode, VisualValue } from "@lonora/contracts";
import { useState } from "react";

/** Keep long result sets inside the answer until the owner asks for more. */
export function VisualTable({
  node,
  fieldId,
  rows,
  display,
  numeric,
  filter,
  onFilter,
  labels,
}: {
  node: VisualNode;
  fieldId: string;
  rows: Record<string, VisualValue>[];
  display: (value: VisualValue | undefined) => string;
  numeric: (value: VisualValue | undefined) => boolean;
  filter: string;
  onFilter: (value: string) => void;
  labels: { filter: string; more: string; less: string };
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? rows : rows.slice(0, 8);
  const fields = node.fields ?? [];
  const numericColumns = fields.map(
    (field) => rows.length > 0 && rows.every((row) => numeric(row[field.key])),
  );
  return (
    <section className="native-visual-node native-visual-table">
      {node.label && <div className="native-visual-label">{node.label}</div>}
      {node.filter_key && (
        <label className="native-visual-filter" htmlFor={`${fieldId}:filter`}>
          {labels.filter}
          <input
            id={`${fieldId}:filter`}
            value={filter}
            onChange={(event) => onFilter(event.target.value)}
          />
        </label>
      )}
      <section
        className="native-visual-table-scroll"
        // biome-ignore lint/a11y/noNoninteractiveTabindex: Keyboard users must be able to scroll wide tables.
        tabIndex={0}
        aria-label={node.label ?? labels.filter}
      >
        <table>
          <thead>
            <tr>
              {fields.map((field, index) => (
                <th scope="col" key={field.key} data-numeric={numericColumns[index] || undefined}>
                  {field.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, index) => (
              <tr key={index}>
                {fields.map((field) => (
                  <td key={field.key} data-numeric={numeric(row[field.key]) || undefined}>
                    <bdi>{display(row[field.key])}</bdi>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {rows.length > 8 && (
        <button
          type="button"
          className="native-visual-more"
          aria-expanded={expanded}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? labels.less : `${labels.more} (${rows.length})`}
        </button>
      )}
    </section>
  );
}
