// The owner's orders, pure: exact decimals, every TradeRequest rule checked before a send, the
// request bodies and ticket keys of the Web, the exits admitted while the broker is not
// verified, and the order log's states.
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/features/market/market_data.dart';
import 'package:lonora/features/trading/trade_numbers.dart';
import 'package:lonora/features/trading/trade_rules.dart';

const _gold = InstrumentLimits(
  tickSize: null,
  volumeMin: null,
  volumeMax: null,
  volumeStep: null,
);

InstrumentLimits limits({
  String tick = '0.01',
  String min = '0.01',
  String max = '50',
  String step = '0.01',
}) => InstrumentLimits.of(
  MarketInstrument({
    'tick_size': tick,
    'volume_min': min,
    'volume_max': max,
    'volume_step': step,
  }),
);

const position = MarketPosition({
  'id': 'p-1',
  'symbol': 'XAUUSD',
  'side': 'buy',
  'volume': '0.10',
  'stop_loss': '2365.00',
  'take_profit': null,
});

void main() {
  group('exact decimals', () {
    test(
      'typed numbers: digits, «٫», Arabic-Indic; no sign, exponent or grouping',
      () {
        final table = <String, String?>{
          '0.3': '0.3',
          '2380.50': '2380.5',
          '007': '7',
          '.5': '0.5',
          '5.': '5',
          '١٢٣٫٤٥': '123.45',
          '۲۳۸۰٫۵': '2380.5',
          ' 0.10 ': '0.1',
          '0.0000001': '0.0000001',
          '1e-7': null,
          '1E3': null,
          '-1': null,
          '+1': null,
          '1,5': null,
          '1٬000': null,
          '1.2.3': null,
          '': null,
          '.': null,
          'abc': null,
        };
        for (final MapEntry(:key, :value) in table.entries) {
          expect(Dec.parse(key)?.toString(), value, reason: key);
        }
      },
    );

    test('server decimals, exponent forms included; never a double', () {
      expect(Dec.fromServer('1E-7').toString(), '0.0000001');
      expect(Dec.fromServer('1.5E+2').toString(), '150');
      expect(Dec.fromServer('2.50E1').toString(), '25');
      expect(Dec.fromServer(2380.5).toString(), '2380.5');
      expect(Dec.fromServer('0.10').toString(), '0.1');
      expect(Dec.fromServer('-1'), isNull);
      expect(Dec.fromServer(null), isNull);
      expect(Dec.fromServer(true), isNull);
    });

    test('0.3 is a multiple of 0.1 (a double says it is not)', () {
      expect(0.3 % 0.1 == 0, isFalse);
      expect(Dec.parse('0.3')!.multipleOf(Dec.parse('0.1')!), isTrue);
      expect(Dec.parse('0.35')!.multipleOf(Dec.parse('0.1')!), isFalse);
      expect(Dec.parse('2380.55')!.multipleOf(Dec.parse('0.05')!), isTrue);
      expect(Dec.parse('1')!.multipleOf(Dec.zero), isFalse);
      expect(Dec.parse('0.3')!.minus(Dec.parse('0.1')!).toString(), '0.2');
      expect(Dec.parse('0.1')!.minus(Dec.parse('0.3')!), isNull);
      expect(Dec.parse('0.10')!, Dec.parse('0.1')!);
      expect(Dec.parse('0.2')! > Dec.parse('0.19')!, isTrue);
    });
  });

  group('a new order', () {
    OpenCheck check({
      String action = 'buy',
      String symbol = 'XAUUSD',
      String volume = '0.10',
      String price = '',
      String stop = '',
      String target = '',
      InstrumentLimits? l,
    }) => checkOpen(
      accountId: 'acct-1',
      action: action,
      symbol: symbol,
      volume: volume,
      price: price,
      stop: stop,
      target: target,
      limits: l ?? limits(),
    );

    test('a market order sends no price, levels only when given', () {
      final c = check(volume: '٠٫١٠', stop: '2365', price: '2400');
      expect(c.request, {
        'account_id': 'acct-1',
        'action': 'buy',
        'symbol': 'XAUUSD',
        'volume': '0.1',
        'stop_loss': '2365',
      });
    });

    test('a pending entry needs its price, on the tick', () {
      expect(
        check(action: 'buy_limit').problems['price']?.key,
        'tr_errRequired',
      );
      expect(
        check(action: 'sell_stop', price: '2350.005').problems['price'],
        const FieldProblem('tr_errTick', ['0.01']),
      );
      expect(check(action: 'buy_limit', price: '2350.00').request, {
        'account_id': 'acct-1',
        'action': 'buy_limit',
        'symbol': 'XAUUSD',
        'volume': '0.1',
        'price': '2350',
      });
    });

    test('volume: required, > 0, in range, on the step from the minimum', () {
      expect(check(volume: '').problems['volume']?.key, 'tr_errRequired');
      expect(check(volume: '0').problems['volume']?.key, 'tr_errPositive');
      expect(check(volume: 'x').problems['volume']?.key, 'tr_errNumber');
      expect(
        check(volume: '60').problems['volume'],
        const FieldProblem('tr_errVolumeRange', ['0.01', '50']),
      );
      expect(
        check(volume: '0.015').problems['volume'],
        const FieldProblem('tr_errVolumeStep', ['0.01', '0.01']),
      );
      // A step counted from the minimum: 0.1 + n × 0.2.
      final odd = limits(min: '0.1', step: '0.2');
      expect(check(volume: '0.3', l: odd).ok, isTrue);
      expect(
        check(volume: '0.4', l: odd).problems['volume']?.key,
        'tr_errVolumeStep',
      );
    });

    test('levels: > 0 and on the tick; the symbol must be given', () {
      expect(check(stop: '0').problems['stop_loss']?.key, 'tr_errPositive');
      expect(
        check(target: '2400.001').problems['take_profit']?.key,
        'tr_errTick',
      );
      expect(check(symbol: '').problems['symbol']?.key, 'tr_errSymbol');
      expect(check(volume: '1', l: _gold).ok, isTrue);
    });
  });

  group('an edit of stop and target', () {
    ModifyCheck edit(String stop, String target, {InstrumentLimits? l}) =>
        checkModify(
          accountId: 'acct-1',
          position: position,
          stop: stop,
          target: target,
          limits: l ?? limits(),
        );

    test('nothing changed: refused before any send', () {
      expect(edit('2365.00', '').problems['change']?.key, 'tr_errNoChange');
      expect(edit('2365', '').problems['change']?.key, 'tr_errNoChange');
    });

    test(
      'a value sets, an emptied level clears, an unset one sends nothing',
      () {
        expect(edit('2370', '2450').request, {
          'account_id': 'acct-1',
          'action': 'modify_position',
          'symbol': 'XAUUSD',
          'position_id': 'p-1',
          'stop_loss': '2370',
          'take_profit': '2450',
        });
        final cleared = edit('', '').request;
        expect(cleared, {
          'account_id': 'acct-1',
          'action': 'modify_position',
          'symbol': 'XAUUSD',
          'position_id': 'p-1',
          'clear_stop_loss': true,
        });
        expect(cleared!.containsKey('stop_loss'), isFalse);
        expect(cleared.containsKey('volume'), isFalse);
        expect(cleared.containsKey('price'), isFalse);
      },
    );

    test('levels on the tick, digits normalised', () {
      expect(edit('2370.005', '').problems['stop_loss']?.key, 'tr_errTick');
      expect(edit('٢٣٧٠٫٥', '').request!['stop_loss'], '2370.5');
      expect(edit('2370.005', '', l: _gold).ok, isTrue);
    });

    test('the ticket is the position and the values (modifyTicket)', () {
      final a = edit('2370', '').request!;
      final b = edit('2371', '').request!;
      expect(modifyTicket(a), 'p-1|2370|||');
      expect(modifyTicket(b), isNot(modifyTicket(a)));
      expect(modifyTicket(edit('', '').request!), 'p-1|||true|');
      expect(keyOfBody(a), 'modify_position:acct-1:p-1|2370|||');
      expect(ticketOf('modify_position', a), modifyTicket(a));
    });
  });

  test('close and cancel bodies, and their keys', () {
    final close = closeRequest(accountId: 'acct-1', p: position);
    expect(close, {
      'account_id': 'acct-1',
      'action': 'close_position',
      'symbol': 'XAUUSD',
      'position_id': 'p-1',
    });
    expect(keyOfBody(close), 'close_position:acct-1:p-1');
    const order = MarketOrder({
      'id': 'o-7',
      'symbol': 'XAUUSD',
      'side': 'buy_limit',
      'volume': '0.2',
    });
    final cancel = cancelRequest(accountId: 'acct-1', o: order);
    expect(cancel, {
      'account_id': 'acct-1',
      'action': 'cancel_order',
      'symbol': 'XAUUSD',
      'order_id': 'o-7',
    });
    expect(keyOfBody(cancel), 'cancel_order:acct-1:o-7');
    expect(keyOfBody({'action': 'buy', 'account_id': 'acct-1'}), 'open:acct-1');
  });

  test('statuses that settle and those that keep the identity', () {
    for (final s in ['confirmed', 'failed', 'resolved']) {
      expect(operationSettled(s), isTrue);
      expect(operationUnsettled(s), isFalse);
    }
    for (final s in ['reserved', 'submitted', 'ambiguous']) {
      expect(operationSettled(s), isFalse);
      expect(operationUnsettled(s), isTrue);
    }
  });

  group('exits admitted while the broker is not verified', () {
    AccountSnapshot snap({List<Json>? positions, List<Json>? orders}) =>
        AccountSnapshot.fromJson({
          'account': {'id': 'acct-1'},
          'positions':
              positions ??
              [
                {
                  'id': 'p-1',
                  'symbol': 'XAUUSD',
                  'side': 'buy',
                  'volume': '0.10',
                  'stop_loss': '2365.00',
                  'take_profit': '2450',
                },
              ],
          'orders': orders ?? const [],
        });

    Json modify(Json extra) => {
      'action': 'modify_position',
      'symbol': 'XAUUSD',
      'position_id': 'p-1',
      ...extra,
    };

    test('a close of an open position', () {
      expect(
        riskReducing({
          'action': 'close_position',
          'symbol': 'XAUUSD',
          'position_id': 'p-1',
        }, snap()),
        isTrue,
      );
      expect(
        riskReducing({
          'action': 'close_position',
          'symbol': 'XAUUSD',
          'position_id': 'p-9',
        }, snap()),
        isFalse,
      );
    });

    test(
      'a stop moved toward the market, target unchanged, nothing cleared',
      () {
        final s = snap();
        expect(riskReducing(modify({'stop_loss': '2370'}), s), isTrue);
        expect(riskReducing(modify({'stop_loss': '2360'}), s), isFalse);
        expect(riskReducing(modify({'stop_loss': '2365'}), s), isFalse);
        expect(
          riskReducing(
            modify({'stop_loss': '2370', 'take_profit': '2450.0'}),
            s,
          ),
          isTrue,
        );
        expect(
          riskReducing(modify({'stop_loss': '2370', 'take_profit': '2460'}), s),
          isFalse,
        );
        expect(
          riskReducing(
            modify({'stop_loss': '2370', 'clear_take_profit': true}),
            s,
          ),
          isFalse,
        );
        expect(riskReducing(modify({'take_profit': '2460'}), s), isFalse);
        final sell = snap(
          positions: [
            {
              'id': 'p-1',
              'symbol': 'XAUUSD',
              'side': 'sell',
              'volume': '1',
              'stop_loss': '2400',
            },
          ],
        );
        expect(riskReducing(modify({'stop_loss': '2390'}), sell), isTrue);
        expect(riskReducing(modify({'stop_loss': '2410'}), sell), isFalse);
        final bare = snap(
          positions: [
            {'id': 'p-1', 'symbol': 'XAUUSD', 'side': 'buy', 'volume': '1'},
          ],
        );
        expect(riskReducing(modify({'stop_loss': '2300'}), bare), isTrue);
      },
    );

    test('a cancel of an entry order, never of a protective one', () {
      const entry = {
        'id': 'o-1',
        'symbol': 'XAUUSD',
        'side': 'buy_limit',
        'volume': '0.2',
      };
      const protect = {
        'id': 'o-2',
        'symbol': 'XAUUSD',
        'side': 'sell_stop',
        'volume': '0.05',
      };
      final s = snap(orders: [entry, protect]);
      Json cancel(String id) => {
        'action': 'cancel_order',
        'symbol': 'XAUUSD',
        'order_id': id,
      };
      expect(riskReducing(cancel('o-1'), s), isTrue);
      expect(riskReducing(cancel('o-2'), s), isFalse);
      expect(protectiveOrder(const MarketOrder(protect), s.positions), isTrue);
      expect(protectiveOrder(const MarketOrder(entry), const []), isFalse);
      expect(
        protectiveOrder(
          MarketOrder({...protect}..['side'] = 'weird'),
          s.positions,
        ),
        isTrue,
      );
      expect(riskReducing({'action': 'buy', 'symbol': 'XAUUSD'}, s), isFalse);
    });
  });

  group('order states (order-state.ts)', () {
    JournalEntry e(
      String status, {
      String action = 'buy',
      Json details = const {},
      String? verification,
      Json? resolution,
    }) => JournalEntry({
      'status': status,
      'request': {'action': action, 'symbol': 'XAUUSD', 'volume': '0.5'},
      'result': {'details': details},
      'verification_status': verification,
      'resolution': resolution,
    });

    test('every branch', () {
      expect(orderState(e('reserved')), OrderState.requested);
      expect(orderState(e('submitted')), OrderState.sent);
      expect(
        orderState(e('confirmed', details: {'partial_execution': true})),
        OrderState.partial,
      );
      expect(
        orderState(
          e('confirmed', action: 'buy_limit', verification: 'verified'),
        ),
        OrderState.accepted,
      );
      expect(
        orderState(e('confirmed', verification: 'verified')),
        OrderState.filled,
      );
      expect(
        orderState(
          e(
            'confirmed',
            details: {
              'verification': {'status': 'verified'},
            },
          ),
        ),
        OrderState.filled,
      );
      expect(
        orderState(e('confirmed', verification: 'pending')),
        OrderState.accepted,
      );
      expect(orderState(e('failed')), OrderState.rejected);
      expect(orderState(e('ambiguous')), OrderState.uncertain);
      expect(
        orderState(e('resolved', resolution: {'outcome': 'executed'})),
        OrderState.filled,
      );
      expect(
        orderState(e('resolved', resolution: {'outcome': 'not_executed'})),
        OrderState.cancelled,
      );
      expect(orderState(e('resolved')), OrderState.uncertain);
      expect(orderState(e('weird')), OrderState.uncertain);
      expect(orderTone(OrderState.partial), OrderTone.ok);
      expect(orderTone(OrderState.cancelled), OrderTone.off);
      expect(orderTone(OrderState.uncertain), OrderTone.warn);
    });

    test('a price and size only with the broker evidence of a fill', () {
      final filled = e(
        'confirmed',
        verification: 'verified',
        details: {'price': '2380.5', 'volume': '0.5'},
      );
      expect(orderFill(filled), (price: '2380.5', volume: '0.5'));
      final partial = e(
        'confirmed',
        details: {'partial_execution': true, 'volume': '0.2', 'price': 'x'},
      );
      expect(orderFill(partial), (price: null, volume: '0.2'));
      expect(orderFill(e('failed', details: {'price': '1'})), (
        price: null,
        volume: null,
      ));
    });
  });
}
