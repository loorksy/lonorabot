// biome-ignore-all lint/suspicious/noArrayIndexKey: Immutable server documents give stateless text, plot geometry and table rows positional identity.
import type { VisualDocument, VisualNode, VisualState } from "@lonora/contracts";
import { evaluateVisualValue } from "@lonora/core";
import { visual } from "@lonora/ui-tokens";
import { useState } from "react";
import { Text, View } from "react-native";
import Svg, {
  Circle,
  G,
  Line,
  Path,
  Polygon,
  Polyline,
  Rect,
  Text as SvgText,
} from "react-native-svg";
import { type NativeVisualPalette, visualTone } from "./native-rich-theme";

type Props = {
  node: VisualNode;
  document: VisualDocument;
  state: VisualState;
  palette: NativeVisualPalette;
  unavailable: string;
};

export function NativeVisualChart({ node, document, state, palette, unavailable }: Props) {
  const [width, setWidth] = useState(320);
  const points = (node.points ?? []).flatMap((point) => {
    const raw = evaluateVisualValue(point.value, document, state);
    const value =
      typeof raw === "number"
        ? raw
        : typeof raw === "string" && raw.trim()
          ? Number(raw)
          : Number.NaN;
    return Number.isFinite(value)
      ? [{ label: String(evaluateVisualValue(point.label, document, state) ?? ""), value }]
      : [];
  });
  if (!points.length)
    return <Text style={{ color: palette["muted-foreground"] }}>{unavailable}</Text>;
  const h = visual.chartHeight;
  const pad = 28;
  const chartWidth = Math.max(120, width - pad * 2);
  const color = visualTone(palette, node.tone === "neutral" ? "info" : (node.tone ?? "info"));
  const minimum = Math.min(0, ...points.map((point) => point.value));
  const maximum = Math.max(0, ...points.map((point) => point.value));
  const span = maximum - minimum || 1;
  const y = (value: number) => pad + (1 - (value - minimum) / span) * (h - pad * 2);
  const x = (index: number) =>
    pad + chartWidth * (points.length === 1 ? 0.5 : index / (points.length - 1));
  const segments = points.filter((point) => point.value > 0);
  const total = segments.reduce((sum, point) => sum + point.value, 0);
  const tones = [
    palette.link,
    palette.success,
    palette.warning,
    palette.foreground,
    palette["muted-foreground"],
  ];
  let previous = -Math.PI / 2;
  const pie = segments.map((point, index) => {
    const angle = (point.value / total) * Math.PI * 2;
    const next = previous + angle;
    const radius = Math.min(width, h) * 0.36;
    const cx = width / 2;
    const cy = h / 2;
    const first = [cx + radius * Math.cos(previous), cy + radius * Math.sin(previous)];
    const last = [cx + radius * Math.cos(next), cy + radius * Math.sin(next)];
    const d = `M ${cx} ${cy} L ${first[0]} ${first[1]} A ${radius} ${radius} 0 ${angle > Math.PI ? 1 : 0} 1 ${last[0]} ${last[1]} Z`;
    previous = next;
    return segments.length === 1 ? (
      <Circle
        key={point.label + index}
        cx={cx}
        cy={cy}
        r={radius}
        fill={tones[index % tones.length]}
      />
    ) : (
      <Path key={point.label + index} d={d} fill={tones[index % tones.length]} />
    );
  });
  const kind = node.chart_kind ?? "line";
  return (
    <View
      onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
      style={{ gap: visual.space.small }}
    >
      {node.label ? (
        <Text
          accessibilityRole="header"
          style={{ color: palette.foreground, fontSize: visual.font.label, fontWeight: "600" }}
        >
          {node.label}
        </Text>
      ) : null}
      {kind === "pie" && total <= 0 ? (
        <Text style={{ color: palette["muted-foreground"] }}>{unavailable}</Text>
      ) : (
        <Svg
          width="100%"
          height={h}
          viewBox={`0 0 ${width} ${h}`}
          accessibilityRole="image"
          accessibilityLabel={`${node.label ?? ""}. ${points.map((p) => `${p.label}: ${p.value}`).join(". ")}`}
        >
          {kind === "pie" ? (
            pie
          ) : (
            <>
              {[minimum, minimum + span / 2, maximum].map((value, index) => (
                <G key={index}>
                  <Line
                    x1={pad}
                    y1={y(value)}
                    x2={width - pad}
                    y2={y(value)}
                    stroke={palette.border}
                  />
                  <SvgText
                    x={pad}
                    y={y(value) - 5}
                    fill={palette["muted-foreground"]}
                    fontSize={visual.font.small}
                  >
                    {Number(value.toPrecision(5))}
                  </SvgText>
                </G>
              ))}
              {kind === "line" ? (
                <Polyline
                  points={points.map((point, index) => `${x(index)},${y(point.value)}`).join(" ")}
                  fill="none"
                  stroke={color}
                  strokeWidth={2}
                />
              ) : (
                points.map((point, index) => {
                  const barWidth = Math.max(1, (chartWidth / points.length) * 0.65);
                  const position = pad + (chartWidth * (index + 0.5)) / points.length;
                  return (
                    <Rect
                      key={point.label + index}
                      x={position - barWidth / 2}
                      y={Math.min(y(0), y(point.value))}
                      width={barWidth}
                      height={Math.max(1, Math.abs(y(0) - y(point.value)))}
                      fill={point.value < 0 ? palette.destructive : color}
                      rx={2}
                    />
                  );
                })
              )}
            </>
          )}
        </Svg>
      )}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: visual.space.normal }}>
        {points.map((point, index) => (
          <Text
            key={point.label + index}
            selectable
            style={{
              color: kind === "pie" ? tones[index % tones.length] : palette["muted-foreground"],
              fontSize: visual.font.small,
            }}
          >
            {point.label}: {point.value}
          </Text>
        ))}
      </View>
    </View>
  );
}

export function NativeVisualDiagram({
  node,
  palette,
  unavailable,
  rtl,
}: Pick<Props, "node" | "palette" | "unavailable"> & { rtl: boolean }) {
  const [width, setWidth] = useState(320);
  const vertices = node.vertices ?? [];
  if (!vertices.length)
    return <Text style={{ color: palette["muted-foreground"] }}>{unavailable}</Text>;
  const columns = width > 500 ? 3 : 2;
  const boxWidth = Math.max(100, (width - visual.space.normal * (columns + 1)) / columns);
  const boxHeight = 64;
  const rowHeight = boxHeight + visual.space.large * 2;
  const h = Math.ceil(vertices.length / columns) * rowHeight;
  const position = (id: string) => {
    const index = vertices.findIndex((vertex) => vertex.id === id);
    return {
      x:
        visual.space.normal +
        (rtl ? columns - 1 - (index % columns) : index % columns) *
          (boxWidth + visual.space.normal),
      y: visual.space.normal + Math.floor(index / columns) * rowHeight,
    };
  };
  return (
    <View
      onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
      style={{ gap: visual.space.small }}
    >
      {node.label ? (
        <Text style={{ color: palette.foreground, fontWeight: "600", fontSize: visual.font.label }}>
          {node.label}
        </Text>
      ) : null}
      <Svg
        width="100%"
        height={h}
        viewBox={`0 0 ${width} ${h}`}
        accessibilityRole="image"
        accessibilityLabel={`${node.label ?? ""}. ${vertices.map((vertex) => vertex.label).join(". ")}. ${(node.edges ?? []).map((edge) => `${vertices.find((v) => v.id === edge.source)?.label} → ${vertices.find((v) => v.id === edge.target)?.label}`).join(". ")}`}
      >
        {(node.edges ?? []).map((edge, index) => {
          const from = position(edge.source),
            to = position(edge.target);
          const sameRow = from.y === to.y;
          const forward = from.x < to.x;
          const down = from.y < to.y;
          const x1 = sameRow ? from.x + (forward ? boxWidth : 0) : from.x + boxWidth / 2;
          const y1 = sameRow ? from.y + boxHeight / 2 : from.y + (down ? boxHeight : 0);
          const x2 = sameRow ? to.x + (forward ? 0 : boxWidth) : to.x + boxWidth / 2;
          const y2 = sameRow ? to.y + boxHeight / 2 : to.y + (down ? 0 : boxHeight);
          const angle = Math.atan2(y2 - y1, x2 - x1);
          const arrow = `${x2},${y2} ${x2 - 7 * Math.cos(angle) + 4 * Math.sin(angle)},${y2 - 7 * Math.sin(angle) - 4 * Math.cos(angle)} ${x2 - 7 * Math.cos(angle) - 4 * Math.sin(angle)},${y2 - 7 * Math.sin(angle) + 4 * Math.cos(angle)}`;
          return (
            <G key={index}>
              <Line x1={x1} y1={y1} x2={x2} y2={y2} stroke={palette["muted-foreground"]} />
              <Polygon points={arrow} fill={palette["muted-foreground"]} />
              {edge.label ? (
                <SvgText
                  x={(x1 + x2) / 2 + 4}
                  y={(y1 + y2) / 2}
                  fill={palette["muted-foreground"]}
                  fontSize={visual.font.small}
                >
                  {edge.label.slice(0, 25)}
                </SvgText>
              ) : null}
            </G>
          );
        })}
        {vertices.map((vertex) => {
          const { x, y } = position(vertex.id);
          const lines = vertex.label.match(/.{1,20}/gu) ?? [vertex.label];
          return (
            <G key={vertex.id}>
              <Rect
                x={x}
                y={y}
                width={boxWidth}
                height={boxHeight}
                rx={visual.radius.normal}
                fill={palette.card}
                stroke={palette.border}
              />
              {lines.slice(0, 3).map((line, index) => (
                <SvgText
                  key={index}
                  x={x + boxWidth / 2}
                  y={y + 24 + index * 16}
                  textAnchor="middle"
                  fill={palette.foreground}
                  fontSize={visual.font.small}
                >
                  {line}
                </SvgText>
              ))}
            </G>
          );
        })}
      </Svg>
    </View>
  );
}
