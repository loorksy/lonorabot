// The agent profile hub: hero with live status and the three actions, configuration rows,
// routines, trading (Mandate summary, watches), stop / turn on, delete; goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/agent_profile
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/avatar/avatar.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/agents/agent_profile_screen.dart';
import 'package:lonora/state/app_state.dart';

import 'wpe_harness.dart';

const goldState = {
  'agent_id': 'a-gold',
  'state': 'idle',
  'phase': 'monitoring',
  'watch_count': 1,
  'watches': [
    {
      'kind': 'price',
      'symbol': 'XAUUSD',
      'condition': 'above',
      'level': '2400',
    },
  ],
  'pending_approval_count': 0,
  'trading_readiness': {
    'state': 'ask_me',
    'trading_mode': 'ask',
    'has_trading_account': true,
    'unresolved_count': 0,
  },
};

void scriptGold({bool voice = true}) {
  fakeApi
    ..on('GET /agents/a-gold/state', (_, _) => goldState)
    ..on('GET /voice/status', (_, _) => {'transport_configured': voice})
    ..on(
      'GET /routines',
      (_, _) => [
        {
          'id': 'r-1',
          'agent_id': 'a-gold',
          'title': 'Morning gold brief',
          'prompt': 'Summarize overnight gold moves before London opens.',
          'cron': '30 7 * * 1-5',
          'timezone': 'Asia/Riyadh',
          'enabled': true,
          'next_run_at': '2026-11-30T04:30:00+00:00',
        },
        {
          'id': 'r-2',
          'agent_id': 'a-gold',
          'title': 'Weekly review',
          'prompt': 'Review the week of trades.',
          'cron': '0 18 * * 5',
          'timezone': 'Asia/Riyadh',
          'enabled': false,
          'next_run_at': '2026-11-27T15:00:00+00:00',
        },
      ],
    )
    ..on(
      'GET /watches',
      (_, _) => [
        {
          'id': 'w-1',
          'agent_id': 'a-gold',
          'version': 1,
          'payload': {
            'kind': 'price',
            'symbol': 'XAUUSD',
            'condition': 'above',
            'level': '2400',
            'enabled': true,
            'expires_at': null,
          },
          'state': {'code': 'watch_active'},
        },
        {
          'id': 'w-2',
          'agent_id': 'a-gold',
          'version': 2,
          'payload': {
            'kind': 'price',
            'symbol': 'XAUUSD',
            'condition': 'below',
            'level': '2300',
            'enabled': false,
          },
          'state': {'code': 'watch_paused'},
        },
      ],
    );
}

/// The gold desk's one-to-one conversation in the inbox.
const goldInbox = [
  {'thread_id': 't-gold', 'agent_id': 'a-gold'},
];

void main() {
  setUpAll(setUpWpeHarness);
  setUp(resetWpe);

  testWidgets('shows the hub, its rows and the trading summary', (
    tester,
  ) async {
    scriptGold();
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    expect(find.text('Gold desk'), findsOneWidget);
    expect(find.text('Gold trader · XAUUSD'), findsOneWidget);
    expect(find.text('Message'), findsOneWidget);
    expect(find.text('Call'), findsOneWidget);
    expect(find.text('Settings'), findsOneWidget);
    expect(find.textContaining('Trade only XAUUSD.'), findsOneWidget);
    expect(find.textContaining('Morning gold brief'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Watches'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Trading mode: Ask'), findsOneWidget);
  });

  testWidgets('ma:C7 the «view all» list icon mirrors in Arabic', (
    tester,
  ) async {
    scriptGold();
    await pumpScreen(tester, const AgentProfileScreen(agentId: 'a-gold'));
    final icon = find.byIcon(LnIcons.listChecks);
    await tester.scrollUntilVisible(
      icon,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(LnIcons.listChecks.matchTextDirection, isTrue);
    expect(Directionality.of(tester.element(icon)), TextDirection.rtl);
  });

  testWidgets('Message opens the agent conversation', (tester) async {
    scriptGold();
    fakeApi.on(
      'POST /agents/a-gold/conversation',
      (_, _) => {'id': 't-gold', 'agent_id': 'a-gold'},
    );
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tapAndSettle(tester, find.text('Message'));
    expect(shownRoute(tester), '/chats/thread/t-gold');
  });

  testWidgets('Call explains when voice is not set up', (tester) async {
    scriptGold(voice: false);
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tapAndSettle(tester, find.text('Call'));
    expect(find.text('Calls are not set up'), findsOneWidget);
    await tapAndSettle(tester, find.text('Open voice settings'));
    expect(shownRoute(tester), '/settings/voice');
  });

  testWidgets('stopping the agent patches paused', (tester) async {
    scriptGold();
    fakeApi.on(
      'PATCH /agents/a-gold',
      (body, _) => {...fixtureAgents[1], 'paused': true},
    );
    final store = await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tester.scrollUntilVisible(
      find.text('Stop the agent'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tapAndSettle(tester, find.text('Stop the agent'));
    expect(fakeApi.callsTo('PATCH', '/agents/a-gold').single.body, {
      'paused': true,
    });
    expect(store.state.shell.agents['a-gold']!.paused, isTrue);
    expect(find.text('Turn the agent on'), findsOneWidget);
    await settleToasts(tester);
  });

  testWidgets('delete confirms, then shows the server refusal', (tester) async {
    scriptGold();
    fakeApi.on(
      'DELETE /agents/a-gold',
      (_, _) => throw ApiError(status: 409, code: 'request_failed'),
    );
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tapAndSettle(tester, find.bySemanticsLabel('Agent actions'));
    await tapAndSettle(tester, find.text('Delete agent'));
    expect(find.text('Delete «Gold desk»?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Delete'));
    expect(fakeApi.callsTo('DELETE', '/agents/a-gold'), hasLength(1));
    expect(find.text('The request failed. Try again.'), findsOneWidget);
    await settleToasts(tester);
  });

  testWidgets('delete goes back to the agents list', (tester) async {
    scriptGold();
    fakeApi.on('DELETE /agents/a-gold', (_, _) => {'deleted': true});
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tapAndSettle(tester, find.bySemanticsLabel('Agent actions'));
    await tapAndSettle(tester, find.text('Delete agent'));
    await tapAndSettle(tester, find.text('Delete'));
    expect(shownRoute(tester), '/agents');
    await settleToasts(tester);
  });

  testWidgets('the personal agent offers neither stop nor delete', (
    tester,
  ) async {
    fakeApi.on('GET /voice/status', (_, _) => {'transport_configured': true});
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-lonora'),
      locale: 'en',
    );
    expect(find.text('Your personal assistant'), findsOneWidget);
    expect(find.text('Stop the agent'), findsNothing);
    await tapAndSettle(tester, find.bySemanticsLabel('Agent actions'));
    expect(find.text('Delete agent'), findsNothing);
  });

  testWidgets('cancelling a watch is confirmed', (tester) async {
    scriptGold();
    fakeApi.on('POST /watches/w-1/control', (_, _) => {});
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tester.scrollUntilVisible(
      find.text('Watches'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -300));
    await tester.pumpAndSettle();
    await tapAndSettle(tester, find.textContaining('above').last);
    await tapAndSettle(tester, find.text('Stop the watch'));
    expect(find.text('Stop this watch?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Stop'));
    expect(fakeApi.callsTo('POST', '/watches/w-1/control').single.body, {
      'action': 'cancel',
    });
    await settleToasts(tester);
  });

  testWidgets('Files opens the agent\'s own files', (tester) async {
    scriptGold();
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
      store: wpeStore(locale: 'en', inbox: goldInbox),
    );
    await tapAndSettle(tester, find.text('Files'));
    expect(shownRoute(tester), '/files?agent=a-gold');
  });

  testWidgets('without its conversation the Files row is still there', (
    tester,
  ) async {
    scriptGold();
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tapAndSettle(tester, find.text('Files'));
    expect(shownRoute(tester), '/files?agent=a-gold');
  });

  testWidgets('Lonora loads its watches once its state shows an account', (
    tester,
  ) async {
    fakeApi
      ..on('GET /voice/status', (_, _) => {'transport_configured': true})
      ..on(
        'GET /agents/a-lonora/state',
        (_, _) => {
          'state': 'idle',
          'trading_readiness': {
            'has_trading_account': true,
            'unresolved_count': 0,
            'trading_mode': 'ask',
          },
        },
      )
      ..on(
        'GET /watches',
        (_, _) => [
          {
            'id': 'w-9',
            'agent_id': 'a-lonora',
            'version': 1,
            'payload': {
              'kind': 'price',
              'symbol': 'EURUSD',
              'condition': 'below',
              'level': '1.05',
              'enabled': true,
            },
            'state': {'code': 'watch_active'},
          },
        ],
      );
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-lonora'),
      locale: 'en',
    );
    final calls = fakeApi.callsTo('GET', '/watches');
    expect(calls.single.query, {'agent_id': 'a-lonora'});
    await tester.scrollUntilVisible(
      find.text('Watches'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('EURUSD'), findsOneWidget);
    expect(find.text('No watches.'), findsNothing);
  });

  testWidgets('Call shows why the conversation could not open', (tester) async {
    scriptGold();
    fakeApi.on(
      'POST /agents/a-gold/conversation',
      (_, _) => throw ApiError(status: 500, code: 'request_failed'),
    );
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
      // As in the app, a failed action is not rethrown; the screen reads its status.
      store: Store<AppState>(
        initialState: wpeStore(locale: 'en').state,
        globalErrorObserver: (_) => SwallowGlobalErrorObserver<AppState>(),
      ),
    );
    await tapAndSettle(tester, find.text('Call'));
    expect(find.text('The request failed. Try again.'), findsOneWidget);
    await settleToasts(tester);
  });

  testWidgets('a failed routines read never offers «create routine»', (
    tester,
  ) async {
    scriptGold();
    fakeApi.on(
      'GET /routines',
      (_, _) => throw ApiError(status: 500, code: 'request_failed'),
    );
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    expect(find.text('Create routine'), findsNothing);
    expect(find.text('View all'), findsOneWidget);
    expect(find.text('The request failed. Try again.'), findsOneWidget);
    // Below the always-shown Files row.
    await tester.ensureVisible(find.text('View all'));
    await tester.pumpAndSettle();
    await tapAndSettle(tester, find.text('View all'));
    expect(shownRoute(tester), '/routines?agent=a-gold');
  });

  testWidgets('the page sits on one screen-fixed vertical gradient', (
    tester,
  ) async {
    scriptGold();
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
      brightness: Brightness.dark,
    );
    final gradient = find.byWidgetPredicate(
      (w) =>
          w is DecoratedBox &&
          (w.decoration as BoxDecoration).gradient is LinearGradient,
    );
    expect(gradient, findsOneWidget);
    final paint =
        (tester.widget<DecoratedBox>(gradient).decoration as BoxDecoration)
                .gradient!
            as LinearGradient;
    expect(paint.colors, [
      LnPalette.dark.profileTop,
      LnPalette.dark.profileBottom,
    ]);
    expect(paint.begin, Alignment.topCenter);
    expect(paint.end, Alignment.bottomCenter);
    final screen = tester.getSize(find.byType(MaterialApp));
    expect(tester.getRect(gradient), Offset.zero & screen);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -400));
    await tester.pumpAndSettle();
    expect(tester.getRect(gradient), Offset.zero & screen);
  });

  testWidgets('the hero: an 80 dp avatar, the name in the display style, and '
      'the lists flat on the page', (tester) async {
    scriptGold();
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final avatar = find.byWidgetPredicate(
      (w) => w is LonoraAvatar && w.agentId == 'a-gold',
    );
    expect(tester.getSize(avatar), const Size.square(80));
    final name = tester.widget<Text>(find.text('Gold desk'));
    expect(name.style!.fontSize, 20);
    expect(name.style!.fontWeight, FontWeight.w700);
    final sections = tester.widgetList<LnSection>(find.byType(LnSection));
    expect(sections, isNotEmpty);
    expect(sections.every((s) => s.flat), isTrue);
  });

  testWidgets('the instructions row opens the full-page editor', (
    tester,
  ) async {
    scriptGold();
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tapAndSettle(tester, find.text('Instructions'));
    expect(shownRoute(tester), '/agent/a-gold/instructions');
  });

  testWidgets('an unknown agent shows that it is missing', (tester) async {
    fakeApi.on(
      'GET /agents/a-none',
      (_, _) => throw ApiError(status: 404, code: 'agent_not_found'),
    );
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-none'),
      locale: 'en',
    );
    expect(find.text('Agent not found'), findsOneWidget);
  });

  testWidgets('loading and missing states sit on the profile gradient too', (
    tester,
  ) async {
    fakeApi.on(
      'GET /agents/a-none',
      (_, _) => throw ApiError(status: 404, code: 'agent_not_found'),
    );
    await pumpScreen(
      tester,
      const AgentProfileScreen(agentId: 'a-none'),
      locale: 'en',
      brightness: Brightness.dark,
    );
    expect(find.text('Agent not found'), findsOneWidget);
    final gradient = find.byWidgetPredicate(
      (w) =>
          w is DecoratedBox &&
          (w.decoration as BoxDecoration).gradient is LinearGradient,
    );
    expect(gradient, findsOneWidget);
    expect(
      ((tester.widget<DecoratedBox>(gradient).decoration as BoxDecoration)
                  .gradient!
              as LinearGradient)
          .colors,
      [LnPalette.dark.profileTop, LnPalette.dark.profileBottom],
    );
    final screen = tester.getSize(find.byType(MaterialApp));
    expect(tester.getRect(gradient), Offset.zero & screen);
    // The page's own fill is clear, so the gradient shows through.
    expect(
      tester
          .widget<Scaffold>(
            find.ancestor(
              of: find.text('Agent not found'),
              matching: find.byType(Scaffold),
            ),
          )
          .backgroundColor,
      const Color(0x00000000),
    );
  });

  for (final v in goldenVariants) {
    testWidgets('golden trading hub ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptGold();
        await pumpScreen(
          tester,
          const AgentProfileScreen(agentId: 'a-gold'),
          brightness: v.brightness,
          locale: v.locale,
          store: wpeStore(locale: v.locale, inbox: goldInbox),
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/profile_gold_${v.name}.png'),
        );
      });
    });
  }

  for (final v in [goldenVariants[0], goldenVariants[3]]) {
    testWidgets('golden trading sections ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptGold();
        await pumpScreen(
          tester,
          const AgentProfileScreen(agentId: 'a-gold'),
          brightness: v.brightness,
          locale: v.locale,
          store: wpeStore(locale: v.locale, inbox: goldInbox),
        );
        await tester.drag(find.byType(Scrollable).first, const Offset(0, -900));
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/profile_gold_sections_${v.name}.png'),
        );
      });
    });
  }

  for (final v in goldenVariants.take(2)) {
    testWidgets('golden neutral hub ${v.name}', (tester) async {
      await withRealShadows(() async {
        fakeApi
          ..on('GET /voice/status', (_, _) => {'transport_configured': false})
          ..on('GET /routines', (_, _) => []);
        await pumpScreen(
          tester,
          const AgentProfileScreen(agentId: 'a-research'),
          brightness: v.brightness,
          locale: v.locale,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/profile_research_${v.name}.png'),
        );
      });
    });
  }
}
