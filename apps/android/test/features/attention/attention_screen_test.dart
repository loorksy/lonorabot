// «يحتاج انتباهك»: grouping by urgency and by agent, unseen dots, seen marking on open (never for
// a waiting question), opening the conversation, empty / error states; goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/attention
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/avatar/avatar.dart';
import 'package:lonora/features/attention/attention_screen.dart';
import 'package:lonora/features/chats/chat_text.dart' show chatClock;

import '../market/wpf_harness.dart';

final viewFixture = <Json>[
  {
    'kind': 'trade_approval',
    'id': 'n-1',
    'agent_id': 'a-gold',
    'thread_id': 't-gold',
    'code': 'approval_required',
    'symbol': 'XAUUSD',
    'seen': false,
    'created_at': '2026-11-27T09:12:00Z',
  },
  {
    'kind': 'owner_question',
    'id': 'q-1',
    'agent_id': 'a-research',
    'thread_id': 't-research',
    'code': null,
    'run_id': 'r-1',
    'seen': false,
    'created_at': '2026-11-27T08:40:00Z',
  },
  {
    'kind': 'broker_health',
    'id': 'n-2',
    'agent_id': 'a-lonora',
    'thread_id': 't-lonora',
    'code': 'broker_connection_lost',
    'seen': true,
    'created_at': '2026-11-26T22:05:00Z',
  },
  {
    'kind': 'agent_alert',
    'id': 'n-3',
    'agent_id': 'a-research',
    'thread_id': 't-research',
    'code': 'agent_notification',
    'summary': 'تقرير التضخم الأمريكي صدر أعلى من المتوقع؛ راجعت السيناريوهات.',
    'seen': false,
    'created_at': '2026-11-27T07:30:00Z',
  },
  {
    'kind': 'background_health',
    'id': 'n-4',
    'agent_id': 'a-lonora',
    'thread_id': 't-lonora',
    'code': 'model_access_failed',
    'reason': 'billing',
    'provider_name': 'OpenAI',
    'seen': false,
    'created_at': '2026-11-27T06:00:00Z',
  },
];

void scriptAttention([List<Json>? rows]) {
  fakeApi
    ..on('GET /attention/view', (_, _) => rows ?? viewFixture)
    ..on('GET /attention', (_, _) => [])
    ..on(
      'POST /attention/seen',
      (body, _) => {'id': (body! as Map)['notification_id']},
    );
}

void main() {
  setUpAll(setUpWpf);
  setUp(() async {
    await resetWpf();
    // The fixture's day: today's items show the clock, yesterday's its weekday.
    chatClock = () => DateTime.utc(2026, 11, 27, 12);
  });
  tearDown(() => chatClock = DateTime.now);

  test('urgency of each kind and group order', () {
    expect(urgencyOf('mandate_card'), AttentionUrgency.decision);
    expect(urgencyOf('owner_question'), AttentionUrgency.decision);
    expect(urgencyOf('broker_health'), AttentionUrgency.health);
    expect(urgencyOf('agent_alert'), AttentionUrgency.alert);
    expect(urgencyOf('something_new'), AttentionUrgency.alert);
    final byUrgency = groupRows(viewFixture, AttentionGrouping.urgency);
    expect([for (final g in byUrgency) g.$1], ['decision', 'health', 'alert']);
    expect([for (final r in byUrgency[1].$2) r['id']], ['n-4', 'n-2']);
    final byAgent = groupRows(viewFixture, AttentionGrouping.agent);
    expect(
      [for (final g in byAgent) g.$1],
      ['a-gold', 'a-research', 'a-lonora'],
    );
  });

  testWidgets('groups by urgency with Lonora labels', (tester) async {
    scriptAttention();
    await pumpWpf(tester, const AttentionScreen(), locale: 'en');
    expect(find.text('Needs your attention'), findsOneWidget);
    expect(find.text('Waiting for your decision'), findsOneWidget);
    expect(find.text('Waiting for approval'), findsOneWidget);
    expect(find.text('A question is waiting for your answer'), findsOneWidget);
    expect(find.text('Credit spent or plan ended at OpenAI'), findsOneWidget);
    expect(find.text('Service health'), findsOneWidget);
    await scrollTo(tester, find.text('Agent alerts'));
    expect(find.textContaining('تقرير التضخم'), findsOneWidget);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, 800));
    await tester.pumpAndSettle();
    await tapAndSettle(tester, find.text('By agent'));
    expect(find.text('Gold desk'), findsOneWidget);
    expect(find.text('Lonora'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('an older item shows the chat list\'s date', (tester) async {
    scriptAttention();
    await pumpWpf(tester, const AttentionScreen(), locale: 'en');
    // cc:C10: yesterday reads as its weekday, as in the chats list, not «26/11».
    expect(find.textContaining('Thursday'), findsOneWidget);
    expect(find.textContaining('26/11'), findsNothing);
    await unmount(tester);
  });

  testWidgets('section headers start at the rows\' avatars', (tester) async {
    scriptAttention();
    await pumpWpf(tester, const AttentionScreen(), locale: 'en');
    // cc:C7: the header and the avatars below it share the list's 24 dp inset.
    expect(
      tester.getRect(find.text('Waiting for your decision')).left,
      tester.getRect(find.byType(LonoraAvatar).first).left,
    );
    await unmount(tester);
  });

  testWidgets('opening an item marks it seen and opens its conversation', (
    tester,
  ) async {
    scriptAttention();
    final store = wpfStore(locale: 'en', attentionView: viewFixture);
    await pumpWpf(tester, const AttentionScreen(), locale: 'en', store: store);
    expect(store.state.shell.attentionUnseen, 4);
    await tapAndSettle(tester, find.text('Waiting for approval'));
    expect(fakeApi.callsTo('POST', '/attention/seen').single.body, {
      'notification_id': 'n-1',
    });
    expect(shownRoute(tester), '/chats/thread/t-gold');
    expect(store.state.shell.attentionUnseen, 3);
    // Nothing is decided by opening it.
    expect(
      fakeApi.calls.where(
        (c) => c.method == 'POST' && c.path != '/attention/seen',
      ),
      isEmpty,
    );
    await unmount(tester);
  });

  testWidgets('a waiting question is not marked seen', (tester) async {
    scriptAttention();
    await pumpWpf(tester, const AttentionScreen(), locale: 'en');
    await tapAndSettle(
      tester,
      find.text('A question is waiting for your answer'),
    );
    expect(fakeApi.callsTo('POST', '/attention/seen'), isEmpty);
    expect(shownRoute(tester), '/chats/thread/t-research');
    await unmount(tester);
  });

  testWidgets('a group conversation row opens that conversation', (
    tester,
  ) async {
    scriptAttention([
      {
        'kind': 'agent_alert',
        'id': 'n-9',
        'agent_id': 'a-gold',
        'thread_id': 't-group',
        'group_id': 'g-1',
        'code': 'agent_notification',
        'summary': 'Desk sync',
        'seen': false,
        'created_at': '2026-11-27T09:00:00Z',
      },
    ]);
    await pumpWpf(tester, const AttentionScreen(), locale: 'en');
    await tapAndSettle(tester, find.text('Desk sync'));
    expect(fakeApi.callsTo('POST', '/attention/seen').single.body, {
      'notification_id': 'n-9',
    });
    expect(shownRoute(tester), '/chats/thread/t-group');
    await unmount(tester);
  });

  testWidgets('a run waiting for the owner reads the view again', (
    tester,
  ) async {
    scriptAttention();
    await pumpWpf(tester, const AttentionScreen(), locale: 'en');
    fakeApi.calls.clear();
    // Attention events refresh the shell snapshot already (RealtimeController): no
    // second read from the screen.
    fakeRealtime
      ..emit('attention.updated')
      ..emit('owner_action.updated')
      ..emit('trading.approval.updated');
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(fakeApi.calls, isEmpty);
    fakeRealtime.emit('run.waiting_input');
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('GET', '/attention/view'), hasLength(1));
    await unmount(tester);
  });

  testWidgets('switching the grouping clicks like a segmented step', (
    tester,
  ) async {
    scriptAttention();
    final haptics = <Object?>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'HapticFeedback.vibrate') {
          haptics.add(call.arguments);
        }
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );
    await pumpWpf(tester, const AttentionScreen(), locale: 'en');
    await tapAndSettle(tester, find.text('By agent'));
    expect(haptics, contains('HapticFeedbackType.selectionClick'));
    await unmount(tester);
  });

  testWidgets('nothing waiting', (tester) async {
    scriptAttention(const []);
    await pumpWpf(tester, const AttentionScreen(), locale: 'en');
    expect(find.text('Nothing needs you right now.'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('a failed first read offers a retry', (tester) async {
    fakeApi.on('GET /attention/view', (_, _) => throw ApiError.network());
    await pumpWpf(tester, const AttentionScreen(), locale: 'en');
    expect(find.text('Retry'), findsOneWidget);
    scriptAttention();
    await tapAndSettle(tester, find.text('Retry'));
    expect(find.text('Waiting for approval'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('text scale 1.3 does not overflow', (tester) async {
    scriptAttention();
    await pumpWpf(tester, const AttentionScreen(), textScale: 1.3);
    expect(tester.takeException(), isNull);
    await unmount(tester);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      scriptAttention();
      await withRealShadows(() async {
        await pumpWpf(
          tester,
          const TabFrame(index: -1, child: AttentionScreen()),
          brightness: v.brightness,
          locale: v.locale,
          store: wpfStore(locale: v.locale, attentionView: viewFixture),
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/attention_${v.name}.png'),
        );
      });
      await unmount(tester);
    });
  }

  testWidgets('golden empty', (tester) async {
    scriptAttention(const []);
    await pumpWpf(
      tester,
      const TabFrame(index: -1, child: AttentionScreen()),
      locale: 'ar',
    );
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/attention_empty_ar.png'),
    );
    await unmount(tester);
  });
}
