// The Chats tab's two homes through the app's own router and shell. The last-conversation home:
// the last opened conversation (else Lonora's own chat, else the list) with the chat list in the
// start-side drawer behind the ☰ button and its unread count of the other chats; a chat opened
// from the drawer replaces the conversation and closes it; back closes it first; links to a
// conversation land at the root; «All chats» opens the full list. The list home keeps the list at
// the root and pushes conversations over it. Goldens of the open drawer (light/dark × ar/en) and
// of its «+» menu.
//
// Regenerate the goldens with: flutter test --update-goldens test/features/chats/drawer_home_test.dart
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/app/app_strings.dart';
import 'package:lonora/app/router.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/chats/chat_drawer.dart';
import 'package:lonora/features/chats/chats_home.dart';
import 'package:lonora/features/chats/chats_screen.dart';
import 'package:lonora/features/conversation/conversation_header.dart';
import 'package:lonora/features/conversation/conversation_screen.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/actions/prefs_actions.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart' show withRealShadows;
import 'harness.dart';

Json _message(String thread, String id, int seq, String role, String text) => {
  'id': id,
  'thread_id': thread,
  'seq': seq,
  'role': role,
  'agent_id': role == 'assistant' ? 'a-${thread.substring(2)}' : null,
  'content': text,
  'created_at': DateTime(2026, 11, 27, 10, seq).toUtc().toIso8601String(),
};

/// Answers a conversation's snapshot: its thread and a short transcript.
void _answerThread(String thread, {String? agent, String? group}) {
  fakeApi.handlers['GET /threads/$thread'] = (_, _) => {
    'id': thread,
    'agent_id': agent,
    'group_id': group,
    'title': '',
  };
  fakeApi.handlers['GET /threads/$thread/messages'] = (_, _) => [
    _message(thread, '$thread-1', 1, 'user', 'Good morning'),
    _message(thread, '$thread-2', 2, 'assistant', 'Morning! All quiet so far.'),
  ];
  fakeApi.handlers['GET /runs'] = (_, _) => <Object>[];
  fakeApi.handlers['POST /threads/$thread/read'] = (_, _) =>
      <String, Object?>{};
}

void _answerThreads() {
  _answerThread('t-lonora', agent: 'a-lonora');
  _answerThread('t-gold', agent: 'a-gold');
  _answerThread('t-news', agent: 'a-news');
}

AppState _state({HomeMode mode = HomeMode.lastChat, List<Json>? inbox}) {
  final base = fixtureState(inbox: inbox, working: false);
  return base.copyWith(prefs: base.prefs.copyWith(homeMode: mode));
}

Future<(Store<AppState>, GoRouter)> _pump(
  WidgetTester tester, {
  AppState? state,
  String locale = 'en',
  Brightness brightness = Brightness.light,
  String? location,
  double textScale = 1,
  bool animations = false,
}) async {
  setGoldenViewport(tester);
  final store = Store<AppState>(initialState: state ?? _state());
  final router = buildRouter(store);
  addTearDown(router.dispose);
  await tester.pumpWidget(
    featureApp(
      store: store,
      router: router,
      locale: locale,
      brightness: brightness,
      textScale: textScale,
      // The harness turns animations off (reduced motion); some tests want them on.
      wrap: animations
          ? (app) => Builder(
              builder: (context) => MediaQuery(
                data: MediaQuery.of(context).copyWith(disableAnimations: false),
                child: app,
              ),
            )
          : null,
    ),
  );
  await tester.pump();
  if (location != null) router.go(location);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
  return (store, router);
}

ConversationScreen _home(WidgetTester tester) =>
    tester.widget<ConversationScreen>(find.byType(ConversationScreen));

Future<void> _openDrawer(WidgetTester tester) async {
  await tester.tap(find.byType(MenuPillButton));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
}

void main() {
  setUpAll(() async {
    await setUpFeatureHarness();
    registerAppStrings();
  });
  setUp(() async {
    resetFakeApi();
    _answerThreads();
    // The last conversation is kept on the device: every test starts without one.
    await devicePrefs.clear();
  });

  group('last-conversation home', () {
    testWidgets('opens on Lonora\'s own chat, then on the last opened one', (
      tester,
    ) async {
      final (store, _) = await _pump(tester);
      expect(_home(tester).threadId, 't-lonora');
      expect(_home(tester).home, isTrue);
      // Opened, it is kept as this owner's last conversation on this server.
      expect(lastThreadOf(store.state.session), 't-lonora');

      rememberLastThread(store.state.session, 't-news');
      await tester.pumpWidget(const SizedBox());
      await _pump(tester);
      expect(_home(tester).threadId, 't-news');
    });

    testWidgets('with no conversation to open, the home is the chat list', (
      tester,
    ) async {
      await _pump(
        tester,
        state: _state(
          inbox: [
            for (final e in fixtureInbox())
              if (e['thread_id'] != 't-lonora') e,
          ],
        ),
      );
      expect(find.byType(ConversationScreen), findsNothing);
      expect(find.byType(ChatsScreen), findsOneWidget);
      expect(find.byType(MenuPillButton), findsNothing);
    });

    testWidgets('☰ counts the unread of the other chats only', (tester) async {
      final handle = tester.ensureSemantics();
      final (store, router) = await _pump(tester);
      // Gold desk 3 + Morning news (marked) 1; muted and archived chats do not count.
      final pill = tester.widget<MenuPillButton>(find.byType(MenuPillButton));
      expect(pill.unreadCount, 4);
      expect(unreadElsewhere(store.state.shell, 't-lonora'), 4);
      expect(unreadElsewhere(store.state.shell, 't-gold'), 1);
      expect(
        tester.getSemantics(find.bySemanticsLabel('Chat list, 4 unread')),
        isSemantics(isButton: true, hasTapAction: true),
      );
      // On Gold desk's own conversation, its unread are not "elsewhere".
      router.go(Routes.thread('t-gold'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(
        tester.widget<MenuPillButton>(find.byType(MenuPillButton)).unreadCount,
        1,
      );
      handle.dispose();
    });

    testWidgets(
      'the drawer lists every chat; a row replaces the conversation',
      (tester) async {
        final (store, router) = await _pump(tester);
        await _openDrawer(tester);
        expect(find.byType(ChatDrawer), findsOneWidget);
        final rows = tester
            .widgetList<ChatListRow>(
              find.descendant(
                of: find.byType(ChatDrawer),
                matching: find.byType(ChatListRow),
              ),
            )
            .toList();
        // Every chat but the archived one, then «All chats».
        expect(rows.map((r) => r.title), [
          'Lonora',
          'Gold desk',
          'Morning news',
          'Trading desk',
          'Research',
          'FX watcher',
          'Reading club',
          'All chats',
        ]);
        expect(rows.every((r) => r.compact), isTrue);
        expect(rows.first.current, isTrue);
        expect(rows[1].unreadCount, 3);
        expect(rows[2].unreadDot, isTrue);
        expect(rows.first.pinned, isTrue);
        expect(rows[3].muted, isTrue);
        // The rows sit at the compact pitch.
        final lonora = tester.getRect(
          find.widgetWithText(ChatListRow, 'Lonora'),
        );
        expect(lonora.height, ChatListRow.compactPitch);
        // Opening the drawer marks nothing read.
        expect(fakeApi.callsTo('POST', '/threads/t-gold/read'), isEmpty);

        await tester.tap(find.widgetWithText(ChatListRow, 'Gold desk'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(_home(tester).threadId, 't-gold');
        expect(_home(tester).home, isTrue);
        expect(find.byType(ChatDrawer), findsNothing);
        expect(
          router.routerDelegate.currentConfiguration.uri.toString(),
          Routes.home('t-gold'),
        );
        // One conversation at the root: nothing to go back to.
        expect(router.canPop(), isFalse);
        expect(lastThreadOf(store.state.session), 't-gold');
      },
    );

    for (final animations in [true, false]) {
      testWidgets('a chat without a conversation yet opens once the server '
          'made it (${animations ? 'animated' : 'reduced motion'})', (
        tester,
      ) async {
        // FX watcher has no conversation: the drawer asks for one, slowly.
        _answerThread('t-fx', agent: 'a-fx');
        fakeApi.handlers['POST /agents/a-fx/conversation'] = (_, _) =>
            Future<Object?>.delayed(
              const Duration(milliseconds: 600),
              () => {'id': 't-fx', 'agent_id': 'a-fx'},
            );
        final (store, router) = await _pump(tester, animations: animations);
        await _openDrawer(tester);
        await tester.tap(find.widgetWithText(ChatListRow, 'FX watcher'));
        await tester.pump();
        // A second tap while it waits asks nothing more.
        await tester.tap(find.widgetWithText(ChatListRow, 'FX watcher'));
        // Frame by frame past the drawer's own closing time (320 ms).
        for (var i = 0; i < 10; i++) {
          await tester.pump(const Duration(milliseconds: 50));
        }
        // Still waiting: the drawer stays open on the current conversation.
        expect(find.byType(ChatDrawer), findsOneWidget);
        expect(_home(tester).threadId, 't-lonora');
        for (var i = 0; i < 16; i++) {
          await tester.pump(const Duration(milliseconds: 50));
        }
        expect(
          fakeApi.callsTo('POST', '/agents/a-fx/conversation'),
          hasLength(1),
        );
        expect(_home(tester).threadId, 't-fx');
        expect(_home(tester).home, isTrue);
        expect(find.byType(ChatDrawer), findsNothing);
        expect(
          router.routerDelegate.currentConfiguration.uri.toString(),
          Routes.home('t-fx'),
        );
        expect(lastThreadOf(store.state.session), 't-fx');
      });
    }

    testWidgets('a conversation pushed over the home leaves the home as it '
        'was', (tester) async {
      // The bare home (cold start, a tab re-tap, a share) on Lonora's chat.
      final (store, router) = await _pump(tester);
      expect(
        router.routerDelegate.currentConfiguration.uri.toString(),
        Routes.chats,
      );
      expect(_home(tester).threadId, 't-lonora');
      // Another page pushes a conversation: it is the last opened one now…
      unawaited(router.push(Routes.thread('t-gold')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));
      final shown = tester
          .widgetList<ConversationScreen>(find.byType(ConversationScreen))
          .toList();
      expect(shown.last.threadId, 't-gold');
      expect(shown.last.home, isFalse, reason: 'pushed: back, not ☰');
      expect(lastThreadOf(store.state.session), 't-gold');
      // …but the home under it stays Lonora's chat.
      expect(
        tester
            .widgetList<ConversationScreen>(
              find.byType(ConversationScreen, skipOffstage: false),
            )
            .map((w) => w.threadId),
        containsAll(['t-lonora', 't-gold']),
      );
      router.pop();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));
      expect(_home(tester).threadId, 't-lonora');
      expect(_home(tester).home, isTrue);
      // A tab re-tap (the bare home again) keeps it too.
      router.go(Routes.chats);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));
      expect(_home(tester).threadId, 't-lonora');
    });

    testWidgets('large text (1.3) lays the drawer out without overflow', (
      tester,
    ) async {
      await _pump(tester, locale: 'ar', textScale: 1.3);
      await _openDrawer(tester);
      expect(find.byType(ChatDrawer), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('back closes the drawer before anything else', (tester) async {
      await _pump(tester);
      await _openDrawer(tester);
      expect(find.byType(ChatDrawer), findsOneWidget);
      await tester.binding.handlePopRoute();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(ChatDrawer), findsNothing);
      expect(_home(tester).threadId, 't-lonora');
    });

    testWidgets('the card closes the drawer and names its action', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await _pump(tester);
      await _openDrawer(tester);
      expect(find.bySemanticsLabel('Close the chat list'), findsOneWidget);
      // The card's visible strip at the end side.
      final size = tester.view.physicalSize / tester.view.devicePixelRatio;
      await tester.tapAt(Offset(size.width - 30, size.height / 2));
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(ChatDrawer), findsNothing);
      handle.dispose();
    });

    for (final locale in ['en', 'ar']) {
      testWidgets('the drawer opens from the start side ($locale)', (
        tester,
      ) async {
        await _pump(tester, locale: locale);
        await _openDrawer(tester);
        final width =
            tester.view.physicalSize.width / tester.view.devicePixelRatio;
        final drawer = tester.getRect(find.byType(ChatDrawer));
        expect(drawer.width, LnDrawerScaffold.drawerWidthFor(width));
        if (locale == 'ar') {
          expect(drawer.right, width);
        } else {
          expect(drawer.left, 0);
        }
        // Search at the start, «+» at the end, 48 dp targets.
        final search = tester.getRect(
          find.descendant(
            of: find.byType(ChatDrawer),
            matching: find.byWidgetPredicate(
              (w) =>
                  w is CircleIconButton &&
                  w.semanticLabel == L10n.instance.t('sh_search'),
            ),
          ),
        );
        expect(search.size, const Size(48, 48));
        expect(
          locale == 'ar' ? width - search.right : search.left,
          LnSpace.pageGutter - 2,
        );
      });
    }

    testWidgets(
      'a link to a conversation lands at the root, around a message',
      (tester) async {
        final (_, router) = await _pump(tester);
        router.go(Routes.thread('t-news', around: 2));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(_home(tester).threadId, 't-news');
        expect(_home(tester).around, 2);
        expect(
          router.routerDelegate.currentConfiguration.uri.toString(),
          Routes.home('t-news', around: 2),
        );
      },
    );

    testWidgets(
      '«All chats» opens the full list; a chat there becomes the home',
      (tester) async {
        final (_, router) = await _pump(tester);
        await _openDrawer(tester);
        await tester.tap(find.widgetWithText(ChatListRow, 'All chats'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        final list = find.byWidgetPredicate(
          (w) => w is ChatsScreen && w.pushed,
        );
        expect(list, findsOneWidget);
        // The full list (filters, lists, archived, selection) with a back circle.
        expect(
          find.byWidgetPredicate(
            (w) => w is CircleIconButton && w.semanticLabel == 'Back',
          ),
          findsOneWidget,
        );
        await tester.tap(find.widgetWithText(ChatListRow, 'Morning news'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(list, findsNothing);
        expect(_home(tester).threadId, 't-news');
        expect(router.canPop(), isFalse);
      },
    );

    testWidgets('«+» offers new agent, new group and the agents', (
      tester,
    ) async {
      await _pump(tester);
      await _openDrawer(tester);
      await tester.tap(
        find.descendant(
          of: find.byType(ChatDrawer),
          matching: find.byWidgetPredicate(
            (w) => w is CircleIconButton && w.semanticLabel == 'New chat',
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LnMenuCard), findsOneWidget);
      expect(find.text('New agent'), findsOneWidget);
      expect(find.text('New group'), findsOneWidget);
      expect(find.text('Manage agents'), findsOneWidget);
    });

    testWidgets('a long press on a row opens the list\'s row menu; «Select» '
        'starts the selection on the full list', (tester) async {
      await _pump(tester);
      await _openDrawer(tester);
      await tester.longPress(find.widgetWithText(ChatListRow, 'Gold desk'));
      await tester.pump(const Duration(milliseconds: 400));
      for (final label in [
        'Agent profile',
        'Mark as read',
        'Pin',
        'Mute notifications',
        'Archive',
        'Select',
      ]) {
        expect(find.text(label), findsOneWidget, reason: label);
      }
      await tester.tap(find.text('Select'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      final list = tester.widget<ChatsScreen>(
        find.byWidgetPredicate((w) => w is ChatsScreen && w.pushed),
      );
      expect(list.select, 'agent:a-gold');
      // The selection toolbar replaces the list's header.
      expect(find.text('1'), findsWidgets);
    });

    testWidgets('the conversation header: ☰ at the start, call at the end', (
      tester,
    ) async {
      await _pump(tester, location: Routes.thread('t-gold'));
      final header = find.byType(ConversationHeader);
      final pill = tester.getRect(find.byType(MenuPillButton));
      final call = tester.getRect(
        find.descendant(
          of: header,
          matching: find.byWidgetPredicate(
            (w) => w is CircleIconButton && w.semanticLabel == 'Call agent',
          ),
        ),
      );
      expect(pill.left, LnSpace.pageGutter - 2);
      final width =
          tester.view.physicalSize.width / tester.view.devicePixelRatio;
      expect(width - call.right, LnSpace.pageGutter - 2);
      expect(call.size, const Size(48, 48));
      // No back circle on the home conversation.
      expect(
        find.descendant(
          of: header,
          matching: find.byWidgetPredicate(
            (w) => w is CircleIconButton && w.semanticLabel == 'Back',
          ),
        ),
        findsNothing,
      );
    });

    for (final (brightness, locale) in [
      (Brightness.dark, 'ar'),
      (Brightness.dark, 'en'),
      (Brightness.light, 'ar'),
      (Brightness.light, 'en'),
    ]) {
      final name = '${brightness.name}_$locale';
      testWidgets('golden drawer open $name', (tester) async {
        await withRealShadows(() async {
          await _pump(tester, locale: locale, brightness: brightness);
          await _openDrawer(tester);
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile('goldens/drawer_open_$name.png'),
          );
        });
      });
    }

    testWidgets('golden drawer + menu dark ar', (tester) async {
      await withRealShadows(() async {
        await _pump(tester, locale: 'ar', brightness: Brightness.dark);
        await _openDrawer(tester);
        await tester.tap(
          find.descendant(
            of: find.byType(ChatDrawer),
            matching: find.byWidgetPredicate(
              (w) => w is CircleIconButton && w.semanticLabel == 'محادثة جديدة',
            ),
          ),
        );
        await tester.pump(const Duration(milliseconds: 400));
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/drawer_create_menu_dark_ar.png'),
        );
      });
    });
  });

  group('list home', () {
    testWidgets('the list is the root; a chat is pushed over it with back', (
      tester,
    ) async {
      final (_, router) = await _pump(
        tester,
        state: _state(mode: HomeMode.list),
      );
      expect(find.byType(ChatsScreen), findsOneWidget);
      expect(find.byType(MenuPillButton), findsNothing);
      expect(find.byType(ChatDrawerScope), findsNothing);
      await tester.tap(find.widgetWithText(ChatListRow, 'Gold desk'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));
      expect(_home(tester).threadId, 't-gold');
      expect(_home(tester).home, isFalse);
      expect(
        router.routerDelegate.currentConfiguration.last.matchedLocation,
        Routes.thread('t-gold'),
      );
      expect(router.canPop(), isTrue);
      expect(
        find.byWidgetPredicate(
          (w) => w is CircleIconButton && w.semanticLabel == 'Back',
        ),
        findsOneWidget,
      );
    });

    testWidgets('home links and the full list fall back to the list home', (
      tester,
    ) async {
      final (_, router) = await _pump(
        tester,
        state: _state(mode: HomeMode.list),
      );
      router.go(Routes.home('t-news'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));
      expect(
        router.routerDelegate.currentConfiguration.uri.toString(),
        Routes.thread('t-news'),
      );
      router.go(Routes.chatList());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));
      expect(
        router.routerDelegate.currentConfiguration.uri.toString(),
        Routes.chats,
      );
    });
  });

  test('homeRedirect keeps each home\'s shape', () {
    Uri u(String s) => Uri.parse(s);
    expect(
      homeRedirect(HomeMode.lastChat, u('/chats/thread/t1?around=4')),
      '/chats?thread=t1&around=4',
    );
    expect(homeRedirect(HomeMode.lastChat, u('/chats?thread=t1')), isNull);
    expect(homeRedirect(HomeMode.lastChat, u('/chats/archived')), isNull);
    expect(homeRedirect(HomeMode.lastChat, u('/chats/all')), isNull);
    expect(
      homeRedirect(HomeMode.list, u('/chats?thread=t1')),
      '/chats/thread/t1',
    );
    expect(homeRedirect(HomeMode.list, u('/chats/all')), '/chats');
    expect(homeRedirect(HomeMode.list, u('/chats/thread/t1')), isNull);
    expect(Routes.chatList(select: 'agent:a1'), '/chats/all?select=agent%3Aa1');
  });
}
