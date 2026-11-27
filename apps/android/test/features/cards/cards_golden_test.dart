// Goldens of the conversation's fixed cards (light/dark × ar/en, 393 × 852 dp at DPR 2), as
// `threadCards` builds them from `ThreadState.side`: pending (trade approval on a simulation
// account, the real Mandate card), acted (a completed approval and an answered Settle card: the
// disabled past-state stadium), refused (an Approve tap the server refused: the reason in the
// owner's words and the card read again), and an execution receipt with a peer exchange.
//
// Regenerate with: flutter test --update-goldens test/features/cards
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/cards/cards_actions.dart';
import 'package:lonora/features/cards/thread_cards.dart';
import 'package:lonora/features/rich/rich_content_view.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/fonts.dart';
import '../../design/harness.dart';
import '../rich/rich_harness.dart';
import 'card_fixtures.dart';

void main() {
  late L10n l10n;
  setUpAll(() async {
    await loadAppFonts();
    await loadMonospaceFont();
    l10n = await loadTestL10n();
  });

  Store<AppState> storeWith(
    Map<String, Object?> side, {
    List<Message>? messages,
  }) => Store<AppState>(
    initialState: signedInState(
      agents: {agentId: agent},
      threads: {
        threadId: ThreadState(
          threadId: threadId,
          thread: const Thread(id: threadId, agentId: agentId),
          messages: messages ?? [message(1), message(2), message(3)],
          loaded: true,
          side: side,
        ),
      },
    ),
  );

  Widget timeline(Store<AppState> store) =>
      StoreConnector<AppState, ThreadState>(
        converter: (s) => s.state.thread(threadId),
        builder: (context, thread) {
          final cards = threadCards(context, thread);
          return ListView(
            padding: BubbleGroup.gutter.copyWith(top: 12, bottom: 24),
            children: [
              for (var i = 0; i < cards.length; i++) ...[
                if (i > 0) const SizedBox(height: LnSpace.senderChangeGap),
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: KeyedSubtree(
                    key: ValueKey(cards[i].key),
                    child: Builder(builder: cards[i].builder),
                  ),
                ),
              ],
            ],
          );
        },
      );

  Future<void> shoot(
    WidgetTester tester,
    Store<AppState> store,
    String name,
    Brightness brightness,
    String locale, {
    Widget? child,
    Future<void> Function()? act,
  }) async {
    setGoldenViewport(tester);
    await withRealShadows(() async {
      await tester.pumpWidget(
        richTestApp(
          l10n: l10n,
          store: store,
          brightness: brightness,
          locale: locale,
          child: child ?? timeline(store),
        ),
      );
      await settle(tester);
      if (act != null) {
        await act();
        await settle(tester);
      }
      // The whole screen, so the image is captured at the viewport's DPR 2.
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/$name.png'),
      );
    });
  }

  setUp(() async {
    await sl.reset();
  });

  for (final (brightness, locale) in goldenVariants) {
    final v = variantName(brightness, locale);
    final ar = locale == 'ar';

    testWidgets('pending $v', (tester) async {
      final store = storeWith({
        SideKeys.approvals: [approval()],
        SideKeys.ownerActions: [mandateCard()],
        SideKeys.accounts: {accountId: 'simulation'},
      });
      await shoot(tester, store, 'cards_pending_$v', brightness, locale);
      // The Mandate button applies the other mode; the approval offers Reject / Approve.
      expect(find.text(ownerActionText(locale).modeFull), findsOneWidget);
      expect(find.text(l10n.t('approve')), findsOneWidget);
      expect(find.text(l10n.t('reject')), findsOneWidget);
      expect(find.text(ownerActionText(locale).simulation), findsOneWidget);
    });

    testWidgets('acted $v', (tester) async {
      final store = storeWith({
        SideKeys.approvals: [
          approval(
            status: 'completed',
            results: [
              {
                'operation_id': 'op-1',
                'status': 'confirmed',
                'broker_id': '50311987',
                'details': <String, Object?>{},
              },
            ],
          ),
        ],
        SideKeys.ownerActions: [
          settleCard(status: 'confirmed', result: {'outcome': 'not_executed'}),
        ],
        SideKeys.accounts: {accountId: 'metaapi'},
      });
      await shoot(tester, store, 'cards_acted_$v', brightness, locale);
      expect(find.text(ownerActionText(locale).brokerAccount), findsOneWidget);
      expect(find.text(l10n.t('approve')), findsNothing);
    });

    testWidgets('refused $v', (tester) async {
      final fake = FakeApi({
        'POST /trading/approvals/appr-1/decision': (_) =>
            ApiError(status: 409, code: 'trade_approval_expired'),
        'GET /trading/approvals?thread_id=$threadId': (_) => [
          approval(status: 'expired'),
        ],
      });
      sl.registerSingleton<ApiClient>(fake);
      final store = storeWith({
        SideKeys.approvals: [approval()],
        SideKeys.accounts: {accountId: 'simulation'},
      });
      await shoot(
        tester,
        store,
        'cards_refused_$v',
        brightness,
        locale,
        act: () async {
          await tester.tap(find.text(l10n.t('approve')));
          await tester.pump();
        },
      );
      expect(fake.bodies.first, {'decision': 'approve'});
      expect(
        find.text(l10n.errorText('trade_approval_expired')),
        findsOneWidget,
      );
      expect(find.text(ownerActionText(locale).renew), findsOneWidget);
    });

    testWidgets('receipt and peer exchange $v', (tester) async {
      final peerMessage = Message.fromJson({
        'id': 'pm1',
        'thread_id': threadId,
        'role': 'assistant',
        'agent_id': agentId,
        'seq': 4,
        'content':
            '<peer_outcome run="r9" status="completed">\n${ar ? 'اكتمل التحليل: الدعم عند **2330**.' : 'Analysis done: support at **2330**.'}\n</peer_outcome>',
        'created_at': '2026-11-27T09:06:00Z',
      });
      final store = storeWith(
        {
          SideKeys.receipts: [receipt()],
          SideKeys.peerMessages: [
            {
              'id': 'peer-1',
              'kind': 'peer_messages',
              'payload': {
                'source_agent_id': agentId,
                'source_agent_name': 'Lonora',
                'target_agent_id': 'a2',
                'target_agent_name': ar ? 'المحلل' : 'Analyst',
                'source_thread_id': threadId,
                'target_thread_id': 'other-thread',
                'source_message_id': 'pm0',
                'target_message_id': 'pmT',
                'source_outcome_message_id': 'pm1',
                'status': 'completed',
              },
            },
          ],
          SideKeys.accounts: {accountId: 'simulation'},
        },
        messages: [message(1), message(2), message(3), peerMessage],
      );
      await shoot(
        tester,
        store,
        'cards_receipt_peer_$v',
        brightness,
        locale,
        child: StoreConnector<AppState, ThreadState>(
          converter: (s) => s.state.thread(threadId),
          builder: (context, thread) {
            final cards = threadCards(context, thread);
            return ListView(
              padding: BubbleGroup.gutter.copyWith(top: 12),
              children: [
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: Builder(builder: cards.single.builder),
                ),
                const SizedBox(height: LnSpace.senderChangeGap),
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: MessageBubble(
                    sender: BubbleSender.agent,
                    child: RichContentView(
                      threadId: threadId,
                      text: peerMessage.content,
                      message: peerMessage,
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      );
      expect(find.text(l10n.t('peerCompleted')), findsOneWidget);
      expect(find.textContaining('peer_outcome'), findsNothing);
    });
  }

  // Large text: the Reject / Approve pair and the fact rows at 1.3× (Arabic, light), and
  // every other card kind laid out at 1.3× without overflow.
  testWidgets('cards at text scale 1.3', (tester) async {
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await shoot(
      tester,
      storeWith({
        SideKeys.approvals: [approval()],
        SideKeys.accounts: {accountId: 'metaapi'},
      }),
      'cards_pending_scale13_light_ar',
      Brightness.light,
      'ar',
    );
    expect(tester.takeException(), isNull);
    for (final row in [
      mandateCard(),
      settleCard(),
      secretCard(),
      settleCard(status: 'expired'),
    ]) {
      final store = storeWith({
        SideKeys.ownerActions: [row],
      });
      await tester.pumpWidget(
        richTestApp(l10n: l10n, store: store, child: timeline(store)),
      );
      await settle(tester);
      expect(tester.takeException(), isNull, reason: '${row['kind']}');
    }
  });
}
