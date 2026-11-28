// The composer's saved drafts, @mentions and «/» commands on the conversation screen, against the
// fake API: what each flow shows, the exact `POST /threads/{id}/messages` body it would send,
// the client-side commands (chart, call, clear), the skills read, Back, RTL, large text,
// semantics and goldens of both lists. No test reaches a server; none sends an order.
//
// Regenerate goldens: flutter test --update-goldens test/features/conversation/composer_assist_widget_test.dart
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/app/deep_links.dart' show SharedFile;
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/conversation/assist_list.dart';
import 'package:lonora/features/conversation/conversation_actions.dart';
import 'package:lonora/features/conversation/conversation_composer.dart';
import 'package:lonora/features/conversation/conversation_screen.dart';
import 'package:lonora/features/conversation/draft_store.dart';
import 'package:lonora/features/conversation/message_widgets.dart'
    show OutgoingTile;
import 'package:lonora/features/rich/rich_content_view.dart';
import 'package:lonora/features/voice/voice_api.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/fonts.dart';
import '../../design/harness.dart';
import 'conversation_harness.dart';

late L10n l10n;

/// Documents in memory: real file IO never completes inside `testWidgets`' fake async zone.
/// [gate], when set, holds every read until it completes (a slow phone).
class MemoryStore implements LocalStore {
  final Map<String, Object?> docs = {};
  Completer<void>? gate;

  @override
  Future<Object?> read(String scope, String name) async {
    await gate?.future;
    return docs['$scope/$name'];
  }

  @override
  Future<void> write(String scope, String name, Object? value) async {
    if (value == null) {
      docs.remove('$scope/$name');
    } else {
      docs['$scope/$name'] = value;
    }
  }

  @override
  Future<void> clearScope(String scope) async =>
      docs.removeWhere((key, _) => key.startsWith('$scope/'));
}

/// A voice call controller that only records what was asked.
class RecordingCalls extends VoiceCallController {
  final List<(String, String)> started = [];

  @override
  Future<void> start({
    required String agentId,
    required String threadId,
    String? incomingCallId,
  }) async => started.add((agentId, threadId));
}

final draftScope = LocalStore.scope('http://127.0.0.1:1', 'owner-1');

Agent namedAgent(
  String id,
  String name, {
  bool paused = false,
  String title = '',
}) => Agent.fromJson({
  'id': id,
  'name': name,
  'avatar': 'orb',
  'color': 'blue',
  'paused': paused,
  'title': title,
});

final nova = namedAgent('agent-2', 'Nova', title: 'Research');
final orion = namedAgent('agent-3', 'Orion', title: 'Macro');
final sleepy = namedAgent('agent-4', 'Sleepy', paused: true);

List<Message> transcript(String locale) => [
  message(
    'm1',
    1,
    'user',
    pick(locale, 'How is gold today?', 'كيف الذهب اليوم؟'),
    at(5),
  ),
  message(
    'm2',
    2,
    'assistant',
    pick(locale, 'Gold is up 0.4% on the day.', 'ارتفع الذهب ٠٫٤٪ اليوم.'),
    at(6),
  ),
];

/// A direct chat with Atlas; the owner has Nova, Orion and a paused agent too.
AppState directState(String locale, {List<Message>? messages}) {
  final base = conversationState(messages: messages ?? transcript(locale));
  final atlas = base.shell.agents[agentId]!;
  return signedIn(
    base.copyWith(
      shell: base.shell.copyWith(
        agents: {
          agentId: atlas,
          nova.id: nova,
          orion.id: orion,
          sleepy.id: sleepy,
        },
        agentOrder: [agentId, nova.id, orion.id, sleepy.id],
        inbox: [
          InboxEntry.fromJson({
            'thread_id': threadId,
            'agent_id': agentId,
            'last_message': {'id': 'm2', 'seq': 2},
            'last_read_seq': 2,
          }),
        ],
      ),
    ),
  );
}

/// The group «Desk» (Atlas leads; Nova and a paused member).
AppState groupState(String locale) {
  final base = directState(locale);
  final group = Group.fromJson({
    'id': 'group-1',
    'version': 1,
    'payload': {
      'name': 'Desk',
      'member_ids': [agentId, nova.id, sleepy.id],
      'lead_agent_id': agentId,
    },
  });
  final t = base.thread(threadId);
  return base
      .copyWith(shell: base.shell.copyWith(groups: {group.id: group}))
      .withThread(
        t.copyWith(
          thread: Thread.fromJson({
            'id': threadId,
            'group_id': group.id,
            'options': {'web_search': false},
          }),
        ),
      );
}

late FakeApi fake;
late MemoryStore drafts;

Future<Store<AppState>> pumpConversation(
  WidgetTester tester,
  AppState state, {
  String locale = 'en',
  Brightness brightness = Brightness.light,
  double textScale = 1,
}) async {
  setGoldenViewport(tester);
  serveThread(fake, state);
  final store = Store<AppState>(initialState: state);
  await tester.pumpWidget(
    conversationApp(
      store: store,
      l10n: l10n,
      locale: locale,
      brightness: brightness,
      textScale: textScale,
      child: const ConversationScreen(threadId: threadId),
    ),
  );
  await tester.pump(const Duration(milliseconds: 100));
  await tester.pump(const Duration(milliseconds: 400));
  return store;
}

/// The conversation under a router, so a command can open another page.
Future<GoRouter> pumpRouted(WidgetTester tester, AppState state) async {
  setGoldenViewport(tester);
  serveThread(fake, state);
  final router = GoRouter(
    initialLocation: '/c',
    routes: [
      GoRoute(
        path: '/c',
        builder: (_, _) => const ConversationScreen(threadId: threadId),
      ),
      GoRoute(
        path: '/charts',
        builder: (context, s) => Text('charts ${s.uri.query}'),
      ),
    ],
  );
  l10n.setLocale(const Locale('en'));
  await tester.pumpWidget(
    StoreProvider<AppState>(
      store: Store<AppState>(initialState: state),
      child: MaterialApp.router(
        routerConfig: router,
        locale: const Locale('en'),
        supportedLocales: L10n.supportedLocales,
        localizationsDelegates: [
          l10n.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
          ...FLocalizations.localizationsDelegates,
        ],
        builder: (context, app) => MediaQuery(
          data: MediaQuery.of(context).copyWith(disableAnimations: true),
          child: FTheme(
            data: lnForuiTheme(LnPalette.light),
            child: LnTheme(
              data: testTheme(Brightness.light),
              child: FToaster(child: app!),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump(const Duration(milliseconds: 500));
  return router;
}

Finder get field => find.byType(TextField);
TextEditingController controllerOf(WidgetTester tester) =>
    tester.widget<TextField>(field).controller!;

/// Types [text] with the caret at its end.
Future<void> type(WidgetTester tester, String text) async {
  await tester.enterText(field, text);
  await tester.pump();
}

/// A row of the @ or / list by the start of its spoken label.
Finder row(String label) => find.byWidgetPredicate(
  (w) =>
      w is LnTappable &&
      (w.semanticLabel?.startsWith(label) ?? false) &&
      w.excludeChildSemantics,
);

Finder button(String label) =>
    find.byWidgetPredicate((w) => w is LnTappable && w.semanticLabel == label);

List<({String method, String path, Object? body})> posts(String path) => [
  for (final c in fake.calls)
    if (c.method == 'POST' && c.path == path) c,
];

List<Json> sent() => [
  for (final c in posts('/threads/$threadId/messages')) asJson(c.body),
];

/// Nothing here may ever reach an order, a run or a webhook.
void expectNoForbiddenCalls() {
  for (final c in fake.calls) {
    expect(c.path.contains('/trading/execute'), isFalse, reason: c.path);
    expect(
      c.method == 'POST' && (c.path == '/runs' || c.path.contains('/webhook')),
      isFalse,
      reason: c.path,
    );
  }
}

Future<void> settle(WidgetTester tester) async {
  await tester.pump(const Duration(seconds: 5));
  await tester.pump(const Duration(seconds: 1));
}

Future<void> send(WidgetTester tester) async {
  await tester.tap(button(l10n.t('send')));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

/// Whether [span] marks [text] as a mention (the fill and the weight).
bool marked(InlineSpan span, String text) {
  var found = false;
  span.visitChildren((s) {
    if (s is TextSpan &&
        s.text == text &&
        s.style?.backgroundColor != null &&
        s.style?.fontWeight == FontWeight.w600) {
      found = true;
    }
    return !found;
  });
  return found;
}

/// The server's shell arrives (a cold start ends).
class SetShellAction extends ReduxAction<AppState> {
  SetShellAction(this.shell);
  final ShellState shell;

  @override
  AppState reduce() => state.copyWith(shell: shell);
}

void main() {
  setUpAll(() async {
    await loadAppFonts();
    l10n = await L10n.load();
  });

  setUp(() {
    fake = registerFakeApi();
    drafts = MemoryStore();
    if (sl.isRegistered<LocalStore>()) sl.unregister<LocalStore>();
    sl.registerSingleton<LocalStore>(MemoryStore());
    DraftStore.debugOverride = DraftStore(
      drafts,
      wipe: () async => drafts.docs.clear(),
    );
  });

  tearDown(() async {
    expectNoForbiddenCalls();
    if (sl.isRegistered<ApiClient>()) await sl.unregister<ApiClient>();
    ConversationComposerState.clearDrafts();
    DraftStore.debugOverride = null;
  });

  group('drafts', () {
    Json artifact() => {
      'id': 'art-1',
      'thread_id': threadId,
      'payload': {
        'name': 'notes.pdf',
        'media_type': 'application/pdf',
        'size': 4096,
      },
    };

    testWidgets('text, the reply and a finished file survive a restart, and '
        'Send removes them', (tester) async {
      final state = directState('en');
      var store = await pumpConversation(tester, state);
      // A file uploads, the owner replies to the agent and types.
      final composer = tester.state<ConversationComposerState>(
        find.byType(ConversationComposer),
      );
      composer.reply(state.thread(threadId).messages.last, 'Atlas');
      await tester.pump();
      await type(tester, 'Watch the 2,400 level');
      // Saved after a pause in typing.
      expect(drafts.docs, isEmpty);
      await tester.pump(const Duration(milliseconds: 450));
      final saved = drafts.docs['$draftScope/$threadId'] as Map?;
      expect(saved?['text'], 'Watch the 2,400 level');
      expect(asJson(saved?['reply'])['id'], 'm2');

      // A finished upload in the saved draft (as `/artifacts/upload` answered it).
      drafts.docs['$draftScope/$threadId'] = {
        ...saved!.cast<String, Object?>(),
        'files': [artifact()],
      };
      // Restart: the screen and the memory go, the phone's copy stays.
      await tester.pumpWidget(const SizedBox());
      ConversationComposerState.debugForgetMemory();
      store = await pumpConversation(tester, state);
      expect(controllerOf(tester).text, 'Watch the 2,400 level');
      expect(find.byType(ComposerReplyBar), findsOneWidget);
      expect(find.text('notes.pdf'), findsOneWidget);
      // Its bubble will resolve the file: the conversation knows it at once.
      expect(
        asJsonList(store.state.thread(threadId).side[artifactsSideKey])
            .map((a) => a['id']),
        contains('art-1'),
      );

      await send(tester);
      final body = sent().single;
      expect(body['content'], 'Watch the 2,400 level');
      expect(body['attachment_ids'], ['art-1']);
      expect(body['reply_to'], 'm2');
      expect(drafts.docs.containsKey('$draftScope/$threadId'), isFalse);
      expect(find.text('notes.pdf'), findsNothing);
    });

    testWidgets('a saved draft never overwrites what was typed meanwhile', (
      tester,
    ) async {
      drafts.docs['$draftScope/$threadId'] = {
        'v': 1,
        'thread_id': threadId,
        'text': 'old draft',
        'files': <Json>[],
        'reply': null,
        'mentions': <Json>[],
      };
      drafts.gate = Completer();
      await pumpConversation(tester, directState('en'));
      await type(tester, 'typed now');
      drafts.gate!.complete();
      await tester.pump(const Duration(milliseconds: 50));
      expect(controllerOf(tester).text, 'typed now');
    });

    testWidgets('a draft sent before its save never comes back', (
      tester,
    ) async {
      final state = directState('en');
      await pumpConversation(tester, state);
      await type(tester, 'sent at once');
      await send(tester);
      await tester.pump(const Duration(milliseconds: 500));
      expect(drafts.docs, isEmpty);
      await tester.pumpWidget(const SizedBox());
      await pumpConversation(tester, state);
      expect(controllerOf(tester).text, isEmpty);
    });

    testWidgets("an edit's text is never saved", (tester) async {
      final state = directState('en');
      await pumpConversation(tester, state);
      final composer = tester.state<ConversationComposerState>(
        find.byType(ConversationComposer),
      );
      composer.edit(state.thread(threadId).messages.first);
      await tester.pump(const Duration(milliseconds: 500));
      await type(tester, 'How is gold now?');
      await tester.pump(const Duration(milliseconds: 500));
      expect(drafts.docs.containsKey('$draftScope/$threadId'), isFalse);
    });

    testWidgets('the app going to the background saves at once; sign-out '
        'removes every draft', (tester) async {
      await pumpConversation(tester, directState('en'));
      await type(tester, 'half a thought');
      expect(drafts.docs, isEmpty);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump();
      expect(
        (drafts.docs['$draftScope/$threadId'] as Map?)?['text'],
        'half a thought',
      );
      for (final state in [
        AppLifecycleState.hidden,
        AppLifecycleState.inactive,
        AppLifecycleState.resumed,
      ]) {
        tester.binding.handleAppLifecycleStateChanged(state);
      }
      ConversationComposerState.clearDrafts();
      await tester.pump();
      expect(drafts.docs, isEmpty);
      // The composer of the signed-out session closes: nothing comes back.
      await type(tester, 'after sign-out');
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(milliseconds: 500));
      expect(drafts.docs, isEmpty);
    });

    testWidgets('a restored mention of an agent no longer offered is dropped', (
      tester,
    ) async {
      drafts.docs['$draftScope/$threadId'] = {
        'v': 1,
        'thread_id': threadId,
        'text': '@Nova @Gone hi',
        'files': <Json>[],
        'reply': null,
        'mentions': [
          {'agent_id': nova.id, 'token': '@Nova', 'start': 0, 'end': 5},
          {'agent_id': 'gone', 'token': '@Gone', 'start': 6, 'end': 11},
        ],
      };
      await pumpConversation(tester, directState('en'));
      expect(controllerOf(tester).text, '@Nova @Gone hi');
      await send(tester);
      expect(sent().single['mention_agent_ids'], [nova.id]);
    });

    testWidgets('mentions restored before the shell loads are kept; at Send '
        'the loaded shell drops only the agent it no longer has', (
      tester,
    ) async {
      drafts.docs['$draftScope/$threadId'] = {
        'v': 1,
        'thread_id': threadId,
        'text': '@Nova @Gone hi',
        'files': <Json>[],
        'reply': null,
        'mentions': [
          {'agent_id': nova.id, 'token': '@Nova', 'start': 0, 'end': 5},
          {'agent_id': 'gone', 'token': '@Gone', 'start': 6, 'end': 11},
        ],
      };
      final full = directState('en');
      // A cold start: neither the shell's cache nor the server's answer is in yet.
      final store = await pumpConversation(
        tester,
        full.copyWith(
          shell: full.shell.copyWith(agents: {}, agentOrder: [], loaded: false),
        ),
      );
      final composer = tester.state<ConversationComposerState>(
        find.byType(ConversationComposer),
      );
      expect(controllerOf(tester).text, '@Nova @Gone hi');
      expect(composer.controller.mentions, hasLength(2));
      store.dispatch(SetShellAction(full.shell));
      await tester.pump();
      await tester.pump();
      expect(
        tester
            .widget<ConversationComposer>(find.byType(ConversationComposer))
            .agents,
        isNotEmpty,
      );
      expect(composer.controller.mentions, hasLength(2));
      await send(tester);
      expect(sent().single['mention_agent_ids'], [nova.id]);
      expect(sent().single['content'], '@Nova @Gone hi');
    });

    testWidgets('a finished upload is saved with the draft (a running one is '
        'not) and comes back after a restart', (tester) async {
      final state = directState('en');
      await pumpConversation(tester, state);
      tester
          .state<ConversationComposerState>(find.byType(ConversationComposer))
          .addSharedFiles([
            const SharedFile(
              path: '/nonexistent/notes.pdf',
              name: 'notes.pdf',
              size: 4096,
            ),
          ]);
      await tester.pump();
      expect(fake.uploads, hasLength(1));
      await tester.pump(const Duration(milliseconds: 450));
      expect(drafts.docs, isEmpty);
      // `/artifacts/upload` answers.
      fake.uploads.single.done.complete(artifact());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 450));
      final saved = asJson(drafts.docs['$draftScope/$threadId']);
      expect(asJsonList(saved['files']).map((f) => f['id']), ['art-1']);
      expect(saved['text'], '');

      await tester.pumpWidget(const SizedBox());
      ConversationComposerState.debugForgetMemory();
      await pumpConversation(tester, state);
      expect(find.text('notes.pdf'), findsOneWidget);
      await send(tester);
      expect(sent().single['attachment_ids'], ['art-1']);
      expect(drafts.docs, isEmpty);
    });
  });

  group('@mentions', () {
    testWidgets('a group lists its active members, the lead tagged, and '
        '«@الكل» names every member', (tester) async {
      await pumpConversation(tester, groupState('ar'), locale: 'ar');
      await type(tester, '@');
      expect(find.byType(MentionList), findsOneWidget);
      expect(find.text('أعضاء المجموعة'), findsOneWidget);
      expect(find.text('@Atlas'), findsOneWidget);
      expect(find.text('@Nova'), findsOneWidget);
      expect(find.text('@Sleepy'), findsNothing);
      expect(find.text('القائد'), findsOneWidget);
      // Two members are not paused.
      expect(find.text('@الكل'), findsOneWidget);
      expect(find.text('تنبيه وكيلين'), findsOneWidget);
      // The suggestion chip gives way to the list.
      await tester.tap(row('@الكل'));
      await tester.pump();
      expect(controllerOf(tester).text, '@الكل ');
      expect(find.byType(MentionList), findsNothing);
      await tester.enterText(field, '@الكل راجعوا الذهب');
      await tester.pump();
      await send(tester);
      final body = sent().single;
      expect(body['mention_agent_ids'], [agentId, nova.id, sleepy.id]);
      expect(body['mention_all'], isFalse);
      expect(body.containsKey('collaboration_session_id'), isFalse);
      expect(body['content'], '@الكل راجعوا الذهب');
    });

    testWidgets('a direct chat offers «@الكل» only while a collaboration is '
        'open, and the send addresses that session', (tester) async {
      fake.answers['GET /threads/$threadId/collaboration'] = (_) => {
        'id': 's1',
        'thread_id': threadId,
        'state': {'status': 'collaborating'},
      };
      await pumpConversation(tester, directState('en'));
      await type(tester, 'please @a');
      // Atlas is this chat's own agent: never a guest. «al» matches «all» too.
      expect(find.text('@Atlas'), findsNothing);
      expect(find.text('@all'), findsOneWidget);
      expect(find.text('Bring an agent into the conversation'), findsOneWidget);
      await tester.tap(row('@all'));
      await tester.pump();
      expect(controllerOf(tester).text, 'please @all ');
      await send(tester);
      final body = sent().single;
      expect(body['mention_agent_ids'], isEmpty);
      expect(body['mention_all'], isTrue);
      expect(body['collaboration_session_id'], 's1');
    });

    testWidgets('no open collaboration: no «@all»; a guest is addressed by id '
        'until its token is edited', (tester) async {
      await pumpConversation(tester, directState('en'));
      await type(tester, '@');
      expect(find.text('@all'), findsNothing);
      expect(find.text('@Nova'), findsOneWidget);
      expect(find.text('@Orion'), findsOneWidget);
      expect(find.text('@Sleepy'), findsNothing);
      expect(find.text('@Atlas'), findsNothing);
      // The role line under the name.
      expect(find.text('Research'), findsOneWidget);
      await tester.tap(row('@Nova'));
      await tester.pump();
      await tester.enterText(field, '${controllerOf(tester).text}check this');
      await tester.pump();
      await send(tester);
      expect(sent().last['mention_agent_ids'], [nova.id]);
      expect(sent().last['mention_all'], isFalse);

      // Picked, then the token edited: the mention is gone.
      await type(tester, '@');
      await tester.tap(row('@Orion'));
      await tester.pump();
      final text = controllerOf(tester).text;
      await tester.enterText(field, text.replaceFirst('Orion', 'Orio'));
      await tester.pump();
      await send(tester);
      expect(sent().last['mention_agent_ids'], isEmpty);
    });

    testWidgets('a picked mention in a group addresses only it (a hand-typed '
        'name is the server\'s to read)', (tester) async {
      await pumpConversation(tester, groupState('en'));
      await type(tester, '@No');
      await tester.tap(row('@Nova'));
      await tester.pump();
      await tester.enterText(field, '${controllerOf(tester).text}and @Atlas');
      await tester.pump();
      // The list for the hand-typed name is open; send anyway.
      await send(tester);
      expect(sent().single['mention_agent_ids'], [nova.id]);
    });

    testWidgets('Back closes the list first, and it stays closed until the '
        'query changes', (tester) async {
      await pumpConversation(tester, directState('en'));
      await type(tester, '@');
      expect(find.byType(MentionList), findsOneWidget);
      final popped = await tester.binding.handlePopRoute();
      await tester.pump();
      expect(popped, isTrue);
      expect(find.byType(MentionList), findsNothing);
      expect(find.byType(ConversationScreen), findsOneWidget);
      await type(tester, '@N');
      expect(find.byType(MentionList), findsOneWidget);
      // Closed again, then the «@» typed anew: the list is back.
      await tester.binding.handlePopRoute();
      await tester.pump();
      expect(find.byType(MentionList), findsNothing);
      await type(tester, '');
      await type(tester, '@N');
      expect(find.byType(MentionList), findsOneWidget);
    });

    testWidgets('«اقتراحات @» off hides both lists; a typed command still '
        'sends', (tester) async {
      final state = directState('en');
      await pumpConversation(
        tester,
        state.copyWith(
          prefs: state.prefs.copyWith(
            chatPrefs: const ChatPrefs(assist: false),
          ),
        ),
      );
      await type(tester, '@');
      expect(find.byType(MentionList), findsNothing);
      await type(tester, '/');
      expect(find.byType(CommandList), findsNothing);
      await type(tester, '/search gold price');
      await send(tester);
      expect(sent().single['command'], {
        'name': 'search',
        'argument': 'gold price',
      });
    });

    testWidgets('mentions are marked in the field and in sent messages, the '
        'text unchanged', (tester) async {
      final state = directState(
        'en',
        messages: [
          message('m1', 1, 'user', 'Ask @Nova first', at(5)),
          message('m2', 2, 'assistant', 'Sure, **@Nova** and `@Nova`.', at(6)),
        ],
      );
      await pumpConversation(tester, state);
      final owner = tester.widget<RichText>(
        find.descendant(
          of: find.byType(OwnerText),
          matching: find.byType(RichText),
        ),
      );
      expect(owner.text.toPlainText(), 'Ask @Nova first');
      expect(marked(owner.text, '@Nova'), isTrue);
      final agent = find.byWidgetPredicate(
        (w) => w is RichText && w.text.toPlainText().startsWith('Sure'),
      );
      final span = tester.widget<RichText>(agent).text;
      expect(marked(span, '@Nova'), isTrue);
      // Code stays code.
      var codeMarked = 0;
      span.visitChildren((s) {
        if (s is TextSpan &&
            s.text != null &&
            s.text!.contains('@Nova') &&
            s.style?.backgroundColor != null) {
          codeMarked++;
        }
        return true;
      });
      expect(codeMarked, 2); // the mention, and the code run's own fill

      // In the field: the committed token is painted, the text stays as typed.
      await type(tester, '@');
      await tester.tap(row('@Nova'));
      await tester.pump();
      final editable = tester.widget<EditableText>(find.byType(EditableText));
      final built = editable.controller.buildTextSpan(
        context: tester.element(find.byType(EditableText)),
        withComposing: false,
      );
      expect(built.toPlainText(), '@Nova ');
      expect(
        (built.children!.first as TextSpan).style?.backgroundColor,
        isNotNull,
      );
    });

    testWidgets('a message still waiting to be sent marks its mentions as its '
        "server's copy will", (tester) async {
      fake.answers['POST /threads/$threadId/messages'] = (_) =>
          throw ApiError.network();
      final store = await pumpConversation(tester, directState('en'));
      await type(tester, 'Ask @Nova first');
      await send(tester);
      expect(store.state.outbox.single.delivery, Delivery.queued);
      await tester.pump(const Duration(milliseconds: 100));
      final owner = tester.widget<RichText>(
        find.descendant(
          of: find.byType(OutgoingTile),
          matching: find.descendant(
            of: find.byType(OwnerText),
            matching: find.byType(RichText),
          ),
        ),
      );
      expect(owner.text.toPlainText(), 'Ask @Nova first');
      expect(marked(owner.text, '@Nova'), isTrue);
    });
  });

  group('/ commands', () {
    testWidgets('«/» lists the six commands in order; a task needs its title', (
      tester,
    ) async {
      await pumpConversation(
        tester,
        directState('ar').copyWith(
          shell: directState('ar').shell.copyWith(
            agents: {
              ...directState('ar').shell.agents,
              agentId: Agent.fromJson({
                ...directState('ar').shell.agents[agentId]!.raw,
                'trading_symbol': 'XAUUSD',
              }),
            },
          ),
        ),
        locale: 'ar',
      );
      await type(tester, '/');
      expect(find.byType(CommandList), findsOneWidget);
      final rows = tester
          .widgetList<LnTappable>(row('/'))
          .map((w) => w.semanticLabel!.split('، ').first)
          .toList();
      expect(rows, ['/مهمة', '/بحث', '/ملخص', '/شارت', '/اتصال', '/مسح']);
      expect(find.text('الأوامر'), findsOneWidget);
      await tester.tap(row('/مهمة'));
      await tester.pump();
      expect(controllerOf(tester).text, '/مهمة ');
      expect(controllerOf(tester).selection.baseOffset, 6);
      // The hint says what to write.
      expect(find.text('عنوان المهمة'), findsOneWidget);
      await send(tester);
      expect(sent(), isEmpty);
      expect(
        find.text('اكتب عنوان المهمة بعد الأمر \u200e/مهمة'),
        findsOneWidget,
      );
      await settle(tester);
      await tester.enterText(field, '/مهمة راقب الذهب عند 2400');
      await tester.pump();
      await send(tester);
      final body = sent().single;
      expect(body['content'], '/مهمة راقب الذهب عند 2400');
      expect(body['command'], {
        'name': 'task',
        'argument': 'راقب الذهب عند 2400',
      });
      expect(body['mention_agent_ids'], isEmpty);
    });

    testWidgets('an unknown command says so; past a whole name the list '
        'closes', (tester) async {
      await pumpConversation(tester, directState('en'));
      await type(tester, '/zz');
      expect(find.text('No command by that name'), findsOneWidget);
      await type(tester, '/searching');
      expect(find.byType(CommandList), findsNothing);
    });

    testWidgets('«/summary» goes at once with the reply, once', (tester) async {
      final state = directState('en');
      await pumpConversation(tester, state);
      final composer = tester.state<ConversationComposerState>(
        find.byType(ConversationComposer),
      );
      composer.reply(state.thread(threadId).messages.last, 'Atlas');
      await tester.pump();
      await type(tester, '/sum');
      final summary = row('/summary');
      await tester.tap(summary);
      await tester.tap(summary, warnIfMissed: false);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      final body = sent().single;
      expect(body['content'], '/summary');
      expect(body['reply_to'], 'm2');
      expect(body['command'], {'name': 'summary', 'argument': ''});
      expect(body['attachment_ids'], isEmpty);
      expect(body['mention_all'], isFalse);
      expect(find.byType(ComposerReplyBar), findsNothing);
      expect(controllerOf(tester).text, isEmpty);
    });

    testWidgets('a command message waits for the network like plain text and '
        'its bubble shows the chip', (tester) async {
      fake.answers['POST /threads/$threadId/messages'] = (_) =>
          throw ApiError.network();
      final store = await pumpConversation(tester, directState('en'));
      await type(tester, '/search gold');
      await send(tester);
      final queued = store.state.outbox.single;
      expect(queued.delivery, Delivery.queued);
      expect(asJson(queued.body['command'])['name'], 'search');
      await tester.pump(const Duration(milliseconds: 100));
      // The chip, then only the words after the command.
      expect(find.byType(CommandChip), findsOneWidget);
      expect(find.text('/search gold'), findsNothing);
      expect(find.text('gold'), findsOneWidget);
    });

    testWidgets('«/clear» asks first; Cancel sends nothing, Clear hides the '
        'messages and the draft', (tester) async {
      fake.answers['POST /threads/$threadId/clear'] = (_) => {
        'thread_id': threadId,
        'last_read_seq': 2,
        'marked_unread': false,
        'hidden_before_seq': 2,
      };
      final store = await pumpConversation(tester, directState('en'));
      await type(tester, '/cle');
      await tester.tap(row('/clear'));
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('Clear the messages?'), findsOneWidget);
      expect(
        find.text(
          "This chat's messages are hidden for you. The agent and its record stay.",
        ),
        findsOneWidget,
      );
      await tester.tap(find.text('Cancel'));
      await tester.pump(const Duration(milliseconds: 400));
      expect(posts('/threads/$threadId/clear'), isEmpty);
      expect(find.text('Gold is up 0.4% on the day.'), findsOneWidget);

      await type(tester, 'a draft');
      await tester.pump(const Duration(milliseconds: 450));
      await type(tester, '/clear');
      await send(tester);
      await tester.pump(const Duration(milliseconds: 400));
      // A double tap on Clear clears once and keeps the conversation. The second tap lands
      // during the dialog's exit, where the route ignores it; two taps inside one frame
      // would both reach the kit dialog's button (sheets.dart `showLnConfirm`, critic T7):
      // that guard belongs to the frozen kit, not to the composer.
      final clear = find.widgetWithText(FButton, 'Clear');
      await tester.tap(clear);
      await tester.pump(const Duration(milliseconds: 16));
      await tester.tap(clear, warnIfMissed: false);
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pump(const Duration(milliseconds: 400));
      expect(posts('/threads/$threadId/clear'), hasLength(1));
      expect(find.byType(ConversationScreen), findsOneWidget);
      // The server's copy still has them: the floor hides them.
      expect(store.state.thread(threadId).messages, isEmpty);
      expect(find.text('Gold is up 0.4% on the day.'), findsNothing);
      expect(controllerOf(tester).text, isEmpty);
      expect(drafts.docs, isEmpty);
      await settle(tester);
    });

    testWidgets('a refused clear says why and keeps the messages', (
      tester,
    ) async {
      fake.answers['POST /threads/$threadId/clear'] = (_) =>
          throw ApiError.network();
      await pumpConversation(tester, groupState('en'));
      await type(tester, '/clear');
      await send(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(
        find.text(
          "This chat's messages are hidden for you. The group stays with its members.",
        ),
        findsOneWidget,
      );
      await tester.tap(find.widgetWithText(FButton, 'Clear'));
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text(l10n.errorText('network')), findsOneWidget);
      expect(find.text('Gold is up 0.4% on the day.'), findsOneWidget);
      await settle(tester);
    });

    testWidgets('«/call» starts the call with this agent', (tester) async {
      final calls = RecordingCalls();
      final before = VoiceCalls.controller;
      VoiceCalls.controller = calls;
      addTearDown(() => VoiceCalls.controller = before);
      await pumpConversation(tester, directState('en'));
      await type(tester, '/call');
      await tester.tap(row('/call'));
      await tester.pump();
      expect(calls.started, [(agentId, threadId)]);
      expect(controllerOf(tester).text, isEmpty);
      expect(sent(), isEmpty);
    });

    testWidgets('«/chart» opens the charts of this conversation', (
      tester,
    ) async {
      final state = directState('en');
      await pumpRouted(
        tester,
        state.copyWith(
          shell: state.shell.copyWith(
            agents: {
              ...state.shell.agents,
              agentId: Agent.fromJson({
                ...state.shell.agents[agentId]!.raw,
                'trading_symbol': 'XAUUSD',
              }),
            },
          ),
        ),
      );
      await type(tester, '/ch');
      expect(find.text('Open the XAUUSD chart'), findsOneWidget);
      await tester.tap(row('/chart'));
      await tester.pump(const Duration(milliseconds: 500));
      expect(
        find.text('charts thread=$threadId&agent=$agentId'),
        findsOneWidget,
      );
    });

    testWidgets("the agent's skills load once after «/», and a skill row sends "
        'its id', (tester) async {
      var reads = 0;
      fake.answers['GET /skills'] = (query) {
        reads++;
        if (reads == 1) throw ApiError(status: 500, code: 'request_failed');
        return [
          {
            'id': 'sk1',
            'agent_id': agentId,
            'payload': {
              'name': 'Gold brief',
              'manifest': {'description': 'A short gold read'},
            },
          },
          {
            'id': 'sk2',
            'agent_id': agentId,
            'payload': {'name': 'Off', 'enabled': false},
          },
        ];
      };
      await pumpConversation(tester, directState('en'));
      await type(tester, 'hello');
      expect(reads, 0);
      await type(tester, '/');
      await tester.pump();
      // The read failed: the built-in commands still show.
      expect(reads, 1);
      expect(row('/task'), findsOneWidget);
      expect(find.text("Atlas's skills"), findsNothing);
      // The next «/» tries again.
      await type(tester, '');
      await type(tester, '/');
      await tester.pump();
      expect(reads, 2);
      expect(fake.calls.lastWhere((c) => c.path == '/skills').body, {
        'agent_id': agentId,
      });
      expect(find.text('\u2068Atlas\u2069\'s skills'), findsOneWidget);
      expect(row('/Off'), findsNothing);
      await type(tester, '/gold');
      await tester.tap(row('/Gold brief'));
      await tester.pump();
      expect(controllerOf(tester).text, '/Gold brief ');
      await type(tester, '/Gold brief today');
      await send(tester);
      expect(sent().single['command'], {
        'name': 'skill',
        'argument': 'today',
        'skill_id': 'sk1',
      });
      // Loaded once: later «/» do not read again.
      await type(tester, '/');
      expect(reads, 2);
    });

    testWidgets('a group never reads skills and offers no task or call', (
      tester,
    ) async {
      await pumpConversation(tester, groupState('en'));
      await type(tester, '/');
      final rows = tester
          .widgetList<LnTappable>(row('/'))
          .map((w) => w.semanticLabel!.split(', ').first)
          .toList();
      expect(rows, ['/search', '/summary', '/chart', '/clear']);
      expect(fake.calls.where((c) => c.path == '/skills'), isEmpty);
      // A group has no open collaboration to read.
      expect(
        fake.calls.where((c) => c.path.endsWith('/collaboration')),
        isEmpty,
      );
    });
  });

  group('layout and accessibility', () {
    testWidgets('the lists are labelled, every row a 48 dp button', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpConversation(tester, groupState('en'));
      await type(tester, '/');
      expect(find.bySemanticsLabel('Commands'), findsWidgets);
      for (final r in tester.widgetList<LnTappable>(row('/'))) {
        final size = tester.getSize(find.byWidget(r));
        expect(size.height, greaterThanOrEqualTo(48), reason: r.semanticLabel);
      }
      const search = '/search, Search the web, then answer with sources';
      expect(
        tester.getSemantics(find.bySemanticsLabel(search)),
        isSemantics(label: search, isButton: true, hasTapAction: true),
      );
      await type(tester, '@');
      expect(find.bySemanticsLabel('Mention an agent'), findsWidgets);
      for (final r in tester.widgetList<LnTappable>(row('@'))) {
        expect(
          tester.getSize(find.byWidget(r)).height,
          greaterThanOrEqualTo(48),
        );
      }
      expect(
        tester.widget<LnTappable>(row('@Atlas')).semanticLabel,
        '@Atlas, Lead',
      );
      // The field keeps the keyboard: focus stays in it after a pick.
      await tester.tap(row('@Nova'));
      await tester.pump();
      expect(
        tester
            .widget<EditableText>(find.byType(EditableText))
            .focusNode
            .hasFocus,
        isTrue,
      );
      handle.dispose();
    });

    testWidgets('large text (1.3) lays out both lists without overflow', (
      tester,
    ) async {
      await pumpConversation(
        tester,
        groupState('ar'),
        locale: 'ar',
        textScale: 1.3,
      );
      await type(tester, '/');
      expect(tester.takeException(), isNull);
      await type(tester, '@');
      expect(tester.takeException(), isNull);
    });

    testWidgets('in Arabic the «/» reads before the name, rows start at the '
        'right', (tester) async {
      await pumpConversation(tester, directState('ar'), locale: 'ar');
      await type(tester, '/');
      final task = row('/مهمة');
      final rich = tester
          .widgetList<RichText>(
            find.descendant(of: task, matching: find.byType(RichText)),
          )
          .map((r) => r.text.toPlainText())
          .where((t) => t.contains('مهمة'));
      expect(rich.first, startsWith('\u200f/مهمة'));
      final list = tester.getRect(find.byType(CommandList));
      final icon = tester.getRect(
        find.descendant(of: task, matching: find.byType(Icon)).first,
      );
      expect(icon.center.dx, greaterThan(list.center.dx));
    });
  });

  group('goldens', () {
    for (final kind in ['commands', 'mentions']) {
      for (final locale in ['ar', 'en']) {
        for (final brightness in Brightness.values) {
          final name = 'assist_${kind}_${brightness.name}_$locale';
          testWidgets(name, (tester) async {
            await withRealShadows(() async {
              await pumpConversation(
                tester,
                kind == 'commands' ? directState(locale) : groupState(locale),
                locale: locale,
                brightness: brightness,
              );
              await type(tester, kind == 'commands' ? '/' : '@');
              await tester.pump(const Duration(milliseconds: 300));
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
}
