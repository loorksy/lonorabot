import { useState } from "react";
import { Text, View } from "react-native";
import Svg, { G, Line, Polyline, Rect, Text as SvgText } from "react-native-svg";
import type { ChartScene } from "../lib/charts";
import { useSession } from "../lib/session";
import { colors } from "./ui";
export function CandlestickChart({ scene }: { scene: ChartScene }) {
  const { locale, t } = useSession();
  const [width, setWidth] = useState(320);
  const [cursor, setCursor] = useState<number | null>(null);
  const candles = scene.candles.slice(-80);
  const values = candles
    .flatMap((candle) => [Number(candle.high), Number(candle.low)])
    .filter(Number.isFinite);
  if (!values.length)
    return <Text style={{ color: colors.secondary, padding: 24 }}>{t("chartDataEmpty")}</Text>;
  const minimum = Math.min(...values),
    maximum = Math.max(...values);
  const range = Math.max(maximum - minimum, minimum * 0.001);
  const low = minimum - range * 0.07,
    high = maximum + range * 0.07;
  const padding = 10,
    plotWidth = Math.max(width - 65, 40),
    height = 225;
  const x = (index: number) => padding + ((index + 0.5) * plotWidth) / candles.length;
  const y = (value: number) => 12 + ((high - value) / (high - low)) * (height - 28);
  const selected = candles[Math.min(cursor ?? candles.length - 1, candles.length - 1)];
  const number = (value: number) =>
    new Intl.NumberFormat(locale, { maximumFractionDigits: 5 }).format(value);
  const overlays = scene.indicators.filter((item) =>
    ["ema", "sma", "bollinger_bands"].includes(item.name),
  );
  const oscillators = scene.indicators.filter((item) => item.name === "rsi");
  const grid = Array.from({ length: 5 }, (_, index) => high - ((high - low) * index) / 4);
  return (
    <View onLayout={(event) => setWidth(event.nativeEvent.layout.width)} style={{ gap: 8 }}>
      <Text style={{ color: colors.secondary, fontSize: 11, writingDirection: "ltr" }}>
        {new Date(selected.time).toLocaleString(locale)} · O {number(Number(selected.open))} H{" "}
        {number(Number(selected.high))} L {number(Number(selected.low))} C{" "}
        {number(Number(selected.close))}
      </Text>
      <Svg
        width={width}
        height={height}
        accessibilityRole="image"
        accessibilityLabel={`${scene.symbol} · ${scene.timeframe}`}
        onPress={(event) =>
          setCursor(
            Math.max(
              0,
              Math.min(
                candles.length - 1,
                Math.floor(((event.nativeEvent.locationX - padding) / plotWidth) * candles.length),
              ),
            ),
          )
        }
      >
        {grid.map((price) => (
          <G key={price}>
            <Line
              x1={padding}
              x2={plotWidth + padding}
              y1={y(price)}
              y2={y(price)}
              stroke={colors.border}
            />
            <SvgText x={plotWidth + 17} y={y(price) + 4} fontSize={10} fill={colors.secondary}>
              {number(price)}
            </SvgText>
          </G>
        ))}
        {candles.map((candle, index) => {
          const rising = Number(candle.close) >= Number(candle.open);
          const color = rising ? colors.success : colors.error;
          const bodyY = y(Math.max(Number(candle.open), Number(candle.close)));
          const bodyHeight = Math.max(
            1,
            Math.abs(y(Number(candle.open)) - y(Number(candle.close))),
          );
          return (
            <G key={candle.time}>
              <Line
                x1={x(index)}
                x2={x(index)}
                y1={y(Number(candle.high))}
                y2={y(Number(candle.low))}
                stroke={color}
              />
              <Rect
                x={x(index) - (plotWidth / candles.length) * 0.3}
                y={bodyY}
                width={Math.max(1, (plotWidth / candles.length) * 0.6)}
                height={bodyHeight}
                fill={color}
              />
            </G>
          );
        })}
        {overlays.flatMap((indicator) =>
          Object.entries(indicator.series).map(([key, series]) => (
            <Polyline
              key={indicator.name + key}
              points={series
                .slice(-candles.length)
                .flatMap((value, index) =>
                  value === null || !Number.isFinite(value) ? [] : [`${x(index)},${y(value)}`],
                )
                .join(" ")}
              fill="none"
              stroke={colors.warning}
              strokeWidth={1.4}
            />
          )),
        )}
        {scene.annotations
          .filter((item) => item.type === "price" || item.type === "horizontal_line")
          .map((item, _index) => {
            const price = Number(item.price);
            if (!Number.isFinite(price) || price < low || price > high) return null;
            return (
              <G key={JSON.stringify(item)}>
                <Line
                  x1={padding}
                  x2={plotWidth + padding}
                  y1={y(price)}
                  y2={y(price)}
                  stroke={colors.warning}
                  strokeDasharray="4 4"
                />
                <SvgText x={padding + 4} y={y(price) - 5} fill={colors.warning} fontSize={10}>
                  {String(item.label ?? number(price))}
                </SvgText>
              </G>
            );
          })}
        {cursor !== null ? (
          <Line
            x1={x(Math.min(cursor, candles.length - 1))}
            x2={x(Math.min(cursor, candles.length - 1))}
            y1={12}
            y2={height - 16}
            stroke={colors.secondary}
            strokeDasharray="3 3"
          />
        ) : null}
      </Svg>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={{ color: colors.secondary, fontSize: 10 }}>
          {new Date(candles[0].time).toLocaleDateString(locale)}
        </Text>
        <Text style={{ color: colors.secondary, fontSize: 10 }}>
          {new Date(candles.at(-1)?.time ?? "").toLocaleDateString(locale)}
        </Text>
      </View>
      {oscillators.map((indicator) => (
        <View key={indicator.name} style={{ gap: 5 }}>
          <Text style={{ color: colors.secondary, fontSize: 11 }}>
            {indicator.name.toUpperCase()} {indicator.period}
          </Text>
          <Svg width={width} height={65}>
            {[30, 70].map((level) => (
              <Line
                key={level}
                x1={padding}
                x2={padding + plotWidth}
                y1={60 - level * 0.55}
                y2={60 - level * 0.55}
                stroke={colors.border}
                strokeDasharray="4 4"
              />
            ))}
            {Object.entries(indicator.series).map(([key, series]) => (
              <Polyline
                key={key}
                points={series
                  .slice(-candles.length)
                  .flatMap((value, index) =>
                    value === null || !Number.isFinite(value)
                      ? []
                      : [`${x(index)},${60 - value * 0.55}`],
                  )
                  .join(" ")}
                fill="none"
                stroke={colors.warning}
                strokeWidth={1.4}
              />
            ))}
          </Svg>
        </View>
      ))}
      {scene.annotations
        .filter((item) => item.type === "note")
        .map((item, _index) => (
          <Text
            key={JSON.stringify(item)}
            style={{ color: colors.secondary, fontSize: 12, writingDirection: "auto" }}
          >
            {String(item.text ?? item.label ?? "")}
          </Text>
        ))}
    </View>
  );
}
