// The owner's orders, pure: the request bodies the Web sends (apps/web shell/agent/TradesPage.tsx,
// components/trading/TradeActionCard.tsx and Orders.tsx), their ticket keys
// (components/trading/useTicketAction.ts `ticketOf` / `modifyTicket`), every TradeRequest rule
// checked before anything is sent (lonora_contracts.trading `validate_action` and
// lonora_security.financial `validate_trade`: the server's 422 loses the reason), which exits stay
// admissible while the broker is not verified (lonora_trading.admission `risk_reducing`), and the
// order log's states (shell/agent/order-state.ts). Nothing here sends anything.
import 'package:flutter/foundation.dart';

import '../../core/json.dart';
import '../market/market_data.dart';
import 'trade_numbers.dart';

/// The six entries the ticket offers, in the Web's order.
const tradeEntryActions = [
  'buy',
  'sell',
  'buy_limit',
  'sell_limit',
  'buy_stop',
  'sell_stop',
];

/// Entries that wait for a price (a limit or a stop order).
const pendingEntryActions = {
  'buy_limit',
  'sell_limit',
  'buy_stop',
  'sell_stop',
};

/// The statuses that settle an operation (lonora_contracts.trading `TERMINAL_STATUSES`).
const settledStatuses = {'confirmed', 'failed', 'resolved'};

/// Every status an executor answer may carry (`OperationStatus`).
const operationStatuses = {
  'reserved',
  'submitted',
  'confirmed',
  'failed',
  'ambiguous',
  'resolved',
};

bool operationSettled(String status) => settledStatuses.contains(status);

/// Possibly sent and not settled: the identity stays held and is never resent under a new one.
bool operationUnsettled(String status) =>
    const {'reserved', 'submitted', 'ambiguous'}.contains(status);

/// Codes of a 4xx that do not prove the request journaled nothing under this identity.
const keepHeldCodes = {'idempotency_conflict', 'operation_id_conflict'};

/// The held identity's key: one per action, account and ticket (held-operation.ts `key`).
String heldKey(String action, String accountId, String ticket) =>
    '$action:$accountId:$ticket';

/// The one open-order slot of an account: its form shows the held order until it settles.
String openKey(String accountId) => 'open:$accountId';

/// A modify is one operation per distinct change: the position and the body's values
/// (useTicketAction.ts `modifyTicket`).
String modifyTicket(Json request) {
  String value(String key) {
    final item = request[key];
    return item == null || item == false ? '' : '$item';
  }

  return [
    'position_id',
    'stop_loss',
    'take_profit',
    'clear_stop_loss',
    'clear_take_profit',
  ].map(value).join('|');
}

/// The ticket a journal row's request belongs to (useTicketAction.ts `ticketOf`).
String ticketOf(String action, Json request) => switch (action) {
  'modify_position' => modifyTicket(request),
  'cancel_order' => asStr(request['order_id']),
  _ => asStr(request['position_id']),
};

/// The key of the held identity a body belongs to.
String keyOfBody(Json body) {
  final action = asStr(body['action']);
  final account = asStr(body['account_id']);
  return switch (action) {
    'close_position' ||
    'modify_position' ||
    'cancel_order' => heldKey(action, account, ticketOf(action, body)),
    _ => openKey(account),
  };
}

/// «إغلاق الصفقة»: always the whole position (the Web sends no volume).
Json closeRequest({required String accountId, required MarketPosition p}) => {
  'account_id': accountId,
  'action': 'close_position',
  'symbol': p.symbol,
  'position_id': p.id,
};

/// «إلغاء الأمر» of a pending order.
Json cancelRequest({required String accountId, required MarketOrder o}) => {
  'account_id': accountId,
  'action': 'cancel_order',
  'symbol': o.symbol,
  'order_id': o.id,
};

/// «تعديل الوقف والهدف» (TradesPage.tsx `openModify`): a value sets the level, an emptied field
/// where the position had one is an explicit clear, an empty field on an unset level sends
/// nothing. [stop] and [target] are already-validated canonical decimals or ''.
Json modifyRequest({
  required String accountId,
  required MarketPosition p,
  required String stop,
  required String target,
}) => {
  'account_id': accountId,
  'action': 'modify_position',
  'symbol': p.symbol,
  'position_id': p.id,
  if (stop.isNotEmpty)
    'stop_loss': stop
  else if ((p.stopLoss ?? '').isNotEmpty)
    'clear_stop_loss': true,
  if (target.isNotEmpty)
    'take_profit': target
  else if ((p.takeProfit ?? '').isNotEmpty)
    'clear_take_profit': true,
};

/// A new order (TradeActionCard.tsx): the price only for a pending entry, the optional levels
/// only when given. Values are already-validated canonical decimals ('' when not given).
Json openRequest({
  required String accountId,
  required String action,
  required String symbol,
  required String volume,
  String price = '',
  String stop = '',
  String target = '',
}) => {
  'account_id': accountId,
  'action': action,
  'symbol': symbol,
  'volume': volume,
  if (pendingEntryActions.contains(action)) 'price': price,
  if (stop.isNotEmpty) 'stop_loss': stop,
  if (target.isNotEmpty) 'take_profit': target,
};

/// Why a typed value cannot be sent; [args] fill the message's `{0}` `{1}`.
@immutable
class FieldProblem {
  const FieldProblem(this.key, [this.args = const []]);

  /// A label key of lib/features/trading/trading_strings.dart.
  final String key;
  final List<String> args;

  @override
  bool operator ==(Object other) =>
      other is FieldProblem && other.key == key && listEquals(other.args, args);

  @override
  int get hashCode => Object.hash(key, Object.hashAll(args));

  @override
  String toString() => 'FieldProblem($key, $args)';
}

/// The broker's limits of one instrument as exact decimals (null where the broker gave none).
@immutable
class InstrumentLimits {
  const InstrumentLimits({
    this.tickSize,
    this.volumeMin,
    this.volumeMax,
    this.volumeStep,
  });

  factory InstrumentLimits.of(MarketInstrument i) => InstrumentLimits(
    tickSize: _positive(i.tickSize),
    volumeMin: _positive(i.volumeMin),
    volumeMax: _positive(i.volumeMax),
    volumeStep: _positive(i.volumeStep),
  );

  static Dec? _positive(String text) {
    final d = Dec.fromServer(text);
    return d == null || !d.isPositive ? null : d;
  }

  final Dec? tickSize;
  final Dec? volumeMin;
  final Dec? volumeMax;
  final Dec? volumeStep;
}

/// A typed decimal field: empty (null result, no problem), a number > 0, or a problem.
({Dec? value, FieldProblem? problem}) readDecimal(
  String text, {
  bool required = false,
}) {
  if (text.trim().isEmpty) {
    return (
      value: null,
      problem: required ? const FieldProblem('tr_errRequired') : null,
    );
  }
  final d = Dec.parse(text);
  if (d == null) {
    return (value: null, problem: const FieldProblem('tr_errNumber'));
  }
  if (!d.isPositive) {
    return (value: null, problem: const FieldProblem('tr_errPositive'));
  }
  return (value: d, problem: null);
}

/// The volume rules (`validate_trade`): within the broker's range, on its step from the
/// minimum.
FieldProblem? volumeProblem(Dec volume, InstrumentLimits limits) {
  final min = limits.volumeMin, max = limits.volumeMax;
  if ((min != null && volume < min) || (max != null && volume > max)) {
    return FieldProblem('tr_errVolumeRange', [
      '${min ?? '—'}',
      '${max ?? '—'}',
    ]);
  }
  final step = limits.volumeStep;
  if (step != null) {
    final from = volume.minus(min ?? Dec.zero);
    if (from == null || !from.multipleOf(step)) {
      return FieldProblem('tr_errVolumeStep', ['${min ?? 0}', '$step']);
    }
  }
  return null;
}

/// A price, stop or target on the instrument's tick (`validate_trade`).
FieldProblem? tickProblem(Dec price, InstrumentLimits limits) {
  final tick = limits.tickSize;
  if (tick == null || price.multipleOf(tick)) return null;
  return FieldProblem('tr_errTick', ['$tick']);
}

/// A checked new order: the canonical values, or the problem of each field.
@immutable
class OpenCheck {
  const OpenCheck({this.problems = const {}, this.request});

  /// Field → problem (`volume`, `price`, `stop_loss`, `take_profit`, `symbol`).
  final Map<String, FieldProblem> problems;

  /// The body to send, when nothing is wrong (without account and operation id checks).
  final Json? request;

  bool get ok => request != null;
}

/// Every rule of a new order before it is sent: the symbol, a volume within the broker's
/// range and step, a price exactly for a pending entry, levels on the tick, each > 0.
OpenCheck checkOpen({
  required String accountId,
  required String action,
  required String symbol,
  required String volume,
  required String price,
  required String stop,
  required String target,
  required InstrumentLimits limits,
}) {
  final problems = <String, FieldProblem>{};
  if (symbol.isEmpty || symbol.length > 80) {
    problems['symbol'] = const FieldProblem('tr_errSymbol');
  }
  final v = readDecimal(volume, required: true);
  if (v.problem != null) {
    problems['volume'] = v.problem!;
  } else if (volumeProblem(v.value!, limits) case final p?) {
    problems['volume'] = p;
  }
  final pending = pendingEntryActions.contains(action);
  Dec? priceValue;
  if (pending) {
    final r = readDecimal(price, required: true);
    if (r.problem != null) {
      problems['price'] = r.problem!;
    } else if (tickProblem(r.value!, limits) case final p?) {
      problems['price'] = p;
    } else {
      priceValue = r.value;
    }
  }
  Dec? level(String field, String text) {
    final r = readDecimal(text);
    if (r.problem != null) {
      problems[field] = r.problem!;
      return null;
    }
    if (r.value == null) return null;
    if (tickProblem(r.value!, limits) case final p?) {
      problems[field] = p;
      return null;
    }
    return r.value;
  }

  final sl = level('stop_loss', stop);
  final tp = level('take_profit', target);
  if (problems.isNotEmpty || !tradeEntryActions.contains(action)) {
    return OpenCheck(problems: problems);
  }
  return OpenCheck(
    request: openRequest(
      accountId: accountId,
      action: action,
      symbol: symbol,
      volume: '${v.value}',
      price: priceValue?.toString() ?? '',
      stop: sl?.toString() ?? '',
      target: tp?.toString() ?? '',
    ),
  );
}

/// A checked stop-and-target edit (`modification_fields_required`, ticks, > 0).
@immutable
class ModifyCheck {
  const ModifyCheck({this.problems = const {}, this.request});

  /// `stop_loss` / `take_profit` → problem, or `change` → nothing differs from the position.
  final Map<String, FieldProblem> problems;
  final Json? request;

  bool get ok => request != null;
}

/// Every rule of a stop-and-target edit. [limits] null skips the tick check (no instrument
/// could be read: the server still checks it).
ModifyCheck checkModify({
  required String accountId,
  required MarketPosition position,
  required String stop,
  required String target,
  InstrumentLimits? limits,
}) {
  final problems = <String, FieldProblem>{};
  String level(String field, String text) {
    final r = readDecimal(text);
    if (r.problem != null) {
      problems[field] = r.problem!;
      return '';
    }
    if (r.value == null) return '';
    if (limits != null) {
      if (tickProblem(r.value!, limits) case final p?) {
        problems[field] = p;
        return '';
      }
    }
    return '${r.value}';
  }

  final sl = level('stop_loss', stop);
  final tp = level('take_profit', target);
  if (problems.isNotEmpty) return ModifyCheck(problems: problems);
  bool same(String typed, String? current) {
    if (typed.isEmpty) return (current ?? '').trim().isEmpty;
    final now = Dec.fromServer(current);
    return now != null && now == Dec.parse(typed);
  }

  if (same(sl, position.stopLoss) && same(tp, position.takeProfit)) {
    return const ModifyCheck(
      problems: {'change': FieldProblem('tr_errNoChange')},
    );
  }
  return ModifyCheck(
    request: modifyRequest(
      accountId: accountId,
      p: position,
      stop: sl,
      target: tp,
    ),
  );
}

/// Buy, sell or unknown from a broker side (lonora_trading.exposure `direction`).
String sideOf(String side) {
  final s = side.replaceFirst('ORDER_TYPE_', '').toLowerCase();
  return s.startsWith('buy')
      ? 'buy'
      : s.startsWith('sell')
      ? 'sell'
      : 'unknown';
}

/// Whether filling [order] would shrink its symbol's net open volume (admission.py
/// `protective_order`): cancelling such an order removes protection.
bool protectiveOrder(MarketOrder order, List<MarketPosition> positions) {
  var long = Dec.zero, short = Dec.zero;
  for (final p in positions) {
    if (p.symbol != order.symbol) continue;
    final side = sideOf(p.side);
    final volume = Dec.fromServer(p.volume);
    // A side or volume that cannot be read: the order cannot be shown to only add exposure.
    if (side == 'unknown' || volume == null) return true;
    if (side == 'buy') {
      long = long.plus(volume);
    } else {
      short = short.plus(volume);
    }
  }
  if (long == short) return false;
  final side = sideOf(order.side);
  final volume = Dec.fromServer(order.volume);
  if (side == 'unknown' || volume == null) return true;
  final longAfter = side == 'buy' ? long.plus(volume) : long;
  final shortAfter = side == 'sell' ? short.plus(volume) : short;
  return _gap(longAfter, shortAfter) < _gap(long, short);
}

Dec _gap(Dec a, Dec b) => a >= b ? a.minus(b)! : b.minus(a)!;

/// Whether a request stays admissible while the broker account cannot be verified: a full
/// close, the cancel of a non-protective order, or a stop moved strictly toward the market (or
/// added) with the target unchanged and nothing cleared (admission.py `risk_reducing`).
bool riskReducing(Json request, AccountSnapshot snapshot) {
  final action = asStr(request['action']);
  switch (action) {
    case 'close_position':
      return snapshot.positions.any(
        (p) => p.id == request['position_id'] && p.symbol == request['symbol'],
      );
    case 'cancel_order':
      final order = snapshot.orders
          .where(
            (o) => o.id == request['order_id'] && o.symbol == request['symbol'],
          )
          .firstOrNull;
      return order != null && !protectiveOrder(order, snapshot.positions);
    case 'modify_position':
      final p = snapshot.positions
          .where(
            (p) =>
                p.id == request['position_id'] && p.symbol == request['symbol'],
          )
          .firstOrNull;
      if (p == null) return false;
      if (request['clear_stop_loss'] == true ||
          request['clear_take_profit'] == true) {
        return false;
      }
      final stop = Dec.fromServer(request['stop_loss']);
      if (stop == null) return false;
      final target = request['take_profit'];
      if (target != null &&
          Dec.fromServer(target) != Dec.fromServer(p.takeProfit)) {
        return false;
      }
      final side = sideOf(p.side);
      if (side == 'unknown') return false;
      final current = Dec.fromServer(p.stopLoss);
      if (current == null || current.isZero) return true;
      return side == 'buy' ? stop > current : stop < current;
    default:
      return false;
  }
}

/// The order log's states (shell/agent/order-state.ts `OrderState`).
enum OrderState {
  requested,
  sent,
  accepted,
  partial,
  filled,
  rejected,
  cancelled,
  uncertain,
}

/// Tones of the state chip (order-state.ts `ORDER_TONE`).
enum OrderTone { wait, ok, bad, off, warn }

OrderTone orderTone(OrderState s) => switch (s) {
  OrderState.requested ||
  OrderState.sent ||
  OrderState.accepted => OrderTone.wait,
  OrderState.partial || OrderState.filled => OrderTone.ok,
  OrderState.rejected => OrderTone.bad,
  OrderState.cancelled => OrderTone.off,
  OrderState.uncertain => OrderTone.warn,
};

/// «منفَّذ» only with the broker's evidence or the owner's own confirmation; a partial fill is
/// «منفَّذ جزئيًا»; a placed limit or stop order is «مقبول لدى الوسيط» (order-state.ts
/// `orderState`).
OrderState orderState(JournalEntry e) {
  switch (e.status) {
    case 'reserved':
      return OrderState.requested;
    case 'submitted':
      return OrderState.sent;
    case 'confirmed':
      if (e.partialFill) return OrderState.partial;
      if (pendingEntryActions.contains(e.action)) return OrderState.accepted;
      return e.verified ? OrderState.filled : OrderState.accepted;
    case 'failed':
      return OrderState.rejected;
    case 'ambiguous':
      return OrderState.uncertain;
    case 'resolved':
      return switch (e.resolutionOutcome) {
        'executed' => OrderState.filled,
        'not_executed' => OrderState.cancelled,
        _ => OrderState.uncertain,
      };
    default:
      return OrderState.uncertain;
  }
}

/// The broker's evidence on a fill: its price and the volume it reports; only a filled or
/// partly filled order has any (order-state.ts `orderFill`).
({String? price, String? volume}) orderFill(JournalEntry e) {
  final state = orderState(e);
  if (state != OrderState.filled && state != OrderState.partial) {
    return (price: null, volume: null);
  }
  String? decimal(Object? v) {
    if (v == null || v == '' || v is bool) return null;
    return double.tryParse('$v')?.isFinite == true ? '$v' : null;
  }

  final d = e.resultDetails;
  return (price: decimal(d['price']), volume: decimal(d['volume']));
}
