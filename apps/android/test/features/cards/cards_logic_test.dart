// Timeline placement of the fixed cards (packages/core/src/conversation-timeline.ts), the side
// reads, and the exact owner-tap payloads. Safety: only the card routes are ever called, and
// only by the tap; nothing touches trading execution, runs or webhooks.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/features/cards/cards_actions.dart';
import 'package:lonora/features/cards/thread_cards.dart';
import 'package:lonora/features/rich/rich_parts.dart' show drawnSlots;
import 'package:lonora/state/app_state.dart';

import '../rich/rich_harness.dart';
import 'card_fixtures.dart';

void main() {
  group('timeline placement', () {
    final messages = [
      message(1),
      message(2),
      message(3),
      message(4),
      message(5),
    ];

    test(
      'server anchors: a card sits after the message before its timeline_seq',
      () {
        final anchors = cardAnchors(
          messages: messages,
          approvals: [approval(timelineSeq: 3)],
          ownerActions: [mandateCard()],
          receipts: [receipt(timelineSeq: 5)],
        );
        expect(anchors.map((a) => (a.key, a.seq)), [
          ('owner_action:${mandateCard()['id']}', 0),
          ('approval:appr-1', 2),
          ('receipt:op-1', 4),
        ]);
      },
    );

    test('legacy rows anchor by time, then after everything', () {
      final anchors = cardAnchors(
        messages: messages,
        approvals: [
          approval(
            id: 'old',
            timelineSeq: null,
            createdAt: '2026-11-27T09:02:00Z',
          ),
          approval(
            id: 'late',
            timelineSeq: null,
            createdAt: '2026-11-28T00:00:00Z',
          ),
        ],
        ownerActions: const [],
        receipts: const [],
      );
      // Created before message 2 (09:02:30) → after message 1; later than all → after 5.
      expect(anchors.map((a) => (a.id, a.seq)), [('old', 1), ('late', 5)]);
    });

    test('ties: approval, owner action, receipt, then by time and id', () {
      final anchors = cardAnchors(
        messages: messages,
        approvals: [approval(timelineSeq: 4)],
        ownerActions: [settleCard()],
        receipts: [receipt(timelineSeq: 4)],
      );
      expect(anchors.map((a) => a.kind), [
        'approval',
        'owner_action',
        'receipt',
      ]);
    });

    test('a record a loaded message embeds as a trusted slot has no row', () {
      final anchors = cardAnchors(
        messages: messages,
        approvals: [approval()],
        ownerActions: [mandateCard(), settleCard()],
        receipts: const [],
        slots: {'trade_approval:appr-1', 'mandate:${mandateCard()['id']}'},
      );
      expect(anchors.map((a) => a.key), ['owner_action:settle-1']);
    });

    test('duplicates are drawn once', () {
      final anchors = cardAnchors(
        messages: messages,
        approvals: [approval(), approval()],
        ownerActions: const [],
        receipts: [receipt(), receipt()],
      );
      expect(anchors, hasLength(2));
    });
  });

  group('side reads and taps', () {
    late FakeApi fake;
    late Store<AppState> store;

    Future<void> setUpWith(
      Map<String, Object? Function(Object?)> routes,
    ) async {
      await sl.reset();
      fake = FakeApi(routes);
      sl.registerSingleton<ApiClient>(fake);
      store = Store<AppState>(initialState: signedInState());
    }

    test(
      'LoadThreadSideAction reads the four lists and the account providers',
      () async {
        await setUpWith({
          'GET /owner-actions?thread_id=$threadId': (_) => [mandateCard()],
          'GET /trading/approvals?thread_id=$threadId': (_) => [approval()],
          'GET /trading/receipts?thread_id=$threadId': (_) => [receipt()],
          'GET /peer-messages?thread_id=$threadId': (_) => <Object?>[],
          'GET /trading/connections': (_) => connections(),
        });
        await store.dispatchAndWait(LoadThreadSideAction(threadId));
        final t = store.state.thread(threadId);
        expect(sideList(t, SideKeys.ownerActions), hasLength(1));
        expect(sideList(t, SideKeys.approvals), hasLength(1));
        expect(sideList(t, SideKeys.receipts), hasLength(1));
        // Keyed by the connection id the request names, never the broker's number; only
        // the provider is kept.
        expect(
          asJsonList(sideList(t, SideKeys.approvals).single['requests'])
              .single['account_id'],
          accountId,
        );
        expect(t.side[SideKeys.accounts], {accountId: 'simulation'});
        expect('${t.side}', isNot(contains('never-kept')));
        expect('${t.side}', isNot(contains(brokerAccountNumber)));
        expect(fake.calls.every((c) => c.startsWith('GET ')), isTrue);
      },
    );

    test('a late pending read never brings a decided approval back', () async {
      await setUpWith({
        'GET /owner-actions?thread_id=$threadId': (_) => <Object?>[],
        'GET /trading/approvals?thread_id=$threadId': (_) => [approval()],
        'GET /trading/receipts?thread_id=$threadId': (_) => <Object?>[],
        'GET /peer-messages?thread_id=$threadId': (_) => <Object?>[],
        'GET /trading/connections': (_) => connections(),
      });
      store = Store<AppState>(
        initialState: signedInState(
          threads: {
            threadId: ThreadState(
              threadId: threadId,
              side: {
                SideKeys.approvals: [approval(status: 'approved')],
              },
            ),
          },
        ),
      );
      await store.dispatchAndWait(LoadThreadSideAction(threadId));
      expect(
        sideList(
          store.state.thread(threadId),
          SideKeys.approvals,
        ).single['status'],
        'approved',
      );
      // A later state still wins.
      fake.routes['GET /trading/approvals?thread_id=$threadId'] = (_) => [
        approval(status: 'completed'),
      ];
      await store.dispatchAndWait(LoadThreadSideAction(threadId));
      expect(
        sideList(
          store.state.thread(threadId),
          SideKeys.approvals,
        ).single['status'],
        'completed',
      );
    });

    test(
      'a read that started before Approve and lands after it loses',
      () async {
        final read = Completer<Object?>();
        final post = Completer<Object?>();
        await setUpWith({
          'GET /owner-actions?thread_id=$threadId': (_) => <Object?>[],
          'GET /trading/approvals?thread_id=$threadId': (_) => read.future,
          'GET /trading/receipts?thread_id=$threadId': (_) => <Object?>[],
          'GET /peer-messages?thread_id=$threadId': (_) => <Object?>[],
          'GET /trading/connections': (_) => connections(),
          'POST /trading/approvals/appr-1/decision': (_) => post.future,
        });
        store = Store<AppState>(
          initialState: signedInState(
            threads: {
              threadId: ThreadState(
                threadId: threadId,
                side: {
                  SideKeys.approvals: [approval()],
                },
              ),
            },
          ),
        );
        final loading = store.dispatchAndWait(LoadThreadSideAction(threadId));
        final deciding = store.dispatchAndWait(
          TradeApprovalDecisionAction(
            threadId: threadId,
            approvalId: 'appr-1',
            decision: 'approve',
          ),
        );
        post.complete(approval(status: 'approved'));
        await deciding;
        read.complete([approval()]);
        await loading;
        expect(
          sideList(
            store.state.thread(threadId),
            SideKeys.approvals,
          ).single['status'],
          'approved',
        );
      },
    );

    test('mergeApproval keeps the row with more results in the same state', () {
      final full = approval(
        status: 'completed',
        results: [
          {'operation_id': 'op-1', 'status': 'confirmed', 'details': {}},
        ],
      );
      expect(mergeApproval(full, approval(status: 'completed')), same(full));
      expect(mergeApproval(approval(), full), same(full));
      expect(
        mergeApproval(approval(status: 'expired'), approval())['status'],
        'expired',
      );
    });

    test(
      'a failed read keeps what was there; an older pending never wins',
      () async {
        await setUpWith({
          'GET /owner-actions?thread_id=$threadId': (_) => [mandateCard()],
        });
        final confirmed = mandateCard(status: 'cancelled');
        store = Store<AppState>(
          initialState: signedInState(
            threads: {
              threadId: ThreadState(
                threadId: threadId,
                side: {
                  SideKeys.ownerActions: [confirmed],
                  SideKeys.approvals: [approval()],
                },
              ),
            },
          ),
        );
        await store.dispatchAndWait(LoadThreadSideAction(threadId));
        final t = store.state.thread(threadId);
        expect(
          sideList(t, SideKeys.ownerActions).single['status'],
          'cancelled',
        );
        expect(sideList(t, SideKeys.approvals), hasLength(1));
      },
    );

    test(
      'Approve posts exactly {decision: approve} to the approval route',
      () async {
        await setUpWith({
          'POST /trading/approvals/appr-1/decision': (body) =>
              approval(status: 'approved'),
        });
        await store.dispatchAndWait(
          TradeApprovalDecisionAction(
            threadId: threadId,
            approvalId: 'appr-1',
            decision: 'approve',
          ),
        );
        expect(fake.calls, ['POST /trading/approvals/appr-1/decision']);
        expect(fake.bodies.single, {'decision': 'approve'});
        expect(
          sideList(
            store.state.thread(threadId),
            SideKeys.approvals,
          ).single['status'],
          'approved',
        );
      },
    );

    test('a refused decision is rethrown and the card is read again', () async {
      await setUpWith({
        'POST /trading/approvals/appr-1/decision': (_) =>
            ApiError(status: 409, code: 'trade_approval_expired'),
        'GET /trading/approvals?thread_id=$threadId': (_) => [
          approval(status: 'expired'),
        ],
      });
      Object? error;
      try {
        await store.dispatchAndWait(
          TradeApprovalDecisionAction(
            threadId: threadId,
            approvalId: 'appr-1',
            decision: 'reject',
          ),
        );
      } catch (e) {
        error = e;
      }
      expect((error as ApiError).code, 'trade_approval_expired');
      await Future<void>.delayed(Duration.zero);
      expect(
        sideList(
          store.state.thread(threadId),
          SideKeys.approvals,
        ).single['status'],
        'expired',
      );
      expect(fake.bodies.first, {'decision': 'reject'});
    });

    test('the Mandate button applies exactly the mode it shows', () async {
      await setUpWith({
        'POST /owner-actions/${mandateCard()['id']}/decision': (_) =>
            mandateCard(status: 'confirmed'),
      });
      await store.dispatchAndWait(
        OwnerActionDecisionAction(
          threadId: threadId,
          cardId: asStr(mandateCard()['id']),
          decision: 'confirm',
          tradingMode: 'full',
        ),
      );
      expect(fake.bodies.single, {
        'decision': 'confirm',
        'trading_mode': 'full',
      });
    });

    test('a settle answer sends its outcome and nothing else', () async {
      await setUpWith({
        'POST /owner-actions/settle-1/decision': (_) =>
            settleCard(status: 'confirmed'),
      });
      await store.dispatchAndWait(
        OwnerActionDecisionAction(
          threadId: threadId,
          cardId: 'settle-1',
          decision: 'confirm',
          outcome: 'not_executed',
        ),
      );
      expect(fake.bodies.single, {
        'decision': 'confirm',
        'outcome': 'not_executed',
      });
      // Safety: no trading execution, run or webhook route was ever called.
      for (final call in fake.calls) {
        expect(call, isNot(contains('/trading/execute')));
        expect(call, isNot(matches(RegExp(r'^POST /runs$'))));
        expect(call, isNot(contains('webhook')));
      }
    });
  });

  group('undrawn messages', () {
    Message slotMessage(String id, int seq) => Message.fromJson({
      'id': id,
      'thread_id': threadId,
      'role': 'assistant',
      'agent_id': agentId,
      'seq': seq,
      'content': 'Mandate',
      'rich_content': {
        'version': 1,
        'parts': [
          {
            'type': 'ui',
            'document': {
              'v': 2,
              'kind': 'summary',
              'title': 'Mandate',
              'facts': <String, Object?>{},
              'state': <String, Object?>{},
              'calc': <String, Object?>{},
              'blocks': [
                {
                  'type': 'Slot',
                  'card': 'mandate',
                  'record': mandateCard()['id'],
                },
              ],
              'fallback': 'Mandate',
            },
          },
        ],
      },
      'created_at': '2026-11-27T09:03:30Z',
    });

    Set<String> rows(ThreadState t) => cardAnchors(
      messages: t.messages,
      approvals: const [],
      ownerActions: sideList(t, SideKeys.ownerActions),
      receipts: const [],
      slots: drawnSlots(
        t.messages.where((m) => !undrawnMessages(t).contains(m.id)),
      ),
    ).map((a) => a.key).toSet();

    test('a drawn slot is the card\'s place: no row of its own', () {
      final t = ThreadState(
        threadId: threadId,
        messages: [message(1), slotMessage('slot-msg', 2)],
        side: {
          SideKeys.ownerActions: [mandateCard()],
        },
      );
      expect(drawnSlots(t.messages), {'mandate:${mandateCard()['id']}'});
      expect(rows(t), isEmpty);
    });

    test('a slot in a message drawn as a peer exchange keeps the row', () {
      final t = ThreadState(
        threadId: threadId,
        messages: [message(1), slotMessage('slot-msg', 2)],
        side: {
          SideKeys.ownerActions: [mandateCard()],
          SideKeys.peerMessages: [
            {
              'id': 'peer-1',
              'payload': {'source_outcome_message_id': 'slot-msg'},
            },
          ],
        },
      );
      expect(undrawnMessages(t), contains('slot-msg'));
      expect(rows(t), {'owner_action:${mandateCard()['id']}'});
    });

    test('a slot in a message drawn as a question keeps the row', () {
      final t = ThreadState(
        threadId: threadId,
        messages: [message(1), slotMessage('slot-msg', 2)],
        runs: {
          'run-q': Run.fromJson({
            'id': 'run-q',
            'thread_id': threadId,
            'agent_id': agentId,
            'status': 'waiting_input',
            'input_requests': [
              {
                'id': 'q1',
                'run_id': 'run-q',
                'message_id': 'slot-msg',
                'question': 'Which?',
                'choices': [
                  {'id': 'a', 'label': 'A'},
                ],
              },
            ],
          }),
        },
        side: {
          SideKeys.ownerActions: [mandateCard()],
        },
      );
      expect(undrawnMessages(t), {'slot-msg'});
      expect(rows(t), {'owner_action:${mandateCard()['id']}'});
    });
  });
}
