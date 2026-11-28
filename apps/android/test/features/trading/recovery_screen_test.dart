// «التعطل والاستعادة» (RecoveryPage.tsx): each connection's `state.broker_recovery`, the
// details sheet, «إعادة المحاولة» (reads only), the `?account=` narrowing and the refresh on a
// broker event. Nothing here ever writes.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FButton;
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/features/settings/settings_common.dart'
    show SettingsSkeleton;
import 'package:lonora/features/trading/recovery_screen.dart';

import 'trade_harness.dart';

Json _connection(String id, String? status, {String provider = 'metaapi'}) => {
  'id': id,
  'version': 1,
  'payload': {'provider': provider, 'account_id': id, 'enabled': true},
  'state': {
    'broker_identity': {
      'broker': 'Broker $id',
      'login': '10$id',
      'server': 'Srv',
      'connection_version': 1,
    },
    if (status != null)
      'broker_recovery': {
        'status': status,
        'reason_code': 'broker_connection_lost',
        'since': '2026-11-27T08:15:00Z',
        'observed_at': '2026-11-27T09:00:00Z',
        'last_success_at': status == 'reconciling'
            ? null
            : '2026-11-27T08:14:00Z',
        'unresolved_operations': ['op-1', 'op-2'],
        'revision': 3,
      },
  },
};

Future<void> _pump(
  WidgetTester tester, {
  String locale = 'ar',
  String? account,
  Brightness brightness = Brightness.light,
  bool settle = true,
}) => pumpWpf(
  tester,
  RecoveryScreen(account: account),
  locale: locale,
  brightness: brightness,
  store: tradeStore(locale: locale),
  settle: settle,
).then((_) {});

void main() {
  setUpAll(setUpWpf);
  setUp(resetTrades);

  testWidgets('nothing down: the broker is connected', (tester) async {
    tradeApi.on(
      'GET /trading/connections',
      (_, _) => [
        _connection('1', 'connected'),
        _connection('2', null),
        _connection('3', 'degraded')..remove('state'),
      ],
    );
    await _pump(tester);
    expect(find.text('التعطل والاستعادة'), findsOneWidget);
    expect(find.text('الاتصال بالوسيط سليم'), findsOneWidget);
    expect(
      find.text('كل حسابات التداول المرتبطة تستجيب طبيعيًا. لا شيء موقوف.'),
      findsOneWidget,
    );
    await unmount(tester);
  });

  testWidgets('each down status by its name; several accounts are labelled', (
    tester,
  ) async {
    tradeApi.on(
      'GET /trading/connections',
      (_, _) => [
        _connection('1', 'recovering'),
        _connection('2', 'reconciling'),
        _connection('3', 'disconnected'),
        _connection('4', 'degraded'),
        _connection('5', 'connected'),
      ],
    );
    await _pump(tester, locale: 'en');
    expect(find.text('The broker connection dropped'), findsOneWidget);
    expect(
      find.text(
        'Affected execution stops until the connection is restored and checked.',
      ),
      findsOneWidget,
    );
    expect(find.text('Reconnecting'), findsOneWidget);
    expect(find.text('Checking with the broker'), findsOneWidget);
    expect(find.text('Paused for now'), findsNWidgets(2));
    expect(find.text('Execution state'), findsNWidgets(4));
    expect(find.textContaining('Broker 5'), findsNothing);
    expect(find.textContaining('Broker 1'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('?account narrows it to one connection', (tester) async {
    tradeApi.on(
      'GET /trading/connections',
      (_, _) => [
        _connection('1', 'recovering'),
        _connection('2', 'disconnected'),
      ],
    );
    await _pump(tester, account: '2');
    expect(find.text('متوقف مؤقتًا'), findsOneWidget);
    expect(find.text('جارٍ إعادة الاتصال'), findsNothing);
    // One account: no label under the state.
    expect(find.textContaining('Broker 2'), findsNothing);
    await unmount(tester);
  });

  testWidgets(
    'the details: account, since, last read («—» when none), reason, count',
    (tester) async {
      tradeApi.on(
        'GET /trading/connections',
        (_, _) => [_connection('1', 'reconciling')],
      );
      await _pump(tester, locale: 'en');
      await tapAndSettle(tester, find.widgetWithText(FButton, 'State details'));
      expect(find.text('State details'), findsWidgets);
      expect(
        find.bySemanticsLabel(RegExp(r'^Account: .*Broker 1')),
        findsOneWidget,
      );
      expect(find.bySemanticsLabel(RegExp(r'^Since: .*2026')), findsOneWidget);
      expect(find.bySemanticsLabel('Last successful read: —'), findsOneWidget);
      expect(
        find.bySemanticsLabel(RegExp(r'^Reason: .*broker_connection_lost')),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel(
          RegExp(r'^Operations awaiting confirmation: .*2'),
        ),
        findsOneWidget,
      );
      await unmount(tester);
    },
  );

  testWidgets(
    'Try again reads each down account, then the connections, and says so',
    (tester) async {
      var reads = 0;
      tradeApi
        ..on('GET /trading/connections', (_, _) {
          reads++;
          return [
            _connection('1', 'disconnected'),
            _connection('2', 'recovering'),
          ];
        })
        ..on(
          'GET /trading/accounts/1',
          (_, _) => throw ApiError(
            status: 503,
            code: 'broker_connection_unavailable',
          ),
        )
        ..on('GET /trading/accounts/2', (_, _) => accountState(id: '2'));
      await _pump(tester);
      await tapAndSettle(
        tester,
        find.widgetWithText(FButton, 'إعادة المحاولة'),
      );
      final paths = [for (final c in tradeApi.calls) c.path];
      expect(paths.where((p) => p.startsWith('/trading/accounts/')), [
        '/trading/accounts/1',
        '/trading/accounts/2',
      ]);
      expect(
        paths.lastIndexOf('/trading/connections'),
        greaterThan(paths.indexOf('/trading/accounts/2')),
      );
      expect(reads, 2);
      expect(
        find.text('أُعيدت المحاولة. تتحدّث الحالة عندما يستجيب الوسيط.'),
        findsOneWidget,
      );
      expect(tradeApi.calls.where((c) => c.method != 'GET'), isEmpty);
      await settleToasts(tester);
      await unmount(tester);
    },
  );

  testWidgets('loading, a failed read with its retry, and a broker event', (
    tester,
  ) async {
    var fail = true;
    tradeApi.on('GET /trading/connections', (_, _) {
      if (fail) throw ApiError.network();
      return [_connection('1', 'disconnected')];
    });
    await _pump(tester);
    expect(
      find.text('تعذر الاتصال بالخادم. تحقق من العنوان والشبكة.'),
      findsOneWidget,
    );
    fail = false;
    await tapAndSettle(tester, find.text('إعادة المحاولة'));
    expect(find.text('انقطع اتصال الوسيط'), findsOneWidget);
    tradeApi.on(
      'GET /trading/connections',
      (_, _) => [_connection('1', 'connected')],
    );
    fakeRealtime.emit('broker.recovered', {'connection_id': '1'});
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    expect(find.text('الاتصال بالوسيط سليم'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('first read pending shows the skeleton', (tester) async {
    final never = pendingAnswer();
    tradeApi.on('GET /trading/connections', (_, _) => never.future);
    await _pump(tester, settle: false);
    expect(find.byType(SettingsSkeleton), findsOneWidget);
    expect(find.bySemanticsLabel('جارٍ التحميل'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('the heading is a header; buttons are 48 dp', (tester) async {
    tradeApi.on(
      'GET /trading/connections',
      (_, _) => [_connection('1', 'disconnected')],
    );
    await _pump(tester);
    final heading = tester.getSemantics(find.text('انقطع اتصال الوسيط'));
    expect(heading.flagsCollection.isHeader, isTrue);
    for (final b in find.byType(FButton).evaluate()) {
      expect(
        tester.getSize(find.byWidget(b.widget)).height,
        greaterThanOrEqualTo(48),
      );
    }
    await unmount(tester);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      tradeApi.on(
        'GET /trading/connections',
        (_, _) => [
          _connection('1', 'disconnected'),
          _connection('2', 'reconciling'),
        ],
      );
      await withRealShadows(() async {
        await _pump(tester, locale: v.locale, brightness: v.brightness);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/recovery_${v.name}.png'),
        );
      });
      await unmount(tester);
    });
  }

  testWidgets('golden connected (dark, ar)', (tester) async {
    tradeApi.on(
      'GET /trading/connections',
      (_, _) => [_connection('1', 'connected')],
    );
    await withRealShadows(() async {
      await _pump(tester, brightness: Brightness.dark);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/recovery_connected_dark_ar.png'),
      );
    });
    await unmount(tester);
  });
}
