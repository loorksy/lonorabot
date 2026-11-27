// The share target picker: shown for a pending share, filtered by search, a pick opens the
// conversation and leaves the payload for the composer, a dismissal drops it.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/deep_links.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/chats/chat_widgets.dart';
import 'package:lonora/features/share/share_picker.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart' show withRealShadows;
import '../chats/harness.dart';

Future<void> pumpWithListener(
  WidgetTester tester, {
  String locale = 'en',
  Brightness brightness = Brightness.light,
}) async {
  setGoldenViewport(tester);
  final store = Store<AppState>(initialState: fixtureState(working: false));
  final navigator = GlobalKey<NavigatorState>();
  await tester.pumpWidget(
    featureApp(
      store: store,
      router: testRouter(Routes.chats, navigatorKey: navigator),
      brightness: brightness,
      locale: locale,
      // Mounted as the app would: in MaterialApp.router's builder, above the navigator.
      wrap: (app) => ShareListener(navigatorKey: navigator, child: app),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(setUpFeatureHarness);
  setUp(() {
    resetFakeApi();
    pendingShare.value = null;
  });

  testWidgets('a pick addresses the payload and opens the conversation', (
    tester,
  ) async {
    await pumpWithListener(tester);
    final payload = const SharedPayload(text: 'Look at this chart');
    pendingShare.value = payload;
    await tester.pumpAndSettle();
    expect(find.text('Send to…'), findsOneWidget);
    expect(find.text('Look at this chart'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'gold');
    await tester.pump();
    expect(
      find.descendant(
        of: find.byType(ShareTargetPicker),
        matching: find.text('Morning news'),
      ),
      findsNothing,
    );
    await tester.tap(
      find.descendant(
        of: find.byType(ShareTargetPicker),
        matching: find.text('Gold desk'),
      ),
    );
    await tester.pumpAndSettle();
    expect(shownRoute(tester), '/chats/thread/t-gold');
    expect(pendingShare.value?.text, payload.text);
    expect(pendingShare.value?.targetThreadId, 't-gold');
    expect(find.text('Send to…'), findsNothing);
  });

  testWidgets('shared files are listed with the language\'s separator', (
    tester,
  ) async {
    const files = SharedPayload(
      files: [
        SharedFile(path: '/tmp/a.pdf', name: 'a.pdf'),
        SharedFile(path: '/tmp/b.png', name: 'b.png'),
      ],
    );
    // cc:C1: the English comma in English, the Arabic one in Arabic.
    for (final (locale, summary) in [
      ('en', 'a.pdf, b.png'),
      ('ar', 'a.pdf، b.png'),
    ]) {
      pendingShare.value = null;
      await pumpWithListener(tester, locale: locale);
      pendingShare.value = files;
      await tester.pumpAndSettle();
      expect(find.text(summary), findsOneWidget);
      await tester.tapAt(const Offset(200, 60));
      await tester.pumpAndSettle();
    }
  });

  testWidgets('the rows share the sheet\'s edge with the search field', (
    tester,
  ) async {
    // cc:C8: one start edge for the field and the avatars, left in English, right in Arabic.
    for (final locale in ['en', 'ar']) {
      pendingShare.value = null;
      await pumpWithListener(tester, locale: locale);
      pendingShare.value = const SharedPayload(text: 'hello');
      await tester.pumpAndSettle();
      final picker = find.byType(ShareTargetPicker);
      final field = tester.getRect(
        find.descendant(of: picker, matching: find.byType(SearchPill)),
      );
      final avatar = tester.getRect(
        find.descendant(of: picker, matching: find.byType(ChatRowAvatar)).first,
      );
      if (locale == 'ar') {
        expect(avatar.right, field.right);
      } else {
        expect(avatar.left, field.left);
      }
      await tester.tapAt(const Offset(200, 60));
      await tester.pumpAndSettle();
    }
  });

  testWidgets('the loading rows start at the field\'s edge too', (
    tester,
  ) async {
    setGoldenViewport(tester);
    final navigator = GlobalKey<NavigatorState>();
    await tester.pumpWidget(
      featureApp(
        store: Store<AppState>(
          initialState: fixtureState(
            loaded: false,
            agents: [],
            groups: [],
            inbox: [],
          ),
        ),
        router: testRouter(Routes.chats, navigatorKey: navigator),
        locale: 'en',
        wrap: (app) => ShareListener(navigatorKey: navigator, child: app),
      ),
    );
    // Skeletons shimmer: pump through the sheet's entrance instead of settling.
    await tester.pump();
    pendingShare.value = const SharedPayload(text: 'hello');
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    final picker = find.byType(ShareTargetPicker);
    final field = tester.getRect(
      find.descendant(of: picker, matching: find.byType(SearchPill)),
    );
    final skeleton = find.descendant(
      of: picker,
      matching: find.byType(SkeletonRows),
    );
    expect(skeleton, findsOneWidget);
    // The first placeholder is the first row's avatar square.
    final avatar = tester.getRect(
      find.descendant(of: skeleton, matching: find.byType(Container)).first,
    );
    expect(avatar.left, field.left);
  });

  testWidgets('dismissing the picker drops the share', (tester) async {
    await pumpWithListener(tester);
    pendingShare.value = const SharedPayload(text: 'hello');
    await tester.pumpAndSettle();
    expect(find.text('Send to…'), findsOneWidget);
    await tester.tapAt(const Offset(200, 60));
    await tester.pumpAndSettle();
    expect(pendingShare.value, isNull);
    expect(find.text('Send to…'), findsNothing);
  });

  testWidgets('a failed first load offers a retry', (tester) async {
    setGoldenViewport(tester);
    final navigator = GlobalKey<NavigatorState>();
    await tester.pumpWidget(
      featureApp(
        store: Store<AppState>(
          initialState: fixtureState(
            loaded: false,
            agents: [],
            groups: [],
            inbox: [],
            lastError: 'network',
          ),
        ),
        router: testRouter(Routes.chats, navigatorKey: navigator),
        locale: 'en',
        wrap: (app) => ShareListener(navigatorKey: navigator, child: app),
      ),
    );
    await tester.pumpAndSettle();
    pendingShare.value = const SharedPayload(text: 'hello');
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(
      find.descendant(
        of: find.byType(ShareTargetPicker),
        matching: find.byType(ErrorState),
      ),
      findsOneWidget,
    );
  });

  testWidgets('golden: share picker light ar', (tester) async {
    await withRealShadows(() async {
      await pumpWithListener(tester, locale: 'ar');
      pendingShare.value = const SharedPayload(text: 'شارت الذهب اليوم');
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/share_picker_light_ar.png'),
      );
    });
  });
}
