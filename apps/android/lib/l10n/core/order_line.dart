/// Port of the text of packages/core/src/order-line.ts and trade-action-labels.ts: the order
/// line's state names and what an operation does, in @lonora/core's words.
library;

import 'core_tables.g.dart';
import 'text.dart';
import 'values.dart';

/// The owner's words for each trade action (trade-action-labels.ts:1-27).
TradeActionText tradeActionText(String locale) =>
    tradeActionLabels[language(locale)]!;

/// «منفَّذ» / "Filled" … for an order-line state (order-line.ts:68-70).
String orderLineText(String state, String locale) =>
    orderLineLabels[locale.startsWith('ar') ? 'ar' : 'en']![state] ?? '';

String? _decimal(Object? value) {
  if (value is num && value.isFinite) return jsString(value);
  if (value is String && value.trim().isNotEmpty) {
    final parsed = num.tryParse(value.trim());
    if (parsed != null && parsed.isFinite) return value;
  }
  return null;
}

const List<String> _volumeActions = [
  'buy',
  'sell',
  'buy_limit',
  'sell_limit',
  'buy_stop',
  'sell_stop',
  'close_position',
];

/// What the operation does: «شراء» / «بيع» for market orders, the trade-action words for the
/// rest; its volume (entries and closes only) and direction (up, down or null). [request] is
/// the journal's request JSON (order-line.ts:167-202).
({String label, String? volume, String? direction}) orderLineAction(
  Map<String, Object?> request,
  String locale,
) {
  final action = jsString(request['action']);
  final ar = locale.startsWith('ar');
  final labels = tradeActionLabels[ar ? 'ar' : 'en']!;
  final label = action == 'buy'
      ? (ar ? 'شراء' : 'Buy')
      : action == 'sell'
      ? (ar ? 'بيع' : 'Sell')
      : labels[action] ?? action;
  final volume = _volumeActions.contains(action)
      ? _decimal(request['volume'])
      : null;
  final direction = action.startsWith('buy')
      ? 'up'
      : action.startsWith('sell')
      ? 'down'
      : null;
  return (label: label, volume: volume, direction: direction);
}
