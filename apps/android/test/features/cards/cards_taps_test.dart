// The safety-critical taps of the conversation's fixed cards, driven through the widgets:
// drawing a card sends nothing; a double tap sends exactly one decision; a Mandate switch says
// what it applied and reads the agents and approvals again; a Secret's value goes only to its
// route, leaves the field and never reaches an action or the store; Not now, Renew and Latest
// send exactly what web and Expo send (or nothing).
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/features/cards/cards_actions.dart';
import 'package:lonora/features/cards/owner_action_card.dart';
import 'package:lonora/features/cards/thread_cards.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/fonts.dart';
import '../rich/rich_harness.dart';
import 'card_fixtures.dart';

class _Recorder implements ActionObserver<AppState> {
  final List<ReduxAction<AppState>> actions = [];

  @override
  void observe(
    ReduxAction<AppState> action,
    int dispatchCount, {
    required bool ini,
  }) {
    if (ini) actions.add(action);
  }
}

/// The shell reads a Mandate switch triggers, answered as offline so nothing is cached.
Map<String, Object? Function(Object?)> _shellOffline() => {
  for (final path in const [
    '/agents',
    '/groups',
    '/threads/inbox',
    '/chat-lists',
    '/threads/settings',
    '/runs',
    '/attention',
    '/attention/view',
  ])
    'GET $path': (_) => ApiError.network(),
};

void main() {
  late L10n l10n;
  setUpAll(() async {
    await loadAppFonts();
    l10n = await loadTestL10n();
  });

  late FakeApi fake;
  late _Recorder recorder;

  setUp(() async {
    await sl.reset();
  });

  Store<AppState> storeWith(Map<String, Object?> side) {
    recorder = _Recorder();
    return Store<AppState>(
      initialState: signedInState(
        agents: {agentId: agent},
        threads: {
          threadId: ThreadState(
            threadId: threadId,
            thread: const Thread(id: threadId, agentId: agentId),
            messages: [message(1), message(2), message(3)],
            loaded: true,
            side: side,
          ),
        },
      ),
      actionObservers: [recorder],
    );
  }

  void serve(Map<String, Object? Function(Object?)> routes) {
    fake = FakeApi(routes);
    sl.registerSingleton<ApiClient>(fake);
  }

  Future<void> pumpCards(
    WidgetTester tester,
    Store<AppState> store, {
    String locale = 'en',
    void Function(String key)? onJump,
  }) async {
    await tester.pumpWidget(
      richTestApp(
        l10n: l10n,
        store: store,
        locale: locale,
        child: NotificationListener<TimelineCardJumpNotification>(
          onNotification: (n) {
            onJump?.call(n.key);
            return true;
          },
          child: StoreConnector<AppState, ThreadState>(
            converter: (s) => s.state.thread(threadId),
            builder: (context, thread) => ListView(
              children: [
                for (final card in threadCards(context, thread))
                  KeyedSubtree(
                    key: ValueKey(card.key),
                    child: Builder(builder: card.builder),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
    await settle(tester);
  }

  /// Taps the widget with [text], scrolling it into view first.
  Future<void> tapText(WidgetTester tester, String text) async {
    final finder = find.text(text);
    await tester.ensureVisible(finder);
    await tester.tap(finder, warnIfMissed: false);
  }

  testWidgets('drawing the cards sends nothing', (tester) async {
    serve({});
    final store = storeWith({
      SideKeys.approvals: [approval()],
      SideKeys.ownerActions: [mandateCard(), settleCard(), secretCard()],
      SideKeys.receipts: [receipt()],
    });
    await pumpCards(tester, store);
    await tester.pump(const Duration(seconds: 2));
    expect(fake.calls, isEmpty);
  });

  testWidgets('Approve: a double tap sends exactly one decision', (
    tester,
  ) async {
    final answer = Completer<Object?>();
    serve({'POST /trading/approvals/appr-1/decision': (_) => answer.future});
    final store = storeWith({
      SideKeys.approvals: [approval()],
    });
    await pumpCards(tester, store);
    final approve = l10n.t('approve');
    await tester.ensureVisible(find.text(approve));
    // Three taps inside one frame, then more once the card redrew busy.
    await tester.tap(find.text(approve));
    await tester.tap(find.text(approve));
    await tester.tap(find.text(l10n.t('reject')), warnIfMissed: false);
    await tester.pump();
    await tester.tap(find.text(l10n.t('reject')), warnIfMissed: false);
    await tester.pump();
    expect(fake.calls, ['POST /trading/approvals/appr-1/decision']);
    expect(fake.bodies.single, {'decision': 'approve'});
    answer.complete(approval(status: 'approved'));
    await settle(tester);
    expect(find.text(approve), findsNothing);
    expect(find.text(l10n.t('cards_approved')), findsOneWidget);
    expect(fake.calls, hasLength(1));
  });

  testWidgets(
    'Mandate: one switch per double tap; it says what it applied and re-reads',
    (tester) async {
      final answer = Completer<Object?>();
      final id = asStr(mandateCard()['id']);
      serve({
        'POST /owner-actions/$id/decision': (_) => answer.future,
        'GET /trading/approvals?thread_id=$threadId': (_) => [
          approval(status: 'withdrawn'),
        ],
        ..._shellOffline(),
      });
      final store = storeWith({
        SideKeys.ownerActions: [mandateCard()],
        SideKeys.approvals: [approval()],
      });
      await pumpCards(tester, store);
      final full = ownerActionText('en').modeFull;
      await tester.ensureVisible(find.text(full));
      await tester.tap(find.text(full));
      await tester.tap(find.text(full));
      await tester.pump();
      expect(fake.calls, ['POST /owner-actions/$id/decision']);
      expect(fake.bodies.single, {
        'decision': 'confirm',
        'trading_mode': 'full',
      });
      answer.complete(
        mandateCard(
          status: 'confirmed',
          result: {'trading_mode': 'full', 'withdrawn': 2},
        ),
      );
      await settle(tester);
      expect(
        find.text(modeChangeLine('Lonora', 'full', 2, 'en')),
        findsOneWidget,
      );
      // The agents (its mode everywhere) and the approvals it withdrew are read again.
      expect(fake.calls, contains('GET /agents'));
      expect(
        fake.calls,
        contains('GET /trading/approvals?thread_id=$threadId'),
      );
      expect(
        sideList(
          store.state.thread(threadId),
          SideKeys.approvals,
        ).single['status'],
        'withdrawn',
      );
      expect(fake.calls.where((c) => c.startsWith('POST ')), hasLength(1));
      await tester.pump(const Duration(seconds: 3));
    },
  );

  for (final refused in [false, true]) {
    testWidgets(
      'Secret Save${refused ? ' refused' : ''}: the value goes only to its route '
      'and is kept nowhere',
      (tester) async {
        const value = 'sk-test-9f8e7d6c';
        serve({
          'POST /owner-actions/secret-1/secret': (_) => refused
              ? ApiError(status: 422, code: 'secret_value_invalid')
              : secretCard(status: 'confirmed'),
        });
        final store = storeWith({
          SideKeys.ownerActions: [secretCard()],
        });
        await pumpCards(tester, store);
        await tester.enterText(find.byType(EditableText), value);
        await tester.pump();
        await tapText(tester, ownerActionText('en').secretSave);
        await settle(tester);

        expect(fake.calls, ['POST /owner-actions/secret-1/secret']);
        expect(fake.bodies.single, {
          'values': {'WEATHER_KEY': value},
        });
        // The map the card sent was emptied once the request finished.
        expect(asJson(asJson(fake.sentBodies.single)['values']), isEmpty);
        // Nothing typed stays in a field, an action or the store.
        for (final field in tester.widgetList<EditableText>(
          find.byType(EditableText),
        )) {
          expect(field.controller.text, isEmpty);
        }
        expect('${store.state.thread(threadId).side}', isNot(contains(value)));
        expect(
          recorder.actions.map((a) => a.runtimeType).toSet().difference({
            PatchOwnerActionAction,
            RereadOwnerActionsAction,
          }),
          isEmpty,
        );
        if (refused) {
          expect(
            find.text(l10n.errorText('secret_value_invalid')),
            findsOneWidget,
          );
          expect(
            sideList(
              store.state.thread(threadId),
              SideKeys.ownerActions,
            ).single['status'],
            'pending',
          );
        } else {
          expect(
            sideList(
              store.state.thread(threadId),
              SideKeys.ownerActions,
            ).single['status'],
            'confirmed',
          );
        }
      },
    );
  }

  testWidgets('Secret Not now sends {decision: cancel} and no value', (
    tester,
  ) async {
    serve({
      'POST /owner-actions/secret-1/decision': (_) =>
          secretCard(status: 'cancelled'),
    });
    final store = storeWith({
      SideKeys.ownerActions: [secretCard()],
    });
    await pumpCards(tester, store);
    await tester.enterText(find.byType(EditableText), 'typed-not-sent');
    await tester.pump();
    await tapText(tester, ownerActionText('en').notNow);
    await settle(tester);
    expect(fake.calls, ['POST /owner-actions/secret-1/decision']);
    expect(fake.bodies.single, {'decision': 'cancel'});
    expect(find.byType(EditableText), findsNothing);
  });

  testWidgets('Renew on an expired Settle card and an expired approval', (
    tester,
  ) async {
    serve({
      'POST /owner-actions/settle-1/renew': (_) => settleCard(),
      'POST /trading/approvals/appr-1/renew': (_) => {
        'id': 'run-2',
        'thread_id': threadId,
        'agent_id': agentId,
        'status': 'queued',
      },
    });
    final store = storeWith({
      SideKeys.ownerActions: [settleCard(status: 'expired')],
      SideKeys.approvals: [approval(status: 'expired')],
    });
    await pumpCards(tester, store);
    final renew = find.text(ownerActionText('en').renew);
    expect(renew, findsNWidgets(2));
    await tester.ensureVisible(renew.first);
    await tester.tap(renew.first);
    await settle(tester);
    await tester.ensureVisible(find.text(ownerActionText('en').renew).last);
    await tester.tap(find.text(ownerActionText('en').renew).last);
    await settle(tester);
    expect(fake.calls.toSet(), {
      'POST /trading/approvals/appr-1/renew',
      'POST /owner-actions/settle-1/renew',
    });
    expect(fake.bodies, everyElement(<String, Object?>{}));
    expect(store.state.thread(threadId).runs.keys, contains('run-2'));
  });

  testWidgets(
    'Latest on a replaced card shows the newer one and sends nothing',
    (tester) async {
      serve({});
      final store = storeWith({
        SideKeys.ownerActions: [
          {...settleCard(status: 'superseded'), 'superseded_by': 'settle-2'},
        ],
      });
      final jumps = <String>[];
      await pumpCards(tester, store, onJump: jumps.add);
      await tapText(tester, ownerActionText('en').latest);
      await settle(tester);
      expect(jumps, ['owner_action:settle-2']);
      expect(fake.calls, isEmpty);
    },
  );

  testWidgets('the account badge reads the connection the request names', (
    tester,
  ) async {
    serve({});
    final store = storeWith({
      SideKeys.approvals: [approval()],
      // Keyed by the connection id; the broker's own number never matches a request.
      SideKeys.accounts: {accountId: 'metaapi', brokerAccountNumber: 'x'},
    });
    await pumpCards(tester, store);
    expect(find.text(ownerActionText('en').brokerAccount), findsOneWidget);
  });

  testWidgets('the approval kicker keeps «· SYMBOL» with the word before it', (
    tester,
  ) async {
    serve({});
    await pumpCards(
      tester,
      storeWith({
        SideKeys.approvals: [approval()],
      }),
    );
    // cc:C11: no-break spaces on both sides of the dot, so a wrap never leaves it dangling.
    expect(
      find.text('Approval request\u00a0·\u00a0\u2066XAUUSD\u2069'),
      findsOneWidget,
    );
  });

  testWidgets('the receipt kicker keeps «· SYMBOL» with the word before it', (
    tester,
  ) async {
    serve({});
    await pumpCards(
      tester,
      storeWith({
        SideKeys.receipts: [receipt()],
      }),
    );
    // As the approval kicker (cc:C11): no-break spaces on both sides of the dot.
    expect(
      find.text('Execution receipt\u00a0·\u00a0\u2066XAUUSD\u2069'),
      findsOneWidget,
    );
  });

  testWidgets('a drifted approval ends on its status line, no stadium', (
    tester,
  ) async {
    serve({});
    final store = storeWith({
      SideKeys.approvals: [approval(status: 'drifted')],
    });
    await pumpCards(tester, store);
    expect(find.text(approvalStatusText('drifted', 'en')), findsOneWidget);
    expect(find.text(ownerActionText('en').statusCancelled), findsNothing);
    expect(find.text(l10n.t('approve')), findsNothing);
  });
}
