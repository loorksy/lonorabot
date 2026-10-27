// biome-ignore-all lint/suspicious/noArrayIndexKey: Committed point and edge arrays are immutable scalar geometry without local item state.
/** Trusted SVG marks; model data never supplies SVG markup or attributes. */
import type { VisualNode } from "@lonora/contracts";
import { visual } from "@lonora/ui-tokens";
import { useId } from "react";

type Point = { label: string; value: number | null };

export function VisualChart({
  node,
  points,
  unavailable,
  formatValue = (value) => (value === null ? unavailable : String(value)),
  moreLabel,
}: {
  node: VisualNode;
  points: Point[];
  unavailable: string;
  formatValue?: (value: number | null) => string;
  moreLabel: string;
}) {
  const titleId = useId();
  const usable = points.filter(
    (point): point is { label: string; value: number } => point.value !== null,
  );
  if (!usable.length) return <p className="native-visual-muted">{unavailable}</p>;
  const width = 600,
    height = visual.chartHeight,
    inset = 24;
  const minimum = Math.min(0, ...usable.map((point) => point.value));
  const maximum = Math.max(1, ...usable.map((point) => point.value));
  const y = (value: number) =>
    height - inset - ((value - minimum) / (maximum - minimum)) * (height - inset * 2);
  const x = (index: number) =>
    inset + (index / Math.max(1, points.length - 1)) * (width - inset * 2);
  const total = usable.reduce((sum, point) => sum + Math.max(0, point.value), 0);
  let angle = -Math.PI / 2;
  return (
    <figure className="native-visual-graphic">
      {node.label && <figcaption id={titleId}>{node.label}</figcaption>}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={node.label ?? node.type}
        aria-labelledby={node.label ? titleId : undefined}
      >
        {node.chart_kind === "pie" ? (
          usable.map((point, index) => {
            const start = angle;
            angle += total ? (Math.max(0, point.value) / total) * Math.PI * 2 : 0;
            const radius = 85,
              cx = width / 2,
              cy = height / 2;
            const sx = cx + Math.cos(start) * radius,
              sy = cy + Math.sin(start) * radius;
            const ex = cx + Math.cos(angle) * radius,
              ey = cy + Math.sin(angle) * radius;
            return total && point.value > 0 ? (
              usable.length === 1 || Math.max(0, point.value) === total ? (
                <circle
                  key={index}
                  cx={cx}
                  cy={cy}
                  r={radius}
                  className={`native-visual-series series-${index % 5}`}
                />
              ) : (
                <path
                  key={index}
                  className={`native-visual-series series-${index % 5}`}
                  d={`M${cx},${cy} L${sx},${sy} A${radius},${radius} 0 ${angle - start > Math.PI ? 1 : 0} 1 ${ex},${ey} Z`}
                />
              )
            ) : null;
          })
        ) : (
          <>
            <line
              x1={inset}
              y1={y(0)}
              x2={width - inset}
              y2={y(0)}
              className="native-visual-axis"
            />
            {node.chart_kind === "bar" ? (
              points.map((point, index) => {
                if (point.value === null) return null;
                const slot = (width - inset * 2) / points.length;
                return (
                  <rect
                    key={index}
                    className="native-visual-series series-0"
                    x={inset + index * slot + slot * 0.15}
                    y={Math.min(y(0), y(point.value))}
                    width={Math.max(1, slot * 0.7)}
                    height={Math.max(1, Math.abs(y(point.value) - y(0)))}
                    rx="3"
                  />
                );
              })
            ) : (
              <>
                <path
                  d={points
                    .map((point, index) =>
                      point.value === null
                        ? ""
                        : `${index === 0 || points[index - 1].value === null ? "M" : "L"}${x(index)},${y(point.value)}`,
                    )
                    .join(" ")}
                  className="native-visual-chart-line"
                />
                {points.map((point, index) =>
                  point.value === null ? null : (
                    <circle
                      key={index}
                      cx={x(index)}
                      cy={y(point.value)}
                      r="3"
                      className="native-visual-series series-0"
                    />
                  ),
                )}
              </>
            )}
          </>
        )}
      </svg>
      <dl className="native-visual-chart-values">
        {points.slice(0, 8).map((point, index) => (
          <div key={index}>
            <dt>
              <span
                aria-hidden="true"
                className={`native-visual-key series-${node.chart_kind === "pie" ? index % 5 : 0}`}
              />
              {point.label}
            </dt>
            <dd>
              <bdi>{formatValue(point.value)}</bdi>
            </dd>
          </div>
        ))}
      </dl>
      {points.length > 8 && (
        <details className="native-visual-chart-more">
          <summary>
            {moreLabel} ({points.length})
          </summary>
          <dl className="native-visual-chart-values">
            {points.slice(8).map((point, index) => (
              <div key={index}>
                <dt>
                  <bdi>{point.label}</bdi>
                </dt>
                <dd>
                  <bdi>{formatValue(point.value)}</bdi>
                </dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </figure>
  );
}

/** Wrap labels instead of shrinking every node to unreadable text on a phone. */
function diagramLines(label: string): string[] {
  const parts = label.split(/(\s+)/);
  const lines: string[] = [];
  let line = "";
  for (const part of parts) {
    for (let offset = 0; offset < part.length; offset += 30) {
      const chunk = part.slice(offset, offset + 30);
      if (line.length + chunk.length > 30 && line.trim()) {
        lines.push(line.trim());
        line = "";
      }
      line += chunk;
    }
  }
  if (line.trim()) lines.push(line.trim());
  return lines.length ? lines : [""];
}

export function VisualDiagram({ node }: { node: VisualNode }) {
  const marker = useId().replace(/:/g, "");
  const vertices = node.vertices ?? [];
  let top = 8;
  const boxes = vertices.map((vertex) => {
    const lines = diagramLines(vertex.label);
    const height = Math.max(44, lines.length * 18 + 20);
    const box = { ...vertex, lines, top, height };
    top += height + 32;
    return box;
  });
  const height = Math.max(64, top);
  return (
    <figure className="native-visual-graphic native-visual-diagram">
      {node.label && <figcaption>{node.label}</figcaption>}
      <section
        className="native-visual-diagram-scroll"
        aria-label={node.label ?? "Diagram"}
        // biome-ignore lint/a11y/noNoninteractiveTabindex: Large diagrams remain scrollable with a keyboard.
        tabIndex={0}
      >
        <svg viewBox={`0 0 360 ${height}`} role="img" aria-label={node.label ?? "Diagram"}>
          <defs>
            <marker
              id={marker}
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
            </marker>
          </defs>
          {(node.edges ?? []).map((edge, index) => {
            const start = boxes.find((vertex) => vertex.id === edge.source);
            const end = boxes.find((vertex) => vertex.id === edge.target);
            if (!start || !end) return null;
            const forward = end.top > start.top;
            const sy = start.top + (forward ? start.height : 0);
            const ey = end.top + (forward ? 0 : end.height);
            const adjacent = Math.abs(boxes.indexOf(start) - boxes.indexOf(end)) === 1;
            return (
              <g key={index} className="native-visual-edge">
                <path
                  d={
                    adjacent ? `M180,${sy} L180,${ey}` : `M304,${sy} C350,${sy} 350,${ey} 304,${ey}`
                  }
                  markerEnd={`url(#${marker})`}
                />
                {edge.label && (
                  <text
                    x={adjacent ? 190 : 340}
                    y={(sy + ey) / 2}
                    textAnchor={adjacent ? "start" : "end"}
                  >
                    <title>{edge.label}</title>
                    {edge.label.length > 22 ? `${edge.label.slice(0, 21)}…` : edge.label}
                  </text>
                )}
              </g>
            );
          })}
          {boxes.map((vertex) => (
            <g key={vertex.id} className="native-visual-vertex">
              <rect x="56" y={vertex.top} width="248" height={vertex.height} rx="10" />
              <text x="180" y={vertex.top + 25} textAnchor="middle" direction="auto">
                {vertex.lines.map((line, index) => (
                  <tspan key={index} x="180" dy={index ? 18 : 0}>
                    {line}
                  </tspan>
                ))}
              </text>
            </g>
          ))}
        </svg>
      </section>
      <details className="native-visual-diagram-description">
        <summary>{node.label ?? "Diagram"}</summary>
        <ol>
          {vertices.map((vertex) => (
            <li key={vertex.id}>
              <bdi>{vertex.label}</bdi>
              {(node.edges ?? [])
                .filter((edge) => edge.source === vertex.id)
                .map((edge) => (
                  <div key={`${edge.source}:${edge.target}`}>
                    → <bdi>{vertices.find((item) => item.id === edge.target)?.label}</bdi>
                    {edge.label ? (
                      <>
                        {" "}
                        · <bdi>{edge.label}</bdi>
                      </>
                    ) : null}
                  </div>
                ))}
            </li>
          ))}
        </ol>
      </details>
    </figure>
  );
}
