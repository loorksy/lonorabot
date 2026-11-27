// The archived page: the archived rows, unarchiving from the row menu, the keep-archived
// setting, and the empty state.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderParagraph;
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart' show withRealShadows;
import 'harness.dart';

Future<Store<AppState>> pumpArchived(
  WidgetTester tester, {
  AppState? state,
  String locale = 'en',
}) async {
  setGoldenViewport(tester);
  final store = Store<AppState>(initialState: state ?? fixtureState());
  await tester.pumpWidget(
    featureApp(
      store: store,
      router: testRouter(Routes.archived),
      locale: locale,
    ),
  );
  await tester.pumpAndSettle();
  return store;
}

void main() {
  setUpAll(setUpFeatureHarness);
  setUp(resetFakeApi);

  testWidgets('shows the archived chats only and unarchives from the menu', (
    tester,
  ) async {
    fakeApi.handlers['POST /threads/prefs'] = (_, _) => [
      {'thread_id': 't-old', 'archived': false},
    ];
    final store = await pumpArchived(tester);
    expect(find.byType(ChatListRow), findsOneWidget);
    expect(find.text('Old helper'), findsOneWidget);
    await tester.longPress(find.text('Old helper'));
    await tester.pumpAndSettle();
    expect(
      find.text('Pin'),
      findsNothing,
      reason: 'an archived chat is not pinned',
    );
    await tester.tap(find.text('Unarchive'));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('POST', '/threads/prefs').single.body, {
      'thread_ids': ['t-old'],
      'archived': false,
    });
    expect(store.state.shell.entryFor('t-old')!.archived, isFalse);
    expect(find.byType(ChatListRow), findsNothing);
    expect(find.text('Chat returned to the list'), findsOneWidget);
    await settleToasts(tester);
  });

  testWidgets('the keep-archived switch saves the setting', (tester) async {
    fakeApi.handlers['PUT /threads/settings'] = (body, _) => body;
    final store = await pumpArchived(tester);
    expect(find.text('Keep chats archived'), findsOneWidget);
    await tester.tap(find.byType(LnSwitch));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('PUT', '/threads/settings').single.body, {
      'keep_archived': false,
    });
    expect(store.state.shell.keepArchived, isFalse);
    await settleToasts(tester);
  });

  testWidgets('the keep-archived explanation is read in full', (tester) async {
    await pumpArchived(tester);
    final subtitle = find.descendant(
      of: find.text(
        'A chat does not return to the list when a new message arrives.',
      ),
      matching: find.byType(RichText),
    );
    final paragraph = tester.renderObject<RenderParagraph>(subtitle);
    // cc:C4: the subtitle wraps instead of stopping at one line.
    expect(paragraph.didExceedMaxLines, isFalse);
    expect(
      tester.getSize(subtitle).height,
      greaterThan(paragraph.preferredLineHeight * 1.5),
    );
  });

  testWidgets('the last item clears the floating tab bar', (tester) async {
    final extra = [
      for (var i = 0; i < 10; i++) agentJson('a-x$i', 'Archived $i'),
    ];
    final state = fixtureState(
      agents: [...fixtureAgents, ...extra],
      inbox: [
        ...fixtureInbox(),
        for (var i = 0; i < 10; i++)
          inboxJson(
            't-x$i',
            agentId: 'a-x$i',
            content: 'Old note $i',
            at: DateTime(2026, 10, 1 + i),
            archived: true,
          ),
      ],
    );
    await pumpArchived(tester, state: state);
    await tester.drag(find.byType(ListView), const Offset(0, -3000));
    await tester.pumpAndSettle();
    final context = tester.element(find.byType(LnSwitch));
    final bar = FloatingTabBar.occupiedHeight(context);
    final screen =
        tester.view.physicalSize.height / tester.view.devicePixelRatio;
    expect(
      tester.getBottomLeft(find.byType(LnSwitch)).dy,
      lessThan(screen - bar),
    );
  });

  testWidgets('a failed first load offers a retry', (tester) async {
    fakeApi.handlers['GET /agents'] = (_, _) => fixtureAgents;
    await pumpArchived(
      tester,
      state: fixtureState(
        loaded: false,
        agents: [],
        groups: [],
        inbox: [],
        lastError: 'network',
      ),
    );
    expect(find.byType(ErrorState), findsOneWidget);
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('GET', '/agents'), hasLength(1));
  });

  testWidgets('golden: archived light ar', (tester) async {
    await withRealShadows(() async {
      await pumpArchived(tester, locale: 'ar');
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/archived_light_ar.png'),
      );
    });
  });
}
