// Me tab: entries, navigation, sign-out and clear-cache confirmations, usage card, goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/me
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/rendering.dart' show SemanticsAction;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FIcons, FTile;
import 'package:go_router/go_router.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/me/me_screen.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart';
import '../settings_core/feature_harness.dart';

/// Me inside the floating tab bar, as the home shell shows it.
class _MeInShell extends StatelessWidget {
  const _MeInShell();

  @override
  Widget build(BuildContext context) => Stack(
    children: [
      const Positioned.fill(child: MeScreen()),
      const Positioned(
        left: 0,
        right: 0,
        bottom: 0,
        child: IgnorePointer(child: BottomChromeFade()),
      ),
      Positioned(
        left: 0,
        right: 0,
        bottom: 0,
        child: FloatingTabBar(
          items: const [
            LnTabItem(
              icon: LnGlyph(LnGlyphs.chats),
              selectedIcon: LnGlyph(LnGlyphs.chatsFilled),
              label: 'Chats',
            ),
            LnTabItem(
              icon: LnGlyph(LnGlyphs.market),
              selectedIcon: LnGlyph(LnGlyphs.marketFilled),
              label: 'Market',
            ),
            LnTabItem(
              icon: LnGlyph(LnGlyphs.me),
              selectedIcon: LnGlyph(LnGlyphs.meFilled),
              label: 'Me',
            ),
          ],
          selectedIndex: 2,
          onSelect: (_) {},
          actionIcon: const LnGlyph(LnGlyphs.attention),
          actionLabel: 'Attention',
          onAction: () {},
        ),
      ),
    ],
  );
}

void main() {
  setUpAll(setUpFeatureTests);

  late GoRouter router;

  Future<(ScriptedApi, Store<AppState>)> pumpMe(
    WidgetTester tester, {
    String locale = 'ar',
    AppThemeMode theme = AppThemeMode.light,
    bool usageFails = false,
    List<OutgoingMessage> outbox = const [],
  }) async {
    final api = await setUpServices();
    api.on(
      'GET /owner/profile',
      (_) => profileJson(name: 'Ahmed', address: 'أبو خالد'),
    );
    api.on(
      'GET /usage/summary',
      (_) => usageFails
          ? throw ApiError.network()
          : {
              'input_tokens': 1284330,
              'output_tokens': 220415,
              'cached_tokens': 905112,
            },
    );
    final store = testStore(locale: locale, theme: theme, outbox: outbox);
    setFeatureViewport(tester);
    router = testRouter(const _MeInShell());
    await tester.pumpWidget(featureApp(store, router));
    await tester.pumpAndSettle();
    return (api, store);
  }

  testWidgets('shows the owner, every Lonora entry and the usage totals', (
    tester,
  ) async {
    await pumpMe(tester, locale: 'en');
    expect(find.text('أبو خالد'), findsOneWidget);
    for (final title in [
      'Agents',
      'Routines',
      'Tasks',
      'Files',
      'Charts',
      'What I know about you',
      'Integrations',
      'Global model routing',
      'What is running',
      'Notifications and contact',
      'Voice',
      'Language',
      'Appearance',
      'Clear cache',
      'About Lonora',
    ]) {
      await scrollTo(tester, find.text(title));
      expect(find.text(title), findsOneWidget, reason: title);
    }
    await scrollTo(tester, find.text('1,284,330'));
    expect(find.text('220,415'), findsOneWidget);
    expect(find.text('905,112'), findsOneWidget);
  });

  testWidgets('entries open their pages', (tester) async {
    await pumpMe(tester, locale: 'en');
    await tester.tap(find.text('Agents'));
    await tester.pumpAndSettle();
    expect(find.text('stub:/agents'), findsOneWidget);
    router.pop();
    await tester.pumpAndSettle();
    await tester.tap(find.text('أبو خالد'));
    await tester.pumpAndSettle();
    expect(find.text('stub:/settings/account'), findsOneWidget);
  });

  testWidgets('the owner card says that it opens the account', (tester) async {
    final semantics = tester.ensureSemantics();
    await pumpMe(tester, locale: 'en');
    // One merged node: what the card is, what a tap does, and the tap itself.
    final data = tester.getSemantics(find.text('أبو خالد')).getSemanticsData();
    expect(data.label, contains('owner@example.com'));
    expect(data.hint, 'Open the account');
    expect(data.hasAction(SemanticsAction.tap), isTrue);
    semantics.dispose();
  });

  for (final theme in [AppThemeMode.light, AppThemeMode.dark]) {
    testWidgets('the owner card is a full touch target; its initial is '
        'on-accent ink (${theme.name})', (tester) async {
      await pumpMe(tester, locale: 'en', theme: theme);
      final card = find.ancestor(
        of: find.text('أبو خالد'),
        matching: find.byType(FTile),
      );
      expect(
        tester.getSize(card).height,
        greaterThanOrEqualTo(LnSize.minTouch),
      );
      final initial = tester.widget<Text>(
        find.descendant(
          of: find.byType(OwnerInitialAvatar),
          matching: find.byType(Text),
        ),
      );
      final palette = theme == AppThemeMode.dark
          ? LnPalette.dark
          : LnPalette.light;
      expect(initial.style?.color, palette.onAccent);
    });
  }

  testWidgets('the notifications row shows how Lonora reaches the owner', (
    tester,
  ) async {
    await pumpMe(tester, locale: 'en');
    await scrollTo(tester, find.text('Notifications and contact'));
    // profileJson's channel is `message`.
    expect(find.text('Message me'), findsOneWidget);
  });

  testWidgets('chat experience opens the conversation preferences', (
    tester,
  ) async {
    await pumpMe(tester, locale: 'en');
    await scrollTo(tester, find.text('Chat experience'));
    await tapAndSettle(tester, find.text('Chat experience'));
    expect(find.text('Chat experience'), findsNWidgets(2));
    expect(find.byType(LnSwitch), findsNWidgets(4));
  });

  testWidgets('back from the account page, the card reads the profile again', (
    tester,
  ) async {
    final (api, _) = await pumpMe(tester, locale: 'en');
    expect(api.callsTo('GET', '/owner/profile'), hasLength(1));
    api.on(
      'GET /owner/profile',
      (_) => profileJson(name: 'Ahmed', address: 'Abu Khalid'),
    );
    await tester.tap(find.text('أبو خالد'));
    await tester.pumpAndSettle();
    router.pop();
    await tester.pumpAndSettle();
    expect(api.callsTo('GET', '/owner/profile'), hasLength(2));
    expect(find.text('Abu Khalid'), findsOneWidget);
    expect(find.text('أبو خالد'), findsNothing);
  });

  testWidgets('sign-out cannot run twice while the server is slow', (
    tester,
  ) async {
    final (api, store) = await pumpMe(tester, locale: 'en');
    final logout = Completer<Object?>();
    api.on('POST /auth/logout', (_) => logout.future);
    await scrollTo(tester, find.text('Sign out'));
    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign out').last);
    // The confirmation closes; the server has not answered yet (8 s at most).
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Sign out?'), findsNothing);
    expect(store.state.session.signedIn, isTrue);
    // A second tap opens no second confirmation.
    await tester.tap(find.text('Sign out'), warnIfMissed: false);
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Sign out?'), findsNothing);
    logout.complete({'logged_out': true});
    await tester.pumpAndSettle();
    expect(api.callsTo('POST', '/auth/logout'), hasLength(1));
    expect(store.state.session.status, SessionStatus.signedOut);
  });

  testWidgets('sign out asks first, then revokes the session', (tester) async {
    final (api, store) = await pumpMe(tester, locale: 'en');
    await scrollTo(tester, find.text('Sign out'));
    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    expect(find.text('Sign out?'), findsOneWidget);
    // Cancel keeps the session.
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(store.state.session.signedIn, isTrue);
    expect(api.callsTo('POST', '/auth/logout'), isEmpty);

    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign out').last);
    await tester.pumpAndSettle();
    expect(api.callsTo('POST', '/auth/logout'), hasLength(1));
    expect(store.state.session.status, SessionStatus.signedOut);
  });

  testWidgets('clear cache asks first and keeps the outbox', (tester) async {
    final pending = OutgoingMessage(
      nonce: 'n1',
      threadId: 'thread-1',
      body: const {'content': 'not sent yet', 'client_nonce': 'n1'},
      delivery: Delivery.queued,
      createdAt: DateTime.utc(2026, 11, 27),
    );
    final (_, store) = await pumpMe(tester, locale: 'en', outbox: [pending]);
    final scope = LocalStore.scope(testServer, testOwner.id);
    testLocalStore.docs['$scope/shell'] = {'cached': true};
    testLocalStore.docs['$scope/outbox'] = [pending.toJson()];
    // A listed conversation and one no longer listed (archived, deleted): both go.
    testLocalStore.docs['$scope/thread_thread-1'] = {'cached': true};
    testLocalStore.docs['$scope/thread_gone'] = {'cached': true};
    expect(store.state.session.signedIn, isTrue);
    await scrollTo(tester, find.text('Clear cache'));
    await tester.tap(find.text('Clear cache'));
    await tester.pumpAndSettle();
    expect(find.text('Clear the cache?'), findsOneWidget);
    await tester.tap(find.text('Clear'));
    await tester.pumpAndSettle();
    expect(find.text('Cache cleared'), findsOneWidget);
    expect(testLocalStore.docs.containsKey('$scope/shell'), isFalse);
    expect(testLocalStore.docs.containsKey('$scope/thread_thread-1'), isFalse);
    expect(testLocalStore.docs.containsKey('$scope/thread_gone'), isFalse);
    expect(testLocalStore.docs['$scope/outbox'], [pending.toJson()]);
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  });

  testWidgets('usage failure offers a retry', (tester) async {
    final (api, _) = await pumpMe(tester, locale: 'en', usageFails: true);
    await scrollTo(tester, find.textContaining('Could not connect'));
    expect(find.textContaining('Could not connect'), findsOneWidget);
    expect(api.callsTo('GET', '/usage/summary'), hasLength(1));
    api.on(
      'GET /usage/summary',
      (_) => {'input_tokens': 10, 'output_tokens': 20, 'cached_tokens': 30},
    );
    await tapAndSettle(tester, find.textContaining('Could not connect'));
    expect(api.callsTo('GET', '/usage/summary'), hasLength(2));
    expect(find.textContaining('Could not connect'), findsNothing);
    expect(find.text('10'), findsOneWidget);
    expect(find.text('30'), findsOneWidget);
  });

  testWidgets('ms:C7 / ms:C8 the tasks and sign-out icons mirror in Arabic', (
    tester,
  ) async {
    await pumpMe(tester);
    for (final icon in [LnIcons.listChecks, LnIcons.logOut]) {
      await scrollTo(tester, find.byIcon(icon));
      expect(icon.matchTextDirection, isTrue);
      expect(
        Directionality.of(tester.element(find.byIcon(icon))),
        TextDirection.rtl,
      );
    }
    expect(find.byIcon(FIcons.listChecks), findsNothing);
    expect(find.byIcon(FIcons.logOut), findsNothing);
  });

  testWidgets('ms:C6 the usage card sits on the list rows\' grid', (
    tester,
  ) async {
    await pumpMe(tester);
    await scrollTo(tester, find.byIcon(FIcons.chartColumn));
    Finder inRow(Finder of, IconData icon) => find.descendant(
      of: find.ancestor(of: of, matching: find.byType(Row)).first,
      matching: find.byIcon(icon),
    );
    final card = find.byIcon(FIcons.chartColumn);
    final cardChevron = inRow(card, FIcons.chevronRight);
    // The row just above the card: «About Lonora».
    final row = find.ancestor(
      of: find.byIcon(FIcons.info),
      matching: find.byType(FTile),
    );
    final rowIcon = find.byIcon(FIcons.info);
    final rowChevron = find.descendant(
      of: row,
      matching: find.byIcon(FIcons.chevronRight),
    );
    expect(tester.getRect(card).right, tester.getRect(rowIcon).right);
    expect(tester.getSize(card), tester.getSize(rowIcon));
    expect(tester.getRect(cardChevron).left, tester.getRect(rowChevron).left);
    expect(
      IconTheme.of(tester.element(card)).color,
      IconTheme.of(tester.element(rowIcon)).color,
    );
  });

  testWidgets('text at 1.3× lays out without overflow', (tester) async {
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await pumpMe(tester);
    await tester.drag(find.byType(MeScreen), const Offset(0, -2000));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      await withRealShadows(() async {
        await pumpMe(tester, locale: v.locale, theme: v.theme);
        await expectLater(
          find.byType(MaterialAppProbe.type),
          matchesGoldenFile('goldens/me_${v.name}.png'),
        );
      });
    });
  }

  testWidgets('golden light_ar bottom', (tester) async {
    await withRealShadows(() async {
      await pumpMe(tester);
      await tester.drag(find.byType(MeScreen), const Offset(0, -2000));
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialAppProbe.type),
        matchesGoldenFile('goldens/me_light_ar_bottom.png'),
      );
    });
  });
}

/// The root to capture: the whole app surface.
abstract final class MaterialAppProbe {
  static const type = WidgetsApp;
}
