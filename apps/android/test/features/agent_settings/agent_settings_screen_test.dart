// Agent settings: identity and instructions saves, the model choice, the Mandate (only through
// its card, by an explicit tap), market scope, delivery rules, pause and delete; goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/agent_settings
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/features/agents/agent_settings_screen.dart';
import 'package:lonora/features/agents/settings/market_section.dart';
import 'package:lonora/core/models/models.dart';

import '../agent_profile/wpe_harness.dart';

const modelSummary = {
  'record': {
    'revision': 3,
    'preference': {'primary': null, 'fallbacks': []},
    'chosen_by': null,
  },
  'current': {'provider': 'openai', 'model': 'gpt-5.2', 'name': 'GPT-5.2'},
  'available': [
    {'provider': 'openai', 'model': 'gpt-5.2', 'name': 'GPT-5.2'},
    {
      'provider': 'anthropic',
      'model': 'claude-sonnet',
      'name': 'Claude Sonnet',
    },
  ],
  'connected_providers': ['openai', 'anthropic'],
  'usage': {
    'days': 30,
    'requests': 412,
    'input_tokens': 1830000,
    'output_tokens': 240000,
    'cached_tokens': 0,
    'models': [],
  },
};

const mandateCard = {
  'id': 'card-1',
  'kind': 'trading_mode',
  'status': 'pending',
  'agent_id': 'a-gold',
  'facts': {'trading_mode': 'ask'},
};

void scriptSettings({Object? mandate = mandateCard}) {
  fakeApi
    ..on(
      'GET /agents/a-gold/state',
      (_, _) => {
        'state': 'idle',
        'trading_readiness': {
          'has_trading_account': true,
          'unresolved_count': 0,
          'trading_mode': 'ask',
        },
      },
    )
    ..on('GET /agents/a-gold/model/summary', (_, _) => modelSummary)
    ..on('GET /agents/a-research/model/summary', (_, _) => modelSummary)
    ..on(
      'GET /agents/a-gold/notifications',
      (_, _) => {'in_app': true, 'calls': false, 'daily_limit': 20},
    )
    ..on(
      'GET /agents/a-research/notifications',
      (_, _) => {'in_app': true, 'calls': true, 'daily_limit': null},
    )
    ..on('GET /owner-actions/mandate', (_, _) => mandate)
    ..on(
      'GET /trading/connections',
      (_, _) => [
        {
          'id': 'acct-1',
          'version': 4,
          'payload': {
            'provider': 'metaapi',
            'account_id': 'meta-123',
            'enabled': true,
          },
          'state': {
            'broker_identity': {
              'connection_version': 4,
              'broker': 'ICMarkets',
              'login': '5011',
              'server': 'ICMarkets-Demo',
            },
          },
        },
      ],
    )
    ..on('GET /market/symbols', (_, _) => ['XAUUSD', 'EURUSD', 'BTCUSD']);
}

Agent agentOf(String id) =>
    Agent.fromJson(fixtureAgents.firstWhere((a) => a['id'] == id));

void main() {
  setUpAll(setUpWpeHarness);
  setUp(resetWpe);

  Finder field(String label) =>
      find.ancestor(of: find.text(label), matching: find.byType(Column)).first;

  testWidgets('saves only the identity fields that changed', (tester) async {
    scriptSettings();
    fakeApi.on(
      'PATCH /agents/a-gold',
      (body, _) => {...fixtureAgents[1], ...(body as Map<String, dynamic>)},
    );
    final store = await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tester.enterText(
      find.descendant(of: field('Name'), matching: find.byType(EditableText)),
      'Gold desk 2',
    );
    await tester.pump();
    await tapAndSettle(tester, find.text('Save').first);
    expect(fakeApi.callsTo('PATCH', '/agents/a-gold').single.body, {
      'name': 'Gold desk 2',
    });
    expect(store.state.shell.agents['a-gold']!.name, 'Gold desk 2');
    await settleToasts(tester);
  });

  testWidgets('saves the instructions with their own button', (tester) async {
    scriptSettings();
    fakeApi.on(
      'PATCH /agents/a-gold',
      (body, _) => {...fixtureAgents[1], ...(body as Map<String, dynamic>)},
    );
    await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final editor = find.byWidgetPredicate(
      (w) =>
          w is EditableText &&
          w.controller.text.startsWith('Trade only XAUUSD.'),
    );
    await tester.enterText(editor, 'Trade only gold.');
    await tester.pump();
    await tester.ensureVisible(find.text('Save').at(1));
    await tapAndSettle(tester, find.text('Save').at(1));
    expect(fakeApi.callsTo('PATCH', '/agents/a-gold').single.body, {
      'instructions': 'Trade only gold.',
    });
    await settleToasts(tester);
  });

  /// Scrolls [finder] into view (built and on screen).
  Future<void> reveal(WidgetTester tester, Finder finder) async {
    await tester.scrollUntilVisible(
      finder,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(finder);
    await tester.pumpAndSettle();
  }

  /// Scrolls to the Mandate row and opens its sheet.
  Future<void> openMandate(WidgetTester tester) async {
    final row = find.text('Trading mode: Ask');
    await reveal(tester, row);
    await tapAndSettle(tester, row);
  }

  testWidgets('the Mandate row only opens its sheet; a tap inside applies', (
    tester,
  ) async {
    scriptSettings();
    fakeApi.on(
      'POST /owner-actions/card-1/decision',
      (body, _) => {
        ...mandateCard,
        'status': 'confirmed',
        'result': {'trading_mode': 'full', 'withdrawn': 0},
      },
    );
    final store = await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    // The page itself offers no mode button and reads no card.
    expect(find.text('Full'), findsNothing);
    expect(fakeApi.callsTo('GET', '/owner-actions/mandate'), isEmpty);
    await openMandate(tester);
    // Opening the sheet reads the live card but never decides it.
    expect(find.textContaining('Gold desk'), findsWidgets);
    expect(find.text('Now: Ask'), findsOneWidget);
    expect(fakeApi.callsTo('GET', '/owner-actions/mandate'), hasLength(1));
    expect(fakeApi.callsTo('POST', '/owner-actions/card-1/decision'), isEmpty);
    await tapAndSettle(tester, find.text('Full'));
    expect(
      fakeApi.callsTo('POST', '/owner-actions/card-1/decision').single.body,
      {'decision': 'confirm', 'trading_mode': 'full'},
    );
    expect(store.state.shell.agents['a-gold']!.tradingMode, 'full');
    expect(find.text('Now: Ask'), findsNothing);
    await settleToasts(tester);
  });

  testWidgets('closing the Mandate sheet changes nothing', (tester) async {
    scriptSettings();
    final store = await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await openMandate(tester);
    await tapAndSettle(tester, find.text('Close'));
    expect(fakeApi.callsTo('POST', '/owner-actions/card-1/decision'), isEmpty);
    expect(store.state.shell.agents['a-gold']!.tradingMode, 'ask');
  });

  testWidgets('without a Mandate card the owner can ask for one', (
    tester,
  ) async {
    scriptSettings(mandate: null);
    fakeApi.on('POST /owner-actions/mandate?agent_id=a-gold', (_, _) {
      return mandateCard;
    });
    await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await openMandate(tester);
    expect(find.text('Full'), findsNothing);
    await tapAndSettle(tester, find.text('Show Mandate card'));
    expect(
      fakeApi.callsTo('POST', '/owner-actions/mandate?agent_id=a-gold'),
      hasLength(1),
    );
    // The card is shown; the mode itself changes only by the next, explicit tap.
    expect(find.text('Full'), findsOneWidget);
    expect(fakeApi.callsTo('POST', '/owner-actions/card-1/decision'), isEmpty);
  });

  testWidgets('a refused Mandate decision re-reads the live card', (
    tester,
  ) async {
    scriptSettings();
    fakeApi.on(
      'POST /owner-actions/card-1/decision',
      (_, _) =>
          throw ApiError(status: 409, code: 'owner_action_already_decided'),
    );
    final store = await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await openMandate(tester);
    await tapAndSettle(tester, find.text('Full'));
    expect(find.text('This card was already answered.'), findsOneWidget);
    expect(fakeApi.callsTo('GET', '/owner-actions/mandate'), hasLength(2));
    expect(store.state.shell.agents['a-gold']!.tradingMode, 'ask');
    await settleToasts(tester);
  });

  testWidgets('delivery rules save the typed limit', (tester) async {
    scriptSettings();
    fakeApi.on('PUT /agents/a-gold/notifications', (body, _) => body);
    await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final limit = find.byWidgetPredicate(
      (w) => w is EditableText && w.controller.text == '20',
    );
    await tester.scrollUntilVisible(
      limit,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.enterText(limit, '5');
    await tester.pump();
    await tester.ensureVisible(find.text('Save').last);
    await tapAndSettle(tester, find.text('Save').last);
    expect(fakeApi.callsTo('PUT', '/agents/a-gold/notifications').single.body, {
      'in_app': true,
      'calls': false,
      'daily_limit': 5,
    });
    await settleToasts(tester);
  });

  testWidgets('delete shows the refusal of an unresolved operation', (
    tester,
  ) async {
    scriptSettings();
    fakeApi.on(
      'DELETE /agents/a-gold',
      (_, _) => throw ApiError(
        status: 409,
        code: 'delete_blocked_unresolved_operation',
      ),
    );
    await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final delete = find.text('Delete agent');
    await tester.scrollUntilVisible(
      delete,
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tapAndSettle(tester, delete);
    await tapAndSettle(tester, find.text('Delete'));
    expect(
      find.textContaining('a trade linked to it still has no confirmed broker'),
      findsOneWidget,
    );
    await settleToasts(tester);
  });

  testWidgets('a delivery draft survives scrolling away and back', (
    tester,
  ) async {
    scriptSettings();
    fakeApi.on('PUT /agents/a-gold/notifications', (body, _) => body);
    await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final inApp = find.text('In-app messages');
    await reveal(tester, inApp);
    await tapAndSettle(tester, inApp);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, 4000));
    await tester.pumpAndSettle();
    expect(inApp, findsNothing);
    final limit = find.byWidgetPredicate(
      (w) => w is EditableText && w.controller.text == '20',
    );
    await reveal(tester, limit);
    final save = find.text('Save').last;
    await tester.ensureVisible(save);
    await tester.pumpAndSettle();
    await tapAndSettle(tester, save);
    expect(fakeApi.callsTo('PUT', '/agents/a-gold/notifications').single.body, {
      'in_app': false,
      'calls': false,
      'daily_limit': 20,
    });
    await settleToasts(tester);
  });

  testWidgets('leaving with an unsaved delivery change asks first', (
    tester,
  ) async {
    scriptSettings();
    await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final inApp = find.text('In-app messages');
    await reveal(tester, inApp);
    await tapAndSettle(tester, inApp);
    await tapAndSettle(tester, find.bySemanticsLabel('Back'));
    expect(find.text('Discard the changes?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Keep editing'));
    expect(find.text('In-app messages'), findsOneWidget);
    expect(fakeApi.callsTo('PUT', '/agents/a-gold/notifications'), isEmpty);
  });

  testWidgets(
    'the avatar studio resets, asks before dropping, saves two fields',
    (tester) async {
      scriptSettings();
      fakeApi.on(
        'PATCH /agents/a-gold',
        (body, _) => {...fixtureAgents[1], ...(body as Map<String, dynamic>)},
      );
      await pumpScreen(
        tester,
        const AgentSettingsScreen(agentId: 'a-gold'),
        locale: 'en',
      );
      await tapAndSettle(tester, find.text('Edit avatar').first);
      await tester.ensureVisible(find.text('Reset'));
      await tester.pumpAndSettle();
      await tapAndSettle(tester, find.text('Reset'));
      await tapAndSettle(tester, find.text('Cancel'));
      expect(find.text('Discard the changes?'), findsOneWidget);
      await tapAndSettle(tester, find.text('Keep editing'));
      // The sheet's Save (the page's own buttons lie under it).
      await tapAndSettle(tester, find.text('Save').last);
      expect(fakeApi.callsTo('PATCH', '/agents/a-gold').single.body, {
        'avatar': 'orb',
        'color': '#8B5CF6',
      });
      await settleToasts(tester);
    },
  );

  testWidgets('chooses the agent model with the summary revision', (
    tester,
  ) async {
    scriptSettings();
    fakeApi.on('PUT /agents/a-gold/model', (_, _) => {});
    await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final choose = find.text('Choose a model');
    await reveal(tester, choose);
    await tapAndSettle(tester, choose);
    await tapAndSettle(tester, find.textContaining('Claude Sonnet'));
    expect(fakeApi.callsTo('PUT', '/agents/a-gold/model').single.body, {
      'primary': {'provider': 'anthropic', 'model': 'claude-sonnet'},
      'expected_revision': 3,
    });
  });

  testWidgets('goes back to the default model', (tester) async {
    scriptSettings();
    fakeApi
      ..on(
        'GET /agents/a-gold/model/summary',
        (_, _) => {
          ...modelSummary,
          'record': {
            'revision': 4,
            'preference': {
              'primary': {'provider': 'anthropic', 'model': 'claude-sonnet'},
              'fallbacks': [],
            },
            'chosen_by': 'owner',
          },
        },
      )
      ..on('PUT /agents/a-gold/model', (_, _) => {});
    await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final back = find.text('Back to your default model');
    await reveal(tester, back);
    await tapAndSettle(tester, back);
    expect(fakeApi.callsTo('PUT', '/agents/a-gold/model').single.body, {
      'primary': null,
      'expected_revision': 4,
    });
  });

  testWidgets('a market scope change saves with its revision', (tester) async {
    scriptSettings();
    fakeApi.on(
      'PATCH /agents/a-gold',
      (body, _) => {...fixtureAgents[1], ...(body as Map<String, dynamic>)},
    );
    await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final general = find.text('General agent');
    await reveal(tester, general);
    await tapAndSettle(tester, general);
    // The Save under the market scope (the page's upper ones are scrolled away).
    final save = find.text('Save').first;
    await tester.ensureVisible(save);
    await tapAndSettle(tester, save);
    expect(fakeApi.callsTo('PATCH', '/agents/a-gold').single.body, {
      'scope_mode': 'flexible',
      'trading_account_id': null,
      'trading_symbol': null,
      'expected_scope_revision': 2,
    });
    await settleToasts(tester);
  });

  testWidgets('a failed broker list shows its error, not «connect first»', (
    tester,
  ) async {
    scriptSettings();
    fakeApi.on(
      'GET /trading/connections',
      (_, _) => throw ApiError(status: 500, code: 'request_failed'),
    );
    await pumpScreen(
      tester,
      const AgentSettingsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final failed = find.text('The request failed. Try again.');
    await reveal(tester, failed);
    expect(
      find.text('Connect a broker account before creating a trading agent.'),
      findsNothing,
    );
    fakeApi.on('GET /trading/connections', (_, _) => []);
    final before = fakeApi.callsTo('GET', '/trading/connections').length;
    await tapAndSettle(tester, failed);
    // The tile retries the read.
    expect(
      fakeApi.callsTo('GET', '/trading/connections'),
      hasLength(before + 1),
    );
  });

  test('market scope change follows the Lonora core rule', () {
    final gold = agentOf('a-gold');
    expect(agentMarketMode(gold), MarketMode.market);
    expect(
      marketScopeChange(MarketMode.market, 'acct-1', 'XAUUSD', gold),
      isEmpty,
    );
    expect(marketScopeChange(MarketMode.general, '', '', gold), {
      'scope_mode': 'flexible',
      'trading_account_id': null,
      'trading_symbol': null,
      'expected_scope_revision': 2,
    });
    final research = agentOf('a-research');
    expect(agentMarketMode(research), MarketMode.general);
    expect(marketScopeChange(MarketMode.general, '', '', research), isEmpty);
    final lonora = agentOf('a-lonora');
    expect(offersMarketScope(lonora), isFalse);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptSettings();
        await pumpScreen(
          tester,
          const AgentSettingsScreen(agentId: 'a-gold'),
          brightness: v.brightness,
          locale: v.locale,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/settings_${v.name}.png'),
        );
      });
    });
  }

  for (final v in [goldenVariants[0], goldenVariants[3]]) {
    testWidgets('golden mandate sheet ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptSettings();
        await pumpScreen(
          tester,
          const AgentSettingsScreen(agentId: 'a-gold'),
          brightness: v.brightness,
          locale: v.locale,
        );
        final row = find.text(
          v.locale == 'ar' ? 'التفويض: يستأذن' : 'Trading mode: Ask',
        );
        await reveal(tester, row);
        await tapAndSettle(tester, row);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/mandate_sheet_${v.name}.png'),
        );
      });
    });
  }

  for (final v in [goldenVariants[0], goldenVariants[3]]) {
    testWidgets('golden trading ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptSettings();
        await pumpScreen(
          tester,
          const AgentSettingsScreen(agentId: 'a-gold'),
          brightness: v.brightness,
          locale: v.locale,
        );
        await tester.drag(
          find.byType(Scrollable).first,
          const Offset(0, -1000),
        );
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/settings_trading_${v.name}.png'),
        );
      });
    });
  }
}
