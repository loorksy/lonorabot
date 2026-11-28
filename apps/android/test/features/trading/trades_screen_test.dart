// «الصفقات»: the agent's positions with edit and close, its pending orders with cancel, the
// order log; every order behind a review the owner confirms. The fake API answers every
// execute; nothing reaches a server.
//
// Regenerate goldens with: flutter test --update-goldens test/features/trading
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FButton;
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/features/trading/trade_rules.dart';
import 'package:lonora/features/trading/trade_widgets.dart';
import 'package:lonora/features/trading/trades_data.dart';
import 'package:lonora/features/trading/trades_screen.dart';

import 'trade_harness.dart';

Future<void> _pump(
  WidgetTester tester, {
  String agent = 'a-gold',
  String locale = 'ar',
  Brightness brightness = Brightness.light,
  double textScale = 1,
}) async {
  await pumpWpf(
    tester,
    TradesScreen(agentId: agent),
    locale: locale,
    brightness: brightness,
    store: tradeStore(locale: locale),
    textScale: textScale,
  );
}

Finder _text(String t) => find.text(t);

/// Opens the close review of the first position card and returns its confirm button.
Future<Finder> _openClose(
  WidgetTester tester, {
  String label = 'إغلاق الصفقة',
}) async {
  await tapAndSettle(tester, find.widgetWithText(FButton, label).first);
  return buttonLabelled(label);
}

void main() {
  setUpAll(setUpWpf);
  setUp(resetTrades);

  testWidgets(
    'positions of the agent\'s symbol, its pending order and the order log',
    (tester) async {
      scriptTrades();
      await _pump(tester, locale: 'en');
      expect(find.text('Trades'), findsOneWidget);
      // Only XAUUSD: the EURUSD position is another market.
      expect(find.byType(PositionCard), findsOneWidget);
      expect(find.text('XAUUSD'), findsWidgets);
      expect(find.textContaining('EURUSD'), findsNothing);
      expect(find.textContaining('Lonora Sim'), findsWidgets);
      // A missing level reads «—» (the position's and its pending order's target).
      expect(
        find.bySemanticsLabel(RegExp(r'^Take profit: .*—')),
        findsNWidgets(2),
      );
      expect(
        find.bySemanticsLabel(RegExp(r'^Stop loss: .*2365\.00')),
        findsOneWidget,
      );
      await scrollTo(tester, find.byType(PendingOrderCard));
      expect(find.textContaining('Buy limit'), findsOneWidget);
      await scrollTo(tester, find.text('Order log'));
      await scrollTo(tester, find.textContaining('shows only with the broker'));
      expect(find.byType(OrderLogRow), findsNWidgets(5));
      // A partial fill shows the executed size over the asked one; a fill its price only.
      expect(find.textContaining('0.2 / 0.5'), findsOneWidget);
      Finder inLog(String text) => find.descendant(
        of: find.byType(OrderLogRow),
        matching: find.textContaining(text),
      );
      expect(inLog('2380.50'), findsOneWidget);
      // A placed limit order (accepted) and a rejection show no price.
      expect(inLog('2350.00'), findsNothing);
      expect(find.text('Partly filled'), findsOneWidget);
      expect(find.text('Rejected'), findsOneWidget);
      expect(find.text('Unconfirmed'), findsOneWidget);
      expect(find.text('Accepted by the broker'), findsOneWidget);
      expect(
        find.text(
          "«Filled» shows only with the broker's evidence or your confirmation.",
        ),
        findsOneWidget,
      );
      expect(tradeApi.calls.where((c) => c.method != 'GET'), isEmpty);
      await unmount(tester);
    },
  );

  testWidgets('an agent without an account, and the empty states', (
    tester,
  ) async {
    scriptTrades();
    await _pump(tester, agent: 'a-none');
    expect(_text('لم يُختر حساب تداول لهذا الوكيل.'), findsOneWidget);
    await unmount(tester);
    scriptTrades(connections: const []);
    await _pump(tester, agent: 'a-none');
    expect(_text('اربط حساب تداول أولًا من الإعدادات.'), findsOneWidget);
    await unmount(tester);
    scriptTrades(
      account: accountState(positions: const [], orders: const []),
      journal: const [],
    );
    await _pump(tester);
    expect(_text('لا توجد صفقة مفتوحة.'), findsOneWidget);
    expect(_text('لا توجد أوامر معلقة'), findsOneWidget);
    expect(_text('لا أوامر بعد.'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('a failed read says why; offline reads the network text', (
    tester,
  ) async {
    scriptTrades();
    tradeApi
      ..on('GET /trading/accounts/acct-1', (_, _) => throw ApiError.network())
      ..on(
        'GET /trading/journal',
        (_, _) =>
            throw ApiError(status: 503, code: 'broker_connection_unavailable'),
      );
    await _pump(tester);
    expect(
      _text('تعذر الاتصال بالخادم. تحقق من العنوان والشبكة.'),
      findsOneWidget,
    );
    expect(_text('الاتصال بالوسيط غير متاح.'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets(
    'close: Cancel, Back and the barrier send nothing; confirm sends one order',
    (tester) async {
      scriptTrades();
      tradeApi.on(
        'POST /trading/execute',
        (body, _) => executorAnswer(
          body,
          'confirmed',
          details: {
            'verification': {'status': 'verified'},
          },
        ),
      );
      await _pump(tester);
      await _openClose(tester);
      // The review: account and kind, symbol, side, volume, at the market price.
      expect(find.textContaining('تُغلق الصفقة على'), findsOneWidget);
      expect(
        find.bySemanticsLabel(RegExp(r'^الحساب: .*Lonora Sim.*المحاكاة')),
        findsOneWidget,
      );
      expect(find.bySemanticsLabel(RegExp(r'^الاتجاه: شراء')), findsOneWidget);
      expect(find.bySemanticsLabel(RegExp(r'^الحجم: .*0\.10')), findsWidgets);
      // A simulation: no live-money warning.
      expect(find.textContaining('أموال حقيقية'), findsNothing);
      await tapAndSettle(tester, buttonLabelled('إلغاء'));
      expect(tradeApi.executed, isEmpty);
      await _openClose(tester);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(tradeApi.executed, isEmpty);
      await _openClose(tester);
      await tester.tapAt(const Offset(200, 40));
      await tester.pumpAndSettle();
      expect(tradeApi.executed, isEmpty);
      expect(find.byType(TradesScreen), findsOneWidget);

      await tapAndSettle(tester, await _openClose(tester));
      final body = tradeApi.executed.single;
      expect(body, {
        'account_id': 'acct-1',
        'action': 'close_position',
        'symbol': 'XAUUSD',
        'position_id': 'p-1',
        'operation_id': body['operation_id'],
      });
      expect(body['operation_id'], isA<String>());
      // The confirmed close is announced; the card says it under its buttons.
      expect(find.textContaining('مؤكد'), findsWidgets);
      await settleToasts(tester);
      await unmount(tester);
    },
  );

  testWidgets(
    'a double tap on the confirm sends one order and keeps the page',
    (tester) async {
      scriptTrades();
      tradeApi.on(
        'POST /trading/execute',
        (body, _) => executorAnswer(body, 'submitted'),
      );
      await _pump(tester);
      final confirm = await _openClose(tester);
      await tester.tap(confirm);
      await tester.pump(const Duration(milliseconds: 16));
      await tester.tap(confirm, warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(tradeApi.executed, hasLength(1));
      expect(find.byType(TradesScreen), findsOneWidget);
      // Unsettled: it is not sent again under a new identity (the card and its toast say
      // so), and the button checks.
      expect(
        find.textContaining('لن تُرسل هذه العملية مرة أخرى.'),
        findsWidgets,
      );
      expect(
        find.widgetWithText(FButton, 'تحقق من نتيجة الإغلاق'),
        findsOneWidget,
      );
      await settleToasts(tester);
      await unmount(tester);
    },
  );

  testWidgets(
    'no answer: the alert says to check first; the check resends the same bytes',
    (tester) async {
      scriptTrades();
      var n = 0;
      tradeApi.on('POST /trading/execute', (body, _) {
        if (++n == 1) throw ApiError.network('timeout');
        return executorAnswer(body, 'confirmed');
      });
      await _pump(tester);
      await tapAndSettle(tester, await _openClose(tester));
      expect(
        _text(
          'لم يُجب خادم لونورا في الوقت المحدد. إن كان هذا أمرًا، فراجع صفقاتك قبل أن تحاول مجددًا.',
        ),
        findsOneWidget,
      );
      expect(_text('تعذر تنفيذ الطلب. حاول مرة أخرى.'), findsNothing);
      // A remount keeps the held identity.
      await unmount(tester);
      await _pump(tester);
      await tapAndSettle(
        tester,
        await _openClose(tester, label: 'تحقق من نتيجة الإغلاق'),
      );
      expect(tradeApi.executed, hasLength(2));
      expect(
        jsonEncode(tradeApi.executed[1]),
        jsonEncode(tradeApi.executed[0]),
      );
      expect(
        OrderDesk.instance.held(
          testScope,
          heldKey('close_position', 'acct-1', 'p-1'),
        ),
        isNull,
      );
      await settleToasts(tester);
      await unmount(tester);
    },
  );

  testWidgets(
    'leaving and coming back during a close keeps it busy and sends nothing more',
    (tester) async {
      scriptTrades();
      final answer = pendingAnswer();
      tradeApi.on('POST /trading/execute', (_, _) => answer.future);
      await _pump(tester);
      final confirm = await _openClose(tester);
      await tester.tap(confirm);
      // The send is in flight (its spinner never settles): pump, never settle.
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(tradeApi.executed, hasLength(1));
      await unmount(tester);
      await pumpWpf(
        tester,
        const TradesScreen(agentId: 'a-gold'),
        store: tradeStore(),
        settle: false,
      );
      final close = find.widgetWithText(FButton, 'تحقق من نتيجة الإغلاق');
      expect(close, findsOneWidget);
      await tester.tap(close);
      for (var i = 0; i < 6; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      // Busy: the tap opens no review and sends nothing.
      expect(find.textContaining('تُغلق الصفقة على'), findsNothing);
      expect(tradeApi.executed, hasLength(1));
      answer.complete(executorAnswer(tradeApi.executed.single, 'confirmed'));
      await flush(tester);
      await tester.pumpAndSettle();
      expect(find.textContaining('مؤكد'), findsWidgets);
      expect(find.widgetWithText(FButton, 'إغلاق الصفقة'), findsOneWidget);
      await settleToasts(tester);
      await unmount(tester);
    },
  );
  testWidgets(
    'a boundary refusal says why; a post-send rejection is not «not sent again»',
    (tester) async {
      scriptTrades();
      tradeApi.on(
        'POST /trading/execute',
        (_, _) =>
            throw ApiError(status: 409, code: 'broker_observation_unavailable'),
      );
      await _pump(tester);
      await tapAndSettle(tester, await _openClose(tester));
      expect(
        find.textContaining('تعذّر التحقق من حالة حساب الوسيط'),
        findsOneWidget,
      );
      // A 4xx journaled nothing and every send was answered: the identity is released.
      expect(find.widgetWithText(FButton, 'إغلاق الصفقة'), findsOneWidget);
      tradeApi.on(
        'POST /trading/execute',
        (body, _) => executorAnswer(
          body,
          'failed',
          code: 'broker_order_rejected',
          details: {'description': 'Market closed'},
        ),
      );
      await tapAndSettle(tester, await _openClose(tester));
      expect(find.textContaining('رفض الوسيط هذا الأمر.'), findsWidgets);
      expect(find.textContaining('Market closed'), findsWidgets);
      expect(
        find.textContaining('لن تُرسل هذه العملية مرة أخرى.'),
        findsNothing,
      );
      await settleToasts(tester);
      await unmount(tester);
    },
  );

  testWidgets(
    'edit: Save waits for a change; an emptied stop clears it, reviewed old → new',
    (tester) async {
      scriptTrades();
      tradeApi.on(
        'POST /trading/execute',
        (body, _) => executorAnswer(body, 'confirmed'),
      );
      await _pump(tester);
      await tapAndSettle(
        tester,
        find.widgetWithText(FButton, 'تعديل الوقف والهدف'),
      );
      final save = buttonLabelled('حفظ');
      await tester.pumpAndSettle();
      expect(tester.widget<FButton>(save).onPress, isNull);
      final fields = find.byType(TextField);
      await tester.enterText(fields.first, '');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, buttonLabelled('حفظ'));
      // The review: «2365.00 → —».
      expect(
        find.bySemanticsLabel(RegExp(r'^وقف الخسارة: .*2365\.00 → —')),
        findsOneWidget,
      );
      await tapAndSettle(tester, buttonLabelled('حفظ'));
      final body = tradeApi.executed.single;
      expect(body['clear_stop_loss'], isTrue);
      expect(body.containsKey('stop_loss'), isFalse);
      expect(body.containsKey('take_profit'), isFalse);
      expect(body['action'], 'modify_position');
      await settleToasts(tester);
      await unmount(tester);
    },
  );

  testWidgets('edit: a value off the tick is refused before any send', (
    tester,
  ) async {
    scriptTrades();
    await _pump(tester, locale: 'en');
    await tapAndSettle(
      tester,
      find.widgetWithText(FButton, 'Edit stop and target'),
    );
    await tester.enterText(find.byType(TextField).first, '2370.005');
    await tester.pumpAndSettle();
    await tapAndSettle(tester, buttonLabelled('Save'));
    expect(find.text('The price must be a multiple of 0.01.'), findsOneWidget);
    expect(tradeApi.executed, isEmpty);
    await unmount(tester);
  });

  testWidgets(
    'same values after a dropped send reuse the identity; new values a new one',
    (tester) async {
      scriptTrades();
      tradeApi.on('POST /trading/execute', (_, _) => throw ApiError.network());
      await _pump(tester, locale: 'en');
      Future<void> edit(String stop) async {
        await tapAndSettle(
          tester,
          find.widgetWithText(FButton, 'Edit stop and target'),
        );
        await tester.enterText(find.byType(TextField).first, stop);
        await tester.pumpAndSettle();
        await tapAndSettle(tester, buttonLabelled('Save'));
        await tapAndSettle(
          tester,
          buttonLabelled(
            find.text('Check existing operation').evaluate().isEmpty
                ? 'Save'
                : 'Check existing operation',
          ),
        );
      }

      await edit('2370');
      await edit('2370');
      await edit('2375');
      final ids = [for (final b in tradeApi.executed) b['operation_id']];
      expect(ids[1], ids[0]);
      expect(ids[2], isNot(ids[0]));
      await unmount(tester);
    },
  );

  testWidgets('a live account warns in every review', (tester) async {
    scriptTrades();
    await _pump(tester, agent: 'a-live', locale: 'en');
    expect(find.textContaining('Demo Broker'), findsWidgets);
    await tapAndSettle(
      tester,
      find.widgetWithText(FButton, 'Close the trade').first,
    );
    expect(find.textContaining('may execute with real money'), findsOneWidget);
    expect(
      find.bySemanticsLabel(RegExp(r'^Account: .*Broker account')),
      findsOneWidget,
    );
    await tapAndSettle(tester, buttonLabelled('Cancel'));
    expect(tradeApi.executed, isEmpty);
    await unmount(tester);
  });

  testWidgets('trading not allowed: every order is off, and says why', (
    tester,
  ) async {
    scriptTrades(account: accountState(tradeAllowed: false));
    await _pump(tester);
    expect(
      _text('لا يسمح حساب الوسيط هذا بالتداول. تحقق من صلاحياته.'),
      findsOneWidget,
    );
    for (final label in ['تعديل الوقف والهدف', 'إغلاق الصفقة']) {
      expect(
        tester.widget<FButton>(find.widgetWithText(FButton, label)).onPress,
        isNull,
      );
    }
    await scrollTo(tester, find.byType(PendingOrderCard));
    expect(
      tester
          .widget<FButton>(find.widgetWithText(FButton, 'إلغاء الأمر'))
          .onPress,
      isNull,
    );
    await unmount(tester);
  });

  testWidgets(
    'the broker cannot be verified: exits stay, a widened stop is refused',
    (tester) async {
      scriptTrades(
        connections: [
          {
            ...simConnection,
            'state': {
              ...asJson(simConnection['state']),
              'broker_recovery': {
                'status': 'disconnected',
                'reason_code': 'broker_connection_lost',
              },
            },
          },
        ],
      );
      tradeApi.on(
        'POST /trading/execute',
        (body, _) => executorAnswer(body, 'confirmed'),
      );
      await _pump(tester, locale: 'en');
      expect(
        find.textContaining('new orders and protection changes are paused'),
        findsOneWidget,
      );
      await tapAndSettle(
        tester,
        find.widgetWithText(FButton, 'Edit stop and target'),
      );
      await tester.enterText(find.byType(TextField).first, '2360');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, buttonLabelled('Save'));
      expect(
        find.textContaining('only moving the stop loss toward the price'),
        findsWidgets,
      );
      expect(tradeApi.executed, isEmpty);
      await tester.enterText(find.byType(TextField).first, '2370');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, buttonLabelled('Save'));
      await tapAndSettle(tester, buttonLabelled('Save'));
      expect(tradeApi.executed.single['stop_loss'], '2370');
      await settleToasts(tester);
      await unmount(tester);
    },
  );

  testWidgets('cancel a pending order after its review', (tester) async {
    scriptTrades();
    tradeApi.on(
      'POST /trading/execute',
      (body, _) => executorAnswer(body, 'confirmed'),
    );
    await _pump(tester, locale: 'en');
    await scrollTo(tester, find.byType(PendingOrderCard));
    await tapAndSettle(tester, find.widgetWithText(FButton, 'Cancel order'));
    // The card and its review both name the order's kind.
    expect(
      find.bySemanticsLabel(RegExp(r'^Type: Buy limit')),
      findsNWidgets(2),
    );
    expect(
      find.bySemanticsLabel(RegExp(r'^Order price: .*2350\.00')),
      findsNWidgets(2),
    );
    await tapAndSettle(tester, buttonLabelled('Cancel order'));
    expect(tradeApi.executed.single, {
      'account_id': 'acct-1',
      'action': 'cancel_order',
      'symbol': 'XAUUSD',
      'order_id': 'o-7',
      'operation_id': tradeApi.executed.single['operation_id'],
    });
    await settleToasts(tester);
    await unmount(tester);
  });

  testWidgets(
    'after a reload the card reports the newest edit or close by submitted_at',
    (tester) async {
      scriptTrades(
        journal: [
          journalRow(
            'op-old',
            action: 'close_position',
            status: 'failed',
            agentId: null,
            extraRequest: {'position_id': 'p-1'},
            result: {'code': 'position_not_found'},
            submitted: '2026-11-27T07:00:00Z',
            updated: '2026-11-27T09:59:00Z',
          ),
          journalRow(
            'op-new',
            action: 'modify_position',
            status: 'confirmed',
            agentId: null,
            extraRequest: {'position_id': 'p-1', 'stop_loss': '2370'},
            verification: 'pending',
            submitted: '2026-11-27T08:00:00Z',
            updated: '2026-11-27T08:00:01Z',
          ),
        ],
      );
      await _pump(tester);
      expect(find.textContaining('بانتظار تأكيد الوسيط'), findsOneWidget);
      // The owner's own rows are not the agent's order log.
      await scrollTo(tester, _text('لا أوامر بعد.'));
      expect(_text('لا أوامر بعد.'), findsOneWidget);
      await unmount(tester);
    },
  );

  testWidgets('an operation event reads the account and the journal again', (
    tester,
  ) async {
    scriptTrades();
    await _pump(tester);
    final before = tradeApi.callsTo('GET', '/trading/journal').length;
    fakeRealtime.emit('trading.operation_updated', {'operation_id': 'op-1'});
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    expect(tradeApi.callsTo('GET', '/trading/journal').length, before + 1);
    expect(tradeApi.callsTo('GET', '/trading/accounts/acct-1').length, 2);
    await unmount(tester);
  });

  testWidgets('48 dp targets, labelled buttons, Arabic right to left', (
    tester,
  ) async {
    scriptTrades();
    await _pump(tester);
    expect(
      Directionality.of(tester.element(find.byType(PositionCard))),
      TextDirection.rtl,
    );
    for (final button in find.byType(FButton).evaluate()) {
      final box = button.renderObject! as RenderBox;
      expect(box.size.height, greaterThanOrEqualTo(48));
    }
    expect(find.bySemanticsLabel('إغلاق الصفقة'), findsOneWidget);
    expect(find.bySemanticsLabel('تعديل الوقف والهدف'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('text scale 1.3 does not overflow', (tester) async {
    scriptTrades();
    await _pump(tester, textScale: 1.3);
    expect(tester.takeException(), isNull);
    await scrollTo(tester, find.text('سجل الأوامر'), delta: 300);
    expect(tester.takeException(), isNull);
    await unmount(tester);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      scriptTrades();
      await withRealShadows(() async {
        await _pump(tester, locale: v.locale, brightness: v.brightness);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/trades_${v.name}.png'),
        );
      });
      await unmount(tester);
    });
  }

  testWidgets('golden order log (light, ar)', (tester) async {
    scriptTrades();
    await withRealShadows(() async {
      await _pump(tester);
      await scrollTo(tester, find.textContaining('بدليل من الوسيط'));
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/trades_log_light_ar.png'),
      );
    });
    await unmount(tester);
  });

  testWidgets('golden close review (live account)', (tester) async {
    scriptTrades();
    await withRealShadows(() async {
      await _pump(tester, agent: 'a-live');
      await tapAndSettle(
        tester,
        find.widgetWithText(FButton, 'إغلاق الصفقة').first,
      );
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/trades_close_review_ar.png'),
      );
    });
    await unmount(tester);
  });

  testWidgets('golden edit sheet (dark, en)', (tester) async {
    scriptTrades();
    await withRealShadows(() async {
      await _pump(tester, locale: 'en', brightness: Brightness.dark);
      await tapAndSettle(
        tester,
        find.widgetWithText(FButton, 'Edit stop and target'),
      );
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/trades_edit_dark_en.png'),
      );
    });
    await unmount(tester);
  });
}
