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
}: {
  node: VisualNode;
  points: Point[];
  unavailable: string;
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
        {points.map((point, index) => (
          <div key={index}>
            <dt>
              <span
                aria-hidden="true"
                className={`native-visual-key series-${node.chart_kind === "pie" ? index % 5 : 0}`}
              />
              {point.label}
            </dt>
            <dd>{point.value ?? unavailable}</dd>
          </div>
        ))}
      </dl>
    </figure>
  );
}

export function VisualDiagram({ node }: { node: VisualNode }) {
  const marker = useId().replace(/:/g, "");
  const vertices = node.vertices ?? [];
  const width = 600,
    slot = 84,
    height = Math.max(80, vertices.length * slot);
  return (
    <figure className="native-visual-graphic native-visual-diagram">
      {node.label && <figcaption>{node.label}</figcaption>}
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={node.label ?? "Diagram"}>
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
          const start = vertices.findIndex((vertex) => vertex.id === edge.source);
          const end = vertices.findIndex((vertex) => vertex.id === edge.target);
          const forward = end > start;
          const sy = start * slot + (forward ? 58 : 10),
            ey = end * slot + (forward ? 8 : 60);
          const curved = Math.abs(end - start) !== 1;
          return (
            <g key={index} className="native-visual-edge">
              <path
                d={curved ? `M430,${sy} C550,${sy} 550,${ey} 430,${ey}` : `M300,${sy} L300,${ey}`}
                markerEnd={`url(#${marker})`}
              />
              {edge.label && (
                <text
                  x={curved ? 535 : 310}
                  y={(sy + ey) / 2}
                  textAnchor={curved ? "end" : "start"}
                >
                  {edge.label}
                </text>
              )}
            </g>
          );
        })}
        {vertices.map((vertex, index) => (
          <g key={vertex.id} className="native-visual-vertex">
            <rect x="170" y={index * slot + 8} width="260" height="50" rx="10" />
            <text x="300" y={index * slot + 39} textAnchor="middle">
              {vertex.label}
            </text>
          </g>
        ))}
      </svg>
      <ol className="native-visual-accessible-structure">
        {vertices.map((vertex) => (
          <li key={vertex.id}>
            {vertex.label}
            {(node.edges ?? [])
              .filter((edge) => edge.source === vertex.id)
              .map((edge) => (
                <span key={`${edge.source}:${edge.target}`}>
                  {" "}
                  → {vertices.find((item) => item.id === edge.target)?.label}
                  {edge.label ? ` (${edge.label})` : ""}
                </span>
              ))}
          </li>
        ))}
      </ol>
    </figure>
  );
}
