import type {
  CustomIndicator,
  PineJS,
  StudyMetaInfo,
  StudyPlotType,
} from "../../public/charting_library/charting_library";
import type { SceneDatafeed } from "./tradingview-feed";

/** Custom studies are display adapters for server values, with no local indicator maths. */
export function sceneStudies(source: SceneDatafeed, pine: PineJS): CustomIndicator[] {
  return source.scene.indicators.map((indicator, index) => {
    const names = Object.keys(indicator.series);
    const title = `Lonora ${indicator.name} ${indicator.period} (${index + 1})`;
    return {
      name: title,
      metainfo: {
        _metainfoVersion: 53,
        id: `LonoraScene${index}@tv-basicstudies-1` as StudyMetaInfo["id"],
        description: title,
        shortDescription: title,
        isCustomIndicator: true,
        is_price_study: !["RSI", "MACD", "ATR"].includes(indicator.name.toUpperCase()),
        linkedToSeries: true,
        format: { type: "price", precision: 6 },
        plots: names.map((_name, i) => ({ id: `plot_${i}`, type: "line" as StudyPlotType.Line })),
        styles: Object.fromEntries(
          names.map((name, i) => [`plot_${i}`, { title: name, histogramBase: 0 }]),
        ),
        defaults: {
          styles: Object.fromEntries(
            names.map((_name, i) => [
              `plot_${i}`,
              {
                color: ["#6289e8", "#d4a73c", "#b48adb"][i % 3],
                linewidth: 1,
                linestyle: 0,
                plottype: 0,
                trackPrice: false,
                transparency: 0,
                visible: true,
              },
            ]),
          ),
          inputs: {},
        },
        inputs: [],
      },
      constructor: function () {
        this.main = (context) => {
          const time = pine.Std.time(context);
          const scene = source.scene;
          const candleIndex = scene.candles.findIndex((candle) => Date.parse(candle.time) === time);
          return names.map(
            (name) => scene.indicators[index]?.series[name]?.[candleIndex] ?? Number.NaN,
          );
        };
      },
    };
  });
}
