// Conversation screen: goldens (light/dark × en/ar) of a mixed conversation (reactions, quote,
// question, failed outbox entry) and of a live streamed reply, plus behaviour: send with nonce,
// message menu (reactions, select text), reply bar, question answer, stop, unsent retry, shared
// content, states, read marks while on screen only, card jumps, call logs, the run banner,
// run-control busy and Retry-After, uploads, web search, older pages.
//
// Regenerate goldens: flutter test --update-goldens test/features/conversation
import 'dart:async';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:lonora/app/deep_links.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/avatar/avatar.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/cards/owner_action_card.dart';
import 'package:lonora/features/cards/cards_actions.dart' show SideKeys;
import 'package:lonora/features/conversation/conversation_composer.dart';
import 'package:lonora/features/conversation/conversation_screen.dart';
import 'package:lonora/features/conversation/message_widgets.dart';
import 'package:lonora/features/conversation/question_card.dart';
import 'package:lonora/features/conversation/run_rows.dart';
import 'package:lonora/features/rich/rich_content_view.dart';
import 'package:lonora/features/voice/voice_note_button.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';
import 'package:permission_handler/permission_handler.dart'
    show PermissionStatus;

import '../../design/fonts.dart';
import '../../design/harness.dart';
import 'conversation_harness.dart';

late L10n l10n;

AppState mixedState(String locale) {
  String p(String en, String ar) => pick(locale, en, ar);
  return conversationState(
    messages: [
      message(
        'm1',
        1,
        'user',
        p(
          'Can you check EUR/USD for today?',
          'هل يمكنك مراجعة اليورو مقابل الدولار لليوم؟',
        ),
        at(5),
      ),
      message(
        'm2',
        2,
        'assistant',
        p(
          'EUR/USD is holding above 1.0850 this morning. Momentum is soft, so I would wait for a clean break before acting.',
          'يتماسك اليورو فوق 1.0850 هذا الصباح. الزخم ضعيف، لذا أفضّل انتظار اختراق واضح قبل أي خطوة.',
        ),
        at(6),
        reactions: [
          {'reactor': 'owner', 'emoji': '👍', 'created_at': iso(at(7))},
        ],
      ),
      message(
        'm3',
        3,
        'user',
        p('What would change your view?', 'ما الذي قد يغيّر رأيك؟'),
        at(8),
        replyTo: 'm2',
      ),
      message(
        'm4',
        4,
        'assistant',
        p('Which timeframe should I use?', 'أي إطار زمني أستخدم؟'),
        at(9),
      ),
    ],
    runs: {
      'r1': run(
        'r1',
        'waiting_input',
        inputSeq: 3,
        createdAt: at(8),
        inputRequests: [
          {
            'id': 'q1',
            'run_id': 'r1',
            'message_id': 'm4',
            'thread_id': threadId,
            'question': p(
              'Which timeframe should I use for the levels?',
              'أي إطار زمني أستخدم للمستويات؟',
            ),
            'choices': [
              {'id': 'c1', 'label': p('Daily', 'يومي')},
              {'id': 'c2', 'label': p('4 hours', '4 ساعات')},
            ],
            'status': 'pending',
          },
        ],
      ),
    },
    outbox: [
      OutgoingMessage(
        nonce: 'n-failed',
        threadId: threadId,
        body: {
          'content': p('Also send the chart.', 'أرسل الرسم البياني أيضًا.'),
        },
        delivery: Delivery.failed,
        createdAt: at(11),
        errorCode: 'agent_paused',
      ),
    ],
  );
}

AppState streamingState(String locale) {
  String p(String en, String ar) => pick(locale, en, ar);
  return conversationState(
    messages: [
      message(
        'm1',
        1,
        'user',
        p('Summarise my open positions.', 'لخّص مراكزي المفتوحة.'),
        at(5),
      ),
      message(
        'm2',
        2,
        'assistant',
        p(
          'You have two open positions: EUR/USD long and gold short.',
          'لديك مركزان مفتوحان: شراء اليورو وبيع الذهب.',
        ),
        at(6),
      ),
      message(
        'm3',
        3,
        'user',
        p('How is the gold trade doing?', 'كيف حال صفقة الذهب؟'),
        at(7),
      ),
    ],
    runs: {'r2': run('r2', 'running', inputSeq: 3, createdAt: at(7))},
    streams: {
      'r2': liveStream(
        'r2',
        p(
          'Gold is down 0.4% since your entry, so the short is in profit. The next support is',
          'انخفض الذهب 0.4% منذ دخولك، فصفقة البيع رابحة. الدعم التالي عند',
        ),
      ),
    },
  );
}

Future<void> pumpScreen(
  WidgetTester tester,
  Store<AppState> store, {
  Brightness brightness = Brightness.light,
  String locale = 'en',
  int? around,
  bool onScreen = true,
}) async {
  setGoldenViewport(tester);
  await tester.pumpWidget(
    conversationApp(
      store: store,
      l10n: l10n,
      brightness: brightness,
      locale: locale,
      // Tickers off: an offstage tab of the home shell, or a page covering the conversation.
      child: TickerMode(
        enabled: onScreen,
        child: ConversationScreen(threadId: threadId, around: around),
      ),
    ),
  );
  await tester.pump(const Duration(milliseconds: 100));
  await tester.pump(const Duration(milliseconds: 400));
}

/// A composer or row button by its semantics label (LnTappable).
Finder tappable(String label) =>
    find.byWidgetPredicate((w) => w is LnTappable && w.semanticLabel == label);

/// Shows older rows: the transcript is reversed, so dragging down scrolls back.
Future<void> scrollBack(WidgetTester tester) async {
  await tester.drag(find.byType(ListView), const Offset(0, 500));
  await tester.pump(const Duration(milliseconds: 400));
}

/// Lets a shown toast expire and finish leaving (LnToast keeps the shown entry across trees).
Future<void> settleToasts(WidgetTester tester) async {
  await tester.pump(const Duration(seconds: 5));
  await tester.pump(const Duration(seconds: 1));
}

/// The flash of a jump target: its row's highlight.
Color? flashOf(WidgetTester tester, String key) {
  final box = tester.widget<AnimatedContainer>(
    find
        .descendant(
          of: find.byKey(ValueKey(key)),
          matching: find.byType(AnimatedContainer),
        )
        .first,
  );
  return (box.decoration as BoxDecoration?)?.color;
}

void main() {
  setUpAll(() async {
    await loadAppFonts();
    l10n = await L10n.load();
    if (!sl.isRegistered<LocalStore>()) {
      final dir = await Directory.systemTemp.createTemp('lonora_conv_test');
      sl.registerSingleton<LocalStore>(LocalStore.at(dir));
    }
  });

  late FakeApi fake;
  setUp(() => fake = registerFakeApi());
  tearDown(() async {
    if (sl.isRegistered<ApiClient>()) await sl.unregister<ApiClient>();
    pendingShare.value = null;
    ConversationComposerState.clearDrafts();
  });

  group('goldens', () {
    for (final scene in ['mixed', 'streaming']) {
      for (final locale in ['en', 'ar']) {
        for (final brightness in Brightness.values) {
          final name = 'conversation_${scene}_${brightness.name}_$locale';
          testWidgets(name, (tester) async {
            final state = scene == 'mixed'
                ? mixedState(locale)
                : streamingState(locale);
            await withRealShadows(() async {
              await pumpScreen(
                tester,
                Store<AppState>(initialState: state),
                brightness: brightness,
                locale: locale,
              );
              await expectLater(
                find.byType(MaterialApp),
                matchesGoldenFile('goldens/$name.png'),
              );
            });
          });
        }
      }
    }
  });

  group('behaviour', () {
    testWidgets('shows the mixed conversation and its states', (tester) async {
      await pumpScreen(tester, Store<AppState>(initialState: mixedState('en')));
      // The capsule's name and the quote's author.
      expect(
        find.descendant(
          of: find.byType(TitleCapsule),
          matching: find.text('Atlas'),
        ),
        findsOneWidget,
      );
      // The question replaces the message that holds it.
      expect(find.byType(QuestionCard), findsOneWidget);
      expect(find.text('Which timeframe should I use?'), findsNothing);
      expect(find.text('Daily'), findsOneWidget);
      // Failed outbox entry with its Retry.
      expect(find.text('Message not sent'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
      // cc:C9: its bubble is not faded; the red line marks it.
      expect(
        find.ancestor(
          of: find.text('Also send the chart.'),
          matching: find.byType(Opacity),
        ),
        findsNothing,
      );
      // The quote of the reply.
      expect(find.textContaining('EUR/USD is holding'), findsNWidgets(2));
      await scrollBack(tester);
      expect(find.text('Can you check EUR/USD for today?'), findsOneWidget);
      // A time separator above the first message.
      expect(find.byType(DateSeparator), findsOneWidget);
      // The owner's reaction chip.
      expect(find.text('👍'), findsOneWidget);
    });

    testWidgets('sends the typed text with a client nonce', (tester) async {
      fake.answers['POST /threads/$threadId/messages'] = (body) => {
        'message': {
          ...messageJson(
            id: 'm9',
            seq: 9,
            role: 'user',
            content: 'Hello there',
            createdAt: at(20),
          ),
          'client_nonce': asJson(body)['client_nonce'],
        },
        'runs': <Json>[],
      };
      final store = Store<AppState>(initialState: streamingState('en'));
      await pumpScreen(tester, store);
      await tester.enterText(find.byType(TextField), 'Hello there');
      await tester.pump();
      await tester.tap(tappable('Send'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      final post = fake.calls.lastWhere((c) => c.method == 'POST');
      expect(post.path, '/threads/$threadId/messages');
      final body = asJson(post.body);
      expect(body['content'], 'Hello there');
      expect(asStr(body['client_nonce']), isNotEmpty);
      expect(store.state.thread(threadId).messages.last.id, 'm9');
      expect(store.state.outbox, isEmpty);
      expect(find.text('Hello there'), findsOneWidget);
    });

    testWidgets('message menu: reactions, reply bar, select text', (
      tester,
    ) async {
      await pumpScreen(tester, Store<AppState>(initialState: mixedState('en')));
      await scrollBack(tester);
      await tester.longPress(find.textContaining('EUR/USD is holding').last);
      await tester.pump(const Duration(milliseconds: 600));
      expect(find.text('Reply'), findsOneWidget);
      expect(find.text('Copy text'), findsOneWidget);
      expect(find.text('Select text'), findsOneWidget);
      expect(find.text('Turn into a task'), findsOneWidget);
      // Q13: the reply and task glyphs turn with the reading direction.
      expect(find.byIcon(LnIcons.reply), findsOneWidget);
      expect(find.byIcon(LnIcons.listTodo), findsOneWidget);
      // Lonora has no forward or delete route for sent messages.
      expect(find.text('Forward'), findsNothing);
      for (final emoji in ['👍', '❤️', '😂', '😮', '😢', '🙏']) {
        expect(find.text(emoji), findsWidgets);
      }
      // The menu card is headed by the message's time (the time separators' rule).
      expect(find.text(l10n.timeSeparator(at(6))), findsWidgets);
      await tester.tap(find.text('Reply'));
      await tester.pump(const Duration(milliseconds: 600));
      // The reply bar quotes the message; its quote mark says it is a reply.
      final bar = find.byType(ComposerReplyBar);
      expect(bar, findsOneWidget);
      expect(tester.widget<ComposerReplyBar>(bar).title, isNull);
      expect(
        find.descendant(
          of: bar,
          matching: find.textContaining('EUR/USD is holding'),
        ),
        findsOneWidget,
      );
      expect(tappable('Cancel reply'), findsOneWidget);

      // «Select text»: the message drawn by the rich view, selectable.
      await tester.longPress(
        find.descendant(
          of: find.byWidgetPredicate(
            (w) => w is MessageTile && w.message.id == 'm2',
          ),
          matching: find.textContaining('EUR/USD is holding'),
        ),
      );
      await tester.pump(const Duration(milliseconds: 600));
      await tester.tap(find.text('Select text'));
      await tester.pump(const Duration(milliseconds: 600));
      await tester.pump(const Duration(milliseconds: 600));
      final sheet = find.byWidgetPredicate(
        (w) => w is RichContentView && w.selectable,
      );
      expect(sheet, findsOneWidget);
      expect(
        find.descendant(of: sheet, matching: find.byType(SelectionArea)),
        findsOneWidget,
      );
    });

    testWidgets('a quick reaction is sent, and a refusal rolls it back', (
      tester,
    ) async {
      final store = Store<AppState>(initialState: mixedState('en'));
      await pumpScreen(tester, store);
      await scrollBack(tester);
      fake.answers['PUT /threads/$threadId/messages/m2/reactions/%E2%9D%A4%EF%B8%8F'] =
          (_) => {
            'reactions': [
              {'reactor': 'owner', 'emoji': '❤️', 'created_at': iso(at(12))},
            ],
          };
      await tester.longPress(find.textContaining('EUR/USD is holding').last);
      await tester.pump(const Duration(milliseconds: 600));
      await tester.tap(tappable('React ❤️'));
      await tester.pump(const Duration(milliseconds: 600));
      expect(
        fake.calls.where(
          (c) =>
              c.method == 'PUT' &&
              c.path ==
                  '/threads/$threadId/messages/m2/reactions/%E2%9D%A4%EF%B8%8F',
        ),
        hasLength(1),
      );
      List<String> mine() => [
        for (final r
            in store.state
                .thread(threadId)
                .messages
                .firstWhere((m) => m.id == 'm2')
                .reactions)
          if (r.reactor == 'owner') r.emoji,
      ];
      expect(mine(), ['❤️']);

      // The server refuses the removal: the reaction comes back and the reason shows.
      fake.answers['DELETE /threads/$threadId/messages/m2/reactions'] = (_) =>
          throw ApiError(status: 404, code: 'message_not_found');
      await tester.longPress(find.textContaining('EUR/USD is holding').last);
      await tester.pump(const Duration(milliseconds: 600));
      await tester.tap(tappable('React ❤️'));
      await tester.pump(const Duration(milliseconds: 600));
      expect(mine(), ['❤️']);
      expect(find.text(l10n.errorText('message_not_found')), findsOneWidget);
      await settleToasts(tester);
    });

    testWidgets('owner text can be edited and resent', (tester) async {
      await pumpScreen(tester, Store<AppState>(initialState: mixedState('en')));
      await scrollBack(tester);
      await tester.longPress(find.text('Can you check EUR/USD for today?'));
      await tester.pump(const Duration(milliseconds: 600));
      await tester.tap(find.text('Edit and resend'));
      await tester.pump(const Duration(milliseconds: 600));
      expect(find.text('Edit the message'), findsOneWidget);
      final field = tester.widget<TextField>(find.byType(TextField));
      expect(field.controller!.text, 'Can you check EUR/USD for today?');
      await tester.enterText(find.byType(TextField), 'Check EUR/USD please');
      await tester.pump();
      await tester.tap(tappable('Send'));
      await tester.pump(const Duration(milliseconds: 50));
      final body = asJson(fake.calls.lastWhere((c) => c.method == 'POST').body);
      expect(body['edited_from'], 'm1');
      expect(body['content'], 'Check EUR/USD please');
    });

    testWidgets('a choice answers the question with input_answer', (
      tester,
    ) async {
      final store = Store<AppState>(initialState: mixedState('en'));
      await pumpScreen(tester, store);
      await tester.tap(find.text('4 hours'));
      await tester.pump(const Duration(milliseconds: 50));
      final body = asJson(fake.calls.lastWhere((c) => c.method == 'POST').body);
      expect(body['content'], '4 hours');
      expect(body['reply_to'], 'm4');
      expect(body['input_answer'], {
        'run_id': 'r1',
        'question_id': 'q1',
        'choice_id': 'c2',
      });
      await tester.pump(const Duration(milliseconds: 300));
    });

    testWidgets('Stop cancels the working run', (tester) async {
      await pumpScreen(
        tester,
        Store<AppState>(initialState: streamingState('en')),
      );
      expect(find.textContaining('Gold is down 0.4%'), findsOneWidget);
      await tester.tap(tappable('Stop'));
      await tester.pump(const Duration(milliseconds: 50));
      expect(
        fake.calls.where((c) => c.path == '/runs/r2/cancel'),
        hasLength(1),
      );
    });

    testWidgets('the canonical message replaces the live preview', (
      tester,
    ) async {
      final store = Store<AppState>(initialState: streamingState('en'));
      await pumpScreen(tester, store);
      expect(find.textContaining('Gold is down 0.4%'), findsOneWidget);
      final t = store.state.thread(threadId);
      final committed = t.streams['r2']!.copyWith(
        phase: 'committed',
        messageId: 'm4',
      );
      store.dispatch(
        _Patch(
          t
              .copyWith(
                streams: {'r2': committed},
                runs: {'r2': t.runs['r2']!.withStatus('completed')},
              )
              .mergeMessages([
                message(
                  'm4',
                  4,
                  'assistant',
                  'Gold is down 0.4% since your entry. Support is at 2,310.',
                  at(9),
                ),
              ]),
        ),
      );
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.textContaining('Gold is down 0.4%'), findsOneWidget);
      expect(find.textContaining('Support is at 2,310'), findsOneWidget);
    });

    testWidgets('a streamed chunk redraws the live reply only', (tester) async {
      final store = Store<AppState>(initialState: streamingState('en'));
      await pumpScreen(tester, store);
      final tiles = tester.widgetList<MessageTile>(find.byType(MessageTile));
      final before = tiles.toList();
      final t = store.state.thread(threadId);
      final stream = t.streams['r2']!;
      store.dispatch(
        _Patch(
          t.copyWith(
            streams: {
              'r2': stream.copyWith(
                text: '${stream.text} 2,310.',
                sequence: stream.sequence + 1,
              ),
            },
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 50));
      expect(find.textContaining('The next support is 2,310.'), findsOneWidget);
      // The rest of the transcript was not rebuilt (same widgets).
      final after = tester
          .widgetList<MessageTile>(find.byType(MessageTile))
          .toList();
      expect(after, hasLength(before.length));
      for (var i = 0; i < after.length; i++) {
        expect(identical(after[i], before[i]), isTrue);
      }
    });

    testWidgets('the agent at work shows while a run has no text yet', (
      tester,
    ) async {
      final base = streamingState('en');
      final state = base.withThread(
        base.thread(threadId).copyWith(streams: const {}),
      );
      await pumpScreen(tester, Store<AppState>(initialState: state));
      final row = find.byType(WorkingRow);
      expect(row, findsOneWidget);
      // Its avatar sits at the bubbles' text column, 32 dp from the start edge.
      final avatar = find.descendant(
        of: row,
        matching: find.byType(LonoraAvatar),
      );
      expect(tester.getSize(avatar), const Size(32, 32));
      expect(tester.getTopLeft(avatar).dx, LnSpace.pageGutter + 16);
      expect(tester.widget<WorkingRow>(row).semanticLabel, isNotEmpty);
    });

    testWidgets('a failed unsent message retries with the same nonce', (
      tester,
    ) async {
      await pumpScreen(tester, Store<AppState>(initialState: mixedState('en')));
      await tester.tap(find.text('Retry'));
      await tester.pump(const Duration(milliseconds: 50));
      final body = asJson(fake.calls.lastWhere((c) => c.method == 'POST').body);
      expect(body['client_nonce'], 'n-failed');
    });

    testWidgets('a message waiting for the network keeps its bubble readable', (
      tester,
    ) async {
      final state = conversationState(
        outbox: [
          OutgoingMessage(
            nonce: 'n-queued',
            threadId: threadId,
            body: const {'content': 'Send when online.'},
            delivery: Delivery.queued,
            createdAt: at(11),
          ),
        ],
      );
      await pumpScreen(tester, Store<AppState>(initialState: state));
      expect(find.text(l10n.t('sh_waitingNetwork')), findsOneWidget);
      // cc:C9 review: not faded either; the status line marks it.
      expect(
        find.ancestor(
          of: find.text('Send when online.'),
          matching: find.byType(Opacity),
        ),
        findsNothing,
      );
    });

    testWidgets('shared text and files join the composer', (tester) async {
      pendingShare.value = const SharedPayload(
        text: 'From another app',
        targetThreadId: threadId,
      );
      await pumpScreen(
        tester,
        Store<AppState>(initialState: streamingState('en')),
      );
      final field = tester.widget<TextField>(find.byType(TextField));
      expect(field.controller!.text, 'From another app');
      expect(pendingShare.value, isNull);
    });

    testWidgets('loading, empty, unavailable and paused states', (
      tester,
    ) async {
      await pumpScreen(
        tester,
        Store<AppState>(initialState: conversationState(loaded: false)),
      );
      expect(find.bySemanticsLabel('Loading'), findsOneWidget);

      await pumpScreen(
        tester,
        Store<AppState>(initialState: conversationState()),
      );
      expect(
        find.text('No messages yet. Start the conversation.'),
        findsOneWidget,
      );

      await pumpScreen(
        tester,
        Store<AppState>(
          initialState: conversationState(
            loaded: false,
            error: 'thread_not_found',
          ),
        ),
      );
      expect(
        find.text('This conversation is no longer available.'),
        findsOneWidget,
      );
      expect(find.byType(TextField), findsNothing);

      await pumpScreen(
        tester,
        Store<AppState>(
          initialState: conversationState(agent: fixtureAgent(paused: true)),
        ),
      );
      expect(
        find.text('This agent is paused: resume it, then try again.'),
        findsOneWidget,
      );
    });

    testWidgets('the network error state retries', (tester) async {
      await pumpScreen(
        tester,
        Store<AppState>(
          initialState: conversationState(loaded: false, error: 'network'),
        ),
      );
      expect(find.text('Retry'), findsOneWidget);
    });

    testWidgets('the network error state retries the snapshot', (tester) async {
      final state = signedIn(conversationState(loaded: false));
      fake.answers['GET /threads/$threadId'] = (_) =>
          throw ApiError(status: null, code: 'network');
      await pumpScreen(tester, Store<AppState>(initialState: state));
      expect(find.text(l10n.errorText('network')), findsOneWidget);
      final before = fake.calls
          .where((c) => c.method == 'GET' && c.path == '/threads/$threadId')
          .length;
      serveThread(fake, mixedState('en'));
      await tester.tap(find.text('Retry'));
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 400));
      expect(
        fake.calls
            .where((c) => c.method == 'GET' && c.path == '/threads/$threadId')
            .length,
        before + 1,
      );
      expect(find.text('Daily'), findsOneWidget);
    });

    testWidgets('lands around a message, flashes it, then jumps to latest', (
      tester,
    ) async {
      final base = mixedState('en');
      serveThread(fake, base);
      final state = signedIn(
        base.withThread(base.thread(threadId).copyWith(focusSeq: 1)),
      );
      final store = Store<AppState>(initialState: state);
      await pumpScreen(tester, store, around: 1);
      await tester.pump(const Duration(milliseconds: 100));
      expect(
        fake.calls.where(
          (c) =>
              c.path == '/threads/$threadId/messages' &&
              asJson(c.body)['around'] == 1,
        ),
        isNotEmpty,
      );
      expect(find.text('Can you check EUR/USD for today?'), findsOneWidget);
      // The landing row is marked, the others are not.
      expect(flashOf(tester, 'm:m1'), isNotNull);
      expect(flashOf(tester, 'm:m3'), isNull);
      await tester.pump(const Duration(seconds: 2));
      expect(flashOf(tester, 'm:m1'), isNull);
      // Away from the latest message: the jump button loads the newest page.
      fake.calls.clear();
      await tester.tap(tappable('Jump to latest'));
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 600));
      final newest = fake.calls.where(
        (c) => c.method == 'GET' && c.path == '/threads/$threadId/messages',
      );
      expect(newest, hasLength(1));
      expect(asJson(newest.single.body).containsKey('around'), isFalse);
      expect(store.state.thread(threadId).focusSeq, isNull);
    });

    testWidgets('the jump button speaks its unread count in the owner\'s '
        'language', (tester) async {
      final handle = tester.ensureSemantics();
      final base = mixedState('ar');
      serveThread(fake, base);
      final store = Store<AppState>(
        initialState: signedIn(
          base.withThread(base.thread(threadId).copyWith(focusSeq: 1)),
        ),
      );
      await pumpScreen(tester, store, around: 1, locale: 'ar');
      await tester.pump(const Duration(seconds: 2));
      String label() => tester
          .widget<JumpToLatestButton>(find.byType(JumpToLatestButton))
          .semanticLabel;
      expect(label(), 'انتقل إلى أحدث رسالة');
      // A reply arrives while the owner reads older messages.
      store.dispatch(
        _Patch(
          store.state.thread(threadId).mergeMessages([
            message('m9', 9, 'assistant', 'جديد.', at(30)),
          ]),
        ),
      );
      await tester.pump(const Duration(milliseconds: 100));
      // K15: one label, joined with the Arabic comma.
      expect(label(), 'انتقل إلى أحدث رسالة، 1 غير مقروءة');
      // It reaches the tree as one tappable button.
      expect(
        tester.getSemantics(
          find.bySemanticsLabel('انتقل إلى أحدث رسالة، 1 غير مقروءة'),
        ),
        isSemantics(
          label: 'انتقل إلى أحدث رسالة، 1 غير مقروءة',
          isButton: true,
          hasTapAction: true,
        ),
      );
      handle.dispose();
    });

    testWidgets('group conversations name each agent', (tester) async {
      final other = Agent.fromJson({
        'id': 'agent-2',
        'name': 'Nova',
        'avatar': 'orb',
        'color': 'red',
      });
      final base = mixedState('en');
      final group = Group.fromJson({
        'id': 'group-1',
        'version': 1,
        'payload': {
          'name': 'Desk',
          'member_ids': [agentId, 'agent-2'],
        },
      });
      final t = base.thread(threadId);
      final state = base
          .copyWith(
            shell: base.shell.copyWith(
              agents: {...base.shell.agents, 'agent-2': other},
              groups: {'group-1': group},
            ),
          )
          .withThread(
            t.copyWith(
              thread: Thread.fromJson({
                'id': threadId,
                'group_id': 'group-1',
                'options': {'web_search': false},
              }),
              runs: const {},
              messages: [
                ...t.messages.take(3),
                Message.fromJson({
                  ...t.messages[1].raw,
                  'id': 'm5',
                  'seq': 5,
                  'agent_id': 'agent-2',
                  'content': 'I agree with Atlas.',
                }),
              ],
            ),
          );
      await pumpScreen(tester, Store<AppState>(initialState: state));
      expect(
        find.descendant(
          of: find.byType(TitleCapsule),
          matching: find.text('Desk'),
        ),
        findsOneWidget,
      );
      expect(find.text('Nova'), findsOneWidget);
    });

    testWidgets('large text (1.3) lays out without overflow', (tester) async {
      setGoldenViewport(tester);
      await tester.pumpWidget(
        conversationApp(
          store: Store<AppState>(initialState: mixedState('ar')),
          l10n: l10n,
          locale: 'ar',
          textScale: 1.3,
          child: const ConversationScreen(threadId: threadId),
        ),
      );
      await tester.pump(const Duration(milliseconds: 500));
      expect(tester.takeException(), isNull);
    });
  });

  group('contract', () {
    Iterable<int> reads() => [
      for (final c in fake.calls)
        if (c.method == 'POST' && c.path == '/threads/$threadId/read')
          asInt(asJson(c.body)['seq'])!,
    ];

    testWidgets('a share arriving while a conversation is open waits for the '
        'share picker', (tester) async {
      await pumpScreen(tester, Store<AppState>(initialState: mixedState('en')));
      pendingShare.value = const SharedPayload(text: 'Shared later');
      await tester.pump(const Duration(milliseconds: 100));
      expect(pendingShare.value, isNotNull);
      final field = tester.widget<TextField>(find.byType(TextField));
      expect(field.controller!.text, isEmpty);
    });

    testWidgets('a share the picker addressed to the open conversation joins '
        'its composer', (tester) async {
      await pumpScreen(tester, Store<AppState>(initialState: mixedState('en')));
      pendingShare.value = const SharedPayload(text: 'Shared here')
          .withTarget(threadId);
      await tester.pump(const Duration(milliseconds: 100));
      expect(pendingShare.value, isNull);
      final field = tester.widget<TextField>(find.byType(TextField));
      expect(field.controller!.text, 'Shared here');
    });

    testWidgets('read marks and the open thread follow the conversation being '
        'on screen', (tester) async {
      final base = mixedState('en');
      serveThread(fake, base);
      final store = Store<AppState>(initialState: signedIn(base));
      await pumpScreen(tester, store);
      expect(store.state.openThreadId, threadId);
      expect(reads(), [4]);

      // Another tab (the shell keeps this page alive offstage, tickers off).
      await pumpScreen(tester, store, onScreen: false);
      expect(store.state.openThreadId, isNull);
      store.dispatch(
        _Patch(
          store.state.thread(threadId).mergeMessages([
            message('m5', 5, 'assistant', 'New while away', at(12)),
          ]),
        ),
      );
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));
      expect(reads(), [4]);

      // Back on screen: the open thread again, and what arrived is read.
      await pumpScreen(tester, store);
      expect(store.state.openThreadId, threadId);
      expect(reads(), [4, 5]);
    });

    testWidgets('«Show the latest» on a replaced card jumps to its successor', (
      tester,
    ) async {
      Json action(String id, int timelineSeq, {String? supersededBy}) => {
        'id': id,
        'kind': 'trading_mode',
        'status': supersededBy == null ? 'pending' : 'expired',
        'status_reason': null,
        'superseded_by': supersededBy,
        'source': 'system',
        'agent_id': agentId,
        'thread_id': threadId,
        'run_id': null,
        'timeline_seq': timelineSeq,
        'facts': {
          'several_accounts': false,
          'agent': {'exists': true, 'id': agentId, 'name': 'Atlas'},
          'trading_mode': 'ask',
          'active_grant': false,
        },
        'requires_passkey': false,
        'result': <String, Object?>{},
        'expires_at': '2036-11-24T02:11:09.161728+00:00',
        'decided_at': null,
        'decided_via': null,
        'created_at': iso(at(5)),
        'updated_at': iso(at(5)),
      };
      final base = mixedState('en');
      final t = base.thread(threadId);
      final state = base.withThread(
        t.copyWith(
          runs: const {},
          side: {
            SideKeys.ownerActions: [
              action('oa-1', 2, supersededBy: 'oa-2'),
              action('oa-2', 4),
            ],
          },
        ),
      );
      await pumpScreen(tester, Store<AppState>(initialState: state));
      await scrollBack(tester);
      await tester.tap(find.text('Show the latest'));
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 400));
      expect(flashOf(tester, 'c:owner_action:oa-2'), isNotNull);
      await tester.pump(const Duration(seconds: 2));

      // A card that is not in the loaded transcript says so.
      const TimelineCardJumpNotification('owner_action:gone')
          .dispatch(tester.element(find.byType(MessageTile).first));
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text('The message is no longer available.'), findsOneWidget);
      await settleToasts(tester);
    });

    testWidgets('a call log is a call row that calls the agent back', (
      tester,
    ) async {
      final state = conversationState(
        messages: [
          message('m1', 1, 'user', 'Call me when you can.', at(5)),
          Message.fromJson({
            ...messageJson(
              id: 'm2',
              seq: 2,
              role: 'system',
              content: 'Missed voice call',
              createdAt: at(6),
            ),
            'agent_id': agentId,
            'rich_content': {
              'version': 1,
              'parts': [
                {
                  'type': 'call',
                  'direction': 'outgoing',
                  'duration_seconds': 0,
                  'missed': true,
                },
              ],
            },
          }),
        ],
      );
      await pumpScreen(tester, Store<AppState>(initialState: state));
      expect(find.byType(SystemRow), findsNothing);
      final row = tester.widget<CallLogRow>(find.byType(CallLogRow));
      expect(row.part.missed, isTrue);
      expect(row.onCallBack, isNotNull);
      expect(find.textContaining('Missed voice call'), findsOneWidget);
      expect(find.textContaining('Tap to call back'), findsOneWidget);
    });

    testWidgets('the run banner resumes a waiting background run once', (
      tester,
    ) async {
      final base = mixedState('en');
      final routine = run(
        'rt',
        'waiting_takeover',
        trigger: 'routine',
        background: true,
        createdAt: at(12),
      );
      final state = base.withThread(
        base
            .thread(threadId)
            .copyWith(runs: {...base.thread(threadId).runs, 'rt': routine}),
      );
      final store = Store<AppState>(initialState: state);
      final answer = Completer<Object?>();
      fake.answers['POST /runs/rt/resume'] = (_) => answer.future;
      await pumpScreen(tester, store);
      expect(find.textContaining('Atlas · Waiting to resume'), findsOneWidget);
      await tester.tap(tappable('Resume'));
      await tester.pump(const Duration(milliseconds: 50));
      // The request is on its way: the buttons wait.
      await tester.tap(tappable('Resume'));
      await tester.pump(const Duration(milliseconds: 50));
      expect(
        fake.calls.where((c) => c.path == '/runs/rt/resume'),
        hasLength(1),
      );
      answer.complete({...routine.raw, 'status': 'queued'});
      await tester.pump(const Duration(milliseconds: 50));
      expect(find.textContaining('Waiting to resume'), findsNothing);
      expect(store.state.thread(threadId).runs['rt']!.status, 'queued');
    });

    testWidgets('Retry waits for the provider Retry-After', (tester) async {
      final state = conversationState(
        messages: [message('m1', 1, 'user', 'Price of gold?', at(5))],
        runs: {
          'rf': run(
            'rf',
            'failed',
            inputSeq: 1,
            createdAt: at(5),
            errorCode: 'rate_limited',
            failure: {'family': 'rate'},
          ),
        },
      );
      fake.answers['POST /runs/rf/retry'] = (_) => throw ApiError(
        status: 409,
        code: 'run_retry_too_early',
        retryAfter: const Duration(seconds: 1),
      );
      await pumpScreen(tester, Store<AppState>(initialState: state));
      RowTextButton retry() => tester.widget<RowTextButton>(
        find.byWidgetPredicate((w) => w is RowTextButton && w.label == 'Retry'),
      );
      expect(retry().enabled, isTrue);
      await tester.tap(tappable('Retry'));
      await tester.pump(const Duration(milliseconds: 100));
      expect(fake.calls.where((c) => c.path == '/runs/rf/retry'), hasLength(1));
      expect(retry().enabled, isFalse);
      // Retry-After is wall-clock time: let a real second pass, then the row's timer.
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 1100)),
      );
      await tester.pump(const Duration(seconds: 2));
      expect(retry().enabled, isTrue);
      await settleToasts(tester);
    });

    testWidgets('uploads show progress and cancel, and wait out an edit', (
      tester,
    ) async {
      final dir = Directory.systemTemp.createTempSync('lonora_conv_upload');
      File('${dir.path}/a.txt').writeAsStringSync('first');
      File('${dir.path}/b.txt').writeAsStringSync('second');
      pendingShare.value = SharedPayload(
        targetThreadId: threadId,
        files: [
          SharedFile(path: '${dir.path}/a.txt', name: 'a.txt', size: 5),
          SharedFile(path: '${dir.path}/b.txt', name: 'b.txt', size: 6),
        ],
      );
      await pumpScreen(tester, Store<AppState>(initialState: mixedState('en')));
      expect(fake.uploads, hasLength(2));
      expect(fake.uploads.first.fields, {'thread_id': threadId});
      fake.uploads.first.onProgress!(1, 2);
      await tester.pump();
      final chips = tester
          .widgetList<ComposerAttachmentChip>(
            find.byType(ComposerAttachmentChip),
          )
          .toList();
      expect(chips.first.progress, 0.5);

      // Cancel the first one; the second one finishes.
      await tester.tap(tappable('Cancel the upload').first);
      await tester.pump();
      expect(fake.uploads.first.token!.isCancelled, isTrue);
      fake.uploads.last.done.complete({
        'id': 'art-2',
        'payload': {'name': 'b.txt', 'size': 6, 'media_type': 'text/plain'},
      });
      await tester.pump();
      expect(find.byType(ComposerAttachmentChip), findsOneWidget);

      // An edit carries no files: the finished one waits for the next send.
      await scrollBack(tester);
      await tester.longPress(find.text('Can you check EUR/USD for today?'));
      await tester.pump(const Duration(milliseconds: 600));
      await tester.tap(find.text('Edit and resend'));
      await tester.pump(const Duration(milliseconds: 600));
      expect(find.byType(ComposerAttachmentChip), findsNothing);
      await tester.enterText(find.byType(TextField), 'Check EUR/USD please');
      await tester.pump();
      await tester.tap(tappable('Send'));
      await tester.pump(const Duration(milliseconds: 50));
      final edit = asJson(fake.calls.lastWhere((c) => c.method == 'POST').body);
      expect(edit['edited_from'], 'm1');
      expect(edit['attachment_ids'], isEmpty);
      expect(find.byType(ComposerAttachmentChip), findsOneWidget);

      await tester.enterText(find.byType(TextField), 'Here is the file');
      await tester.pump(const Duration(milliseconds: 600));
      await tester.tap(tappable('Send'));
      await tester.pump(const Duration(milliseconds: 50));
      final sent = asJson(fake.calls.lastWhere((c) => c.method == 'POST').body);
      expect(sent['attachment_ids'], ['art-2']);
      expect(find.byType(ComposerAttachmentChip), findsNothing);
      dir.deleteSync(recursive: true);
    });

    testWidgets('the web search chip turns web search off', (tester) async {
      fake.answers['PUT /threads/$threadId/options'] = (body) => {
        'id': threadId,
        'agent_id': agentId,
        'title': '',
        'options': {'web_search': asJson(body)['web_search']},
      };
      final store = Store<AppState>(
        initialState: conversationState(
          messages: [message('m1', 1, 'user', 'Search the news', at(5))],
          webSearch: true,
        ),
      );
      await pumpScreen(tester, store);
      await tester.tap(tappable('Web search is on, tap to turn it off'));
      await tester.pump(const Duration(milliseconds: 100));
      final put = fake.calls.singleWhere((c) => c.method == 'PUT');
      expect(put.path, '/threads/$threadId/options');
      expect(put.body, {'web_search': false});
      expect(store.state.thread(threadId).thread!.webSearch, isFalse);
      expect(tappable('Web search is on, tap to turn it off'), findsNothing);
      expect(find.text('Web search turned off'), findsOneWidget);
      await settleToasts(tester);
    });

    testWidgets('an older page that fails waits for Retry', (tester) async {
      final messages = [
        for (var i = 1; i <= 100; i++)
          message(
            'm$i',
            i,
            i.isOdd ? 'user' : 'assistant',
            'Line $i of a long conversation about markets.',
            DateTime(2025, 3, 14, 9).add(Duration(minutes: i)),
          ),
      ];
      final base = conversationState(messages: messages);
      serveThread(fake, base);
      fake.answers['GET /threads/$threadId/messages'] = (query) {
        if (asJson(query)['before'] != null) {
          throw ApiError(status: null, code: 'network');
        }
        return [for (final m in messages) m.raw];
      };
      await pumpScreen(tester, Store<AppState>(initialState: signedIn(base)));
      int olderReads() =>
          fake.calls.where((c) => asJson(c.body)['before'] != null).length;
      for (var i = 0; i < 12 && olderReads() == 0; i++) {
        await tester.drag(find.byType(ListView), const Offset(0, 3000));
        await tester.pump(const Duration(milliseconds: 300));
      }
      await tester.pump(const Duration(milliseconds: 300));
      expect(olderReads(), 1);
      expect(find.textContaining('Older messages'), findsOneWidget);
      // No new request on every scroll tick.
      await tester.drag(find.byType(ListView), const Offset(0, 300));
      await tester.pump(const Duration(milliseconds: 300));
      expect(olderReads(), 1);
      await tester.tap(tappable('Retry'));
      await tester.pump(const Duration(milliseconds: 300));
      expect(olderReads(), 2);
    });

    testWidgets('an older page of known messages is no failure', (
      tester,
    ) async {
      // The page arrives but adds nothing before the first message (the window's first seq
      // stays): only the action's error code means a page failed.
      final messages = [
        for (var i = 101; i <= 200; i++)
          message(
            'm$i',
            i,
            i.isOdd ? 'user' : 'assistant',
            'Line $i of a long conversation about markets.',
            DateTime(2025, 3, 14, 7).add(Duration(minutes: i)),
          ),
      ];
      final base = conversationState(messages: messages);
      serveThread(fake, base);
      fake.answers['GET /threads/$threadId/messages'] = (_) => [
        for (final m in messages) m.raw,
      ];
      await pumpScreen(tester, Store<AppState>(initialState: signedIn(base)));
      int olderReads() =>
          fake.calls.where((c) => asJson(c.body)['before'] != null).length;
      for (var i = 0; i < 12 && olderReads() == 0; i++) {
        await tester.drag(find.byType(ListView), const Offset(0, 3000));
        await tester.pump(const Duration(milliseconds: 300));
      }
      await tester.pump(const Duration(milliseconds: 300));
      expect(olderReads(), greaterThanOrEqualTo(1));
      expect(find.textContaining('Older messages'), findsNothing);
      expect(tappable('Retry'), findsNothing);
    });

    testWidgets('files alone are sent from the pill\'s own send disc', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      final dir = Directory.systemTemp.createTempSync('lonora_conv_files');
      File('${dir.path}/a.txt').writeAsStringSync('first');
      pendingShare.value = SharedPayload(
        targetThreadId: threadId,
        files: [SharedFile(path: '${dir.path}/a.txt', name: 'a.txt', size: 5)],
      );
      final store = Store<AppState>(
        initialState: conversationState(
          messages: [message('m1', 1, 'assistant', 'Send it over.', at(5))],
        ),
      );
      await pumpScreen(tester, store);
      fake.uploads.single.done.complete({
        'id': 'art-1',
        'payload': {'name': 'a.txt', 'size': 5, 'media_type': 'text/plain'},
      });
      // The trailing slot switches (mic out, send in) over two frames.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 300));
      // One trailing button: an enabled Send, with no mic left under it.
      expect(find.bySemanticsLabel('Voice message'), findsNothing);
      expect(find.byType(VoiceNoteButton), findsNothing);
      expect(
        tester.getSemantics(find.bySemanticsLabel('Send')),
        isSemantics(label: 'Send', isButton: true, isEnabled: true),
      );
      await tester.tap(tappable('Send'));
      await tester.pump(const Duration(milliseconds: 50));
      final sent = asJson(fake.calls.lastWhere((c) => c.method == 'POST').body);
      // Files alone carry the attachment label as their text (the composer's own rule).
      expect(sent['content'], 'Attach file');
      expect(sent['attachment_ids'], ['art-1']);
      dir.deleteSync(recursive: true);
      handle.dispose();
    });

    testWidgets('the voice-note mic is the pill\'s one mic', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpScreen(
        tester,
        Store<AppState>(
          initialState: conversationState(
            messages: [message('m1', 1, 'assistant', 'Hi.', at(5))],
          ),
        ),
      );
      expect(find.byType(VoiceNoteButton), findsOneWidget);
      expect(find.byIcon(FIcons.mic), findsOneWidget);
      expect(find.bySemanticsLabel('Voice message'), findsOneWidget);
      expect(
        tester.getSemantics(find.bySemanticsLabel('Voice message')),
        isSemantics(
          label: 'Voice message',
          hint: 'Tap to record hands-free',
          isButton: true,
          isEnabled: true,
        ),
      );
      handle.dispose();
    });

    testWidgets('the mic records hands-free and closes the keyboard', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      VoiceNoteButton.recorderFactory = _Recorder.new;
      VoiceNoteButton.recordingsDir = () async => Directory.systemTemp.path;
      addTearDown(() {
        VoiceNoteButton.recorderFactory = RecordVoiceNoteRecorder.new;
      });
      await pumpScreen(
        tester,
        Store<AppState>(
          initialState: conversationState(
            messages: [message('m1', 1, 'assistant', 'Hi.', at(5))],
          ),
        ),
      );
      await tester.tap(find.byType(TextField));
      await tester.pump();
      FocusNode field() =>
          tester.widget<TextField>(find.byType(TextField)).focusNode!;
      expect(field().hasFocus, isTrue);
      await tester.tap(find.bySemanticsLabel('Voice message'));
      await tester.pump();
      await tester.pump();
      // Recording: the bar takes the pill's place; the field gives up the keyboard.
      expect(find.byType(ComposerRecordingBar), findsOneWidget);
      expect(field().hasFocus, isFalse);
      // The hidden pill is out of the semantics tree.
      expect(find.bySemanticsLabel('Attach file'), findsNothing);
      await tester.pump(const Duration(seconds: 1));
      await tester.tap(find.bySemanticsLabel('Delete the recording'));
      await tester.pump(const Duration(milliseconds: 600));
      expect(find.byType(ComposerRecordingBar), findsNothing);
      expect(fake.uploads, isEmpty);
      await tester.tap(find.byType(TextField));
      await tester.pump();
      expect(field().hasFocus, isTrue);
      handle.dispose();
    });

    testWidgets('a long press on the empty composer records; release sends', (
      tester,
    ) async {
      VoiceNoteButton.recorderFactory = _Recorder.new;
      VoiceNoteButton.recordingsDir = () async => Directory.systemTemp.path;
      final sent = <double>[];
      final sender = VoiceNoteButton.sender;
      VoiceNoteButton.sender = (
        context, {
        required threadId,
        required path,
        required seconds,
        required peaks,
      }) async => sent.add(seconds);
      addTearDown(() {
        VoiceNoteButton.recorderFactory = RecordVoiceNoteRecorder.new;
        VoiceNoteButton.sender = sender;
      });
      await pumpScreen(
        tester,
        Store<AppState>(
          initialState: conversationState(
            messages: [message('m1', 1, 'assistant', 'Hi.', at(5))],
          ),
        ),
      );
      expect(find.text('Hold to talk, tap to type'), findsOneWidget);
      final gesture = await tester.startGesture(
        tester.getCenter(find.byType(EditableText)),
      );
      await tester.pump(const Duration(milliseconds: 600));
      await tester.pump();
      expect(find.byType(ComposerRecordingBar), findsOneWidget);
      await tester.pump(const Duration(seconds: 2));
      await gesture.up();
      await tester.pump();
      await tester.pump();
      expect(sent.single, closeTo(2, 0.21));
      expect(find.byType(ComposerRecordingBar), findsNothing);
      await settleToasts(tester);
    });

    testWidgets('a direct conversation names its agent in the hint and the '
        'capsule hint names the profile', (tester) async {
      await pumpScreen(tester, Store<AppState>(initialState: mixedState('en')));
      // Empty and unfocused, the composer says how to talk; focused, it names the agent.
      expect(find.text('Hold to talk, tap to type'), findsOneWidget);
      await tester.tap(find.byType(TextField));
      await tester.pump();
      expect(find.text('Message Atlas'), findsOneWidget);
      // The capsule opens the conversation's actions, and says so.
      expect(
        tester.widget<TitleCapsule>(find.byType(TitleCapsule)).semanticHint,
        'Agent actions',
      );
    });
  });
}

class _Patch extends ReduxAction<AppState> {
  _Patch(this.thread);
  final ThreadState thread;
  @override
  AppState reduce() => state.withThread(thread);
}

class _Recorder implements VoiceNoteRecorder {
  @override
  Future<PermissionStatus> permission() async => PermissionStatus.granted;
  @override
  Future<void> start(String path) async {}
  @override
  Future<String?> stop() async => null;
  @override
  Future<void> cancel() async {}
  @override
  Future<void> pause() async {}
  @override
  Future<void> resume() async {}
  @override
  Stream<double> levels() => const Stream.empty();
  @override
  Future<void> dispose() async {}
}
