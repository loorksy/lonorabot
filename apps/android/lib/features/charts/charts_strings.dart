import '../../l10n/l10n.dart';

/// Android-only labels of the charts screen. Lonora's own chart keys (charts, chartEmpty,
/// chartDataEmpty, chartInitializing, chartUpdated, createChart, chooseAccount, chooseSymbol,
/// brokerMissing, timeframe, quote, bid, ask…) are used directly.
void registerChartsStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('ch_refreshRequested')) return;
  target.register(_chartsStrings);
}

const Map<String, List<String>> _chartsStrings = {
  'ch_refreshRequested': ['طُلب تحديث الرسم', 'Chart refresh requested'],
  'ch_range': ['المدى', 'Range'],
  'ch_candles': ['{0} شمعة', '{0} candles'],
  'ch_crosshair': [
    'المس الرسم واسحب لقراءة الشموع',
    'Touch and drag the chart to read the candles',
  ],
  'ch_notes': ['ملاحظات الرسم', 'Chart notes'],
  // The series of a multi-line indicator (MACD, Bollinger bands) in its readout.
  'ch_series_macd': ['MACD', 'MACD'],
  'ch_series_signal': ['الإشارة', 'Signal'],
  'ch_series_histogram': ['المدرج', 'Histogram'],
  'ch_series_upper': ['العلوي', 'Upper'],
  'ch_series_middle': ['الأوسط', 'Middle'],
  'ch_series_lower': ['السفلي', 'Lower'],
};
