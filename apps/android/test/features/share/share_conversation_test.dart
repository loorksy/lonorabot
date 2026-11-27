// The share hand-off with the real conversation screen: a share arriving while a conversation
// stays alive in the chats tab (indexedStack) goes through the picker, and only the picked
// conversation's composer takes it. Kept apart from share_picker_test.dart: it compiles the
// conversation feature.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/app/deep_links.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/features/conversation/conversation_screen.dart';
import 'package:lonora/features/share/share_picker.dart';
import 'package:lonora/state/app_state.dart';

import '../chats/harness.dart';

final _root = GlobalKey<NavigatorState>();

/// The app's shape: the chats tab keeps its pages alive while another tab shows.
GoRouter _router() => GoRouter(
  navigatorKey: _root,
  initialLocation: Routes.chats,
  routes: [
    StatefulShellRoute.indexedStack(
      builder: (_, _, shell) => shell,
      branches: [
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: Routes.chats,
              builder: (_, _) => const Center(child: Text('chats')),
              routes: [
                GoRoute(
                  path: 'thread/:id',
                  builder: (_, s) =>
                      ConversationScreen(threadId: s.pathParameters['id']!),
                ),
              ],
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: Routes.me,
              builder: (_, _) => const Center(child: Text('me')),
            ),
          ],
        ),
      ],
    ),
  ],
);

String _composerText(WidgetTester tester, String threadId) {
  final screen = find.byWidgetPredicate(
    (w) => w is ConversationScreen && w.threadId == threadId,
    skipOffstage: false,
  );
  final field = find.descendant(
    of: screen,
    matching: find.byType(EditableText, skipOffstage: false),
    skipOffstage: false,
  );
  return tester.widget<EditableText>(field.first).controller.text;
}

void main() {
  setUpAll(setUpFeatureHarness);
  setUp(() {
    resetFakeApi();
    pendingShare.value = null;
  });

  testWidgets('a share goes to the picked conversation, not the open one', (
    tester,
  ) async {
    for (final (thread, agent) in [
      ('t-news', 'a-news'),
      ('t-gold', 'a-gold'),
    ]) {
      fakeApi.handlers['GET /threads/$thread'] = (_, _) => {
        'id': thread,
        'agent_id': agent,
        'title': '',
      };
      fakeApi.handlers['GET /threads/$thread/messages'] = (_, _) => <Object>[];
    }
    setGoldenViewport(tester);
    final router = _router();
    await tester.pumpWidget(
      featureApp(
        store: Store<AppState>(initialState: fixtureState(working: false)),
        router: router,
        locale: 'en',
        wrap: (app) => ShareListener(navigatorKey: _root, child: app),
      ),
    );
    await tester.pumpAndSettle();
    // A conversation was open, then another tab: it stays alive offstage.
    router.go(Routes.thread('t-news'));
    await tester.pumpAndSettle();
    router.go(Routes.me);
    await tester.pumpAndSettle();
    expect(
      find.byType(ConversationScreen, skipOffstage: false),
      findsOneWidget,
    );

    // What DeepLinks does with a share: the payload, then the chats list.
    const payload = SharedPayload(text: 'Look at this chart');
    pendingShare.value = payload;
    expect(_composerText(tester, 't-news'), isEmpty);
    router.go(Routes.chats);
    await tester.pumpAndSettle();
    expect(find.text('Send to…'), findsOneWidget);
    expect(pendingShare.value, same(payload));

    await tester.tap(
      find.descendant(
        of: find.byType(ShareTargetPicker),
        matching: find.text('Gold desk'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Send to…'), findsNothing);
    expect(_composerText(tester, 't-gold'), 'Look at this chart');
    expect(pendingShare.value, isNull);
    // Nothing was sent: the owner sends it.
    expect(
      fakeApi.calls.where(
        (c) => c.method == 'POST' && c.path.contains('/messages'),
      ),
      isEmpty,
    );
    await tester.pump(const Duration(seconds: 5));
  });
}
