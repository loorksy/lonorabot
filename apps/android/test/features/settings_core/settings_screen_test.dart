// The Settings page pushed from Me: its three groups, the rows that moved from Me, the in-place
// pickers (home screen, appearance), and goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/settings_core
import 'dart:ui' show Tristate;

import 'package:async_redux/async_redux.dart';
import 'package:flutter/rendering.dart' show SemanticsAction;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FIcons, FTile, FTileGroup;
import 'package:go_router/go_router.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/l10n/l10n.dart' show ltr;
import 'package:lonora/features/settings/about_screen.dart';
import 'package:lonora/features/settings/account_screen.dart';
import 'package:lonora/features/settings/appearance_screen.dart';
import 'package:lonora/features/settings/notifications_screen.dart';
import 'package:lonora/features/settings/settings_screen.dart';
import 'package:lonora/features/settings/voice_settings_screen.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart';
import 'feature_harness.dart';

void main() {
  setUpAll(setUpFeatureTests);

  Future<(ScriptedApi, Store<AppState>)> pumpSettings(
    WidgetTester tester, {
    String locale = 'en',
    AppThemeMode theme = AppThemeMode.light,
    List<OutgoingMessage> outbox = const [],
  }) async {
    final api = await setUpServices(prefs: {'lonora.locale': locale});
    api.on('GET /owner/profile', (_) => profileJson(name: 'Ahmed'));
    final store = testStore(locale: locale, theme: theme, outbox: outbox);
    setFeatureViewport(tester);
    await tester.pumpWidget(
      featureApp(store, testRouter(const SettingsScreen())),
    );
    await tester.pumpAndSettle();
    return (api, store);
  }

  /// The texts of the rows of the [index]th tile group, top to bottom.
  List<String> groupRows(WidgetTester tester, int index) {
    final group = find.byType(FTileGroup).at(index);
    return [
      for (final tile in tester.widgetList<FTile>(
        find.descendant(of: group, matching: find.byType(FTile)),
      ))
        tester
            .widgetList<Text>(
              find.descendant(
                of: find.byWidget(tile),
                matching: find.byType(Text),
              ),
            )
            .first
            .data!,
    ];
  }

  testWidgets('notifications on a card of its own, then the phone\'s '
      'preferences, «Outage and recovery», then About and the version; groups '
      '32 dp apart', (tester) async {
    await pumpSettings(tester);
    expect(find.byType(FTileGroup), findsNWidgets(4));
    expect(groupRows(tester, 0), ['Notifications and contact']);
    expect(groupRows(tester, 1), [
      'Home screen',
      'Language',
      'Appearance',
      'Chat experience',
      'Voice',
      'Clear cache',
    ]);
    expect(groupRows(tester, 2), ['Outage and recovery']);
    expect(groupRows(tester, 3), ['About Lonora', 'App version']);
    final cards = [
      for (var i = 0; i < 4; i++) tester.getRect(find.byType(FTileGroup).at(i)),
    ];
    for (var i = 1; i < 4; i++) {
      expect(cards[i].top - cards[i - 1].bottom, LnSpace.xxl);
    }
  });

  testWidgets('«Outage and recovery» opens its page', (tester) async {
    await pumpSettings(tester);
    await scrollTo(tester, find.text('Outage and recovery'));
    await tapAndSettle(tester, find.text('Outage and recovery'));
    expect(find.text('stub:/settings/recovery'), findsOneWidget);
  });

  testWidgets('the page title is 16/24 in the ink, centred', (tester) async {
    await pumpSettings(tester);
    final title = tester.widget<Text>(find.text('Settings'));
    expect(title.style?.fontSize, 16);
    expect(title.style?.height, 24 / 16);
    expect(title.style?.color, LnPalette.light.fg);
    expect(tester.getCenter(find.text('Settings')).dx, 393 / 2);
  });

  testWidgets('how Lonora reaches the owner: the value in Arabic, a second '
      'line in English', (tester) async {
    await pumpSettings(tester, locale: 'ar');
    // profileJson's channel is `message`.
    final ar = find.text('راسلني');
    expect(ar, findsOneWidget);
    expect(
      tester.getCenter(ar).dy,
      moreOrLessEquals(
        tester.getCenter(find.text('الإشعارات والتواصل')).dy,
        epsilon: 1,
      ),
    );
    await pumpSettings(tester);
    final en = find.text('Message me');
    expect(en, findsOneWidget);
    expect(
      tester.getTopLeft(en).dy,
      greaterThan(
        tester.getBottomLeft(find.text('Notifications and contact')).dy,
      ),
    );
  });

  testWidgets('rows open their pages', (tester) async {
    await pumpSettings(tester);
    for (final (title, route) in [
      ('Notifications and contact', '/settings/notifications'),
      ('Voice', '/settings/voice'),
      ('About Lonora', '/settings/about'),
    ]) {
      await tapAndSettle(tester, find.text(title));
      expect(find.text('stub:$route'), findsOneWidget, reason: title);
      GoRouter.of(tester.element(find.text('stub:$route'))).pop();
      await tester.pumpAndSettle();
    }
  });

  testWidgets('back from Notifications, the row reads how Lonora reaches the '
      'owner again', (tester) async {
    final (api, _) = await pumpSettings(tester);
    expect(api.callsTo('GET', '/owner/profile'), hasLength(1));
    expect(find.text('Message me'), findsOneWidget);
    // Changed on the Notifications page.
    api.on('GET /owner/profile', (_) => profileJson(channel: 'call'));
    await tapAndSettle(tester, find.text('Notifications and contact'));
    expect(find.text('stub:/settings/notifications'), findsOneWidget);
    GoRouter.of(tester.element(find.text('stub:/settings/notifications')))
        .pop();
    await tester.pumpAndSettle();
    expect(api.callsTo('GET', '/owner/profile'), hasLength(2));
    expect(find.text('Call me'), findsOneWidget);
    expect(find.text('Message me'), findsNothing);
  });

  testWidgets('the language sheet says what «Follow system» means; a choice '
      'applies at once and the row shows it', (tester) async {
    final (_, store) = await pumpSettings(tester);
    expect(find.text('English'), findsOneWidget);
    await tapAndSettle(tester, find.text('Language'));
    final sheet = find.ancestor(
      of: find.text('Follow system'),
      matching: find.byType(FTileGroup),
    );
    expect(groupRows(tester, 4), ['Follow system', 'العربية', 'English']);
    expect(
      find.descendant(
        of: sheet,
        matching: find.text(
          '“Follow system” uses Arabic unless the phone is set to English.',
        ),
      ),
      findsOneWidget,
    );
    await tapAndSettle(
      tester,
      find.descendant(of: sheet, matching: find.text('العربية')),
    );
    expect(store.state.prefs.locale, 'ar');
    expect(devicePrefs.getString('lonora.locale'), 'ar');
    expect(find.byType(FTileGroup), findsNWidgets(4));
    expect(find.text('اللغة'), findsOneWidget);
    expect(find.text('العربية'), findsOneWidget);

    // «حسب النظام» forgets the choice; the test phone is in English.
    await tapAndSettle(tester, find.text('اللغة'));
    await tapAndSettle(tester, find.text('حسب النظام'));
    expect(devicePrefs.getString('lonora.locale'), isNull);
    expect(store.state.prefs.locale, 'en');
    expect(find.byType(FTileGroup), findsNWidgets(4));
    expect(find.text('Language'), findsOneWidget);
    expect(find.text('Follow system'), findsOneWidget);
  });

  group('opened from a link, back goes to the page its row lives on', () {
    for (final (route, page, back) in [
      (Routes.notifications, const NotificationsScreen(), Routes.settings),
      (Routes.voice, const VoiceSettingsScreen(), Routes.settings),
      (Routes.appearance, const AppearanceScreen(), Routes.settings),
      (Routes.about, const AboutScreen(), Routes.settings),
      (Routes.account, const AccountScreen(), Routes.me),
    ]) {
      testWidgets(route, (tester) async {
        final api = await setUpServices();
        api.on('GET /owner/profile', (_) => profileJson(name: 'Ahmed'));
        api.on('GET /version', (_) => {'version': '0.2.0', 'build': '1a2b3c'});
        final store = testStore(locale: 'en');
        setFeatureViewport(tester);
        await tester.pumpWidget(
          featureApp(
            store,
            testRouter(
              const SizedBox.shrink(),
              pages: {route: (_) => page},
              initialLocation: route,
            ),
          ),
        );
        await tester.pumpAndSettle();
        await tapAndSettle(tester, find.bySemanticsLabel('Back'));
        expect(find.text('stub:$back'), findsOneWidget);
      });
    }
  });

  testWidgets('the version is a Latin value with no chevron and no action, '
      'in Arabic too', (tester) async {
    final semantics = tester.ensureSemantics();
    await pumpSettings(tester, locale: 'ar');
    expect(find.text(ltr('1.0.0')), findsOneWidget);
    final row = find.ancestor(
      of: find.text('إصدار التطبيق'),
      matching: find.byType(FTile),
    );
    expect(
      find.descendant(of: row, matching: find.byIcon(FIcons.chevronRight)),
      findsNothing,
    );
    final data = tester
        .getSemantics(find.text('إصدار التطبيق'))
        .getSemanticsData();
    expect(data.hasAction(SemanticsAction.tap), isFalse);
    semantics.dispose();
  });

  for (final locale in ['en', 'ar']) {
    testWidgets('the home screen is picked in place: ⇕ on the row, a menu at '
        'its end edge with a check on the current choice ($locale)', (
      tester,
    ) async {
      final (_, store) = await pumpSettings(tester, locale: locale);
      final en = locale == 'en';
      final title = en ? 'Home screen' : 'الشاشة الرئيسية';
      final last = en ? 'Last conversation' : 'آخر محادثة';
      final all = en ? 'All chats' : 'كل المحادثات';
      final row = find.ancestor(
        of: find.text(title),
        matching: find.byType(FTile),
      );
      expect(
        find.descendant(of: row, matching: find.byIcon(FIcons.chevronsUpDown)),
        findsOneWidget,
      );
      expect(
        find.descendant(of: row, matching: find.byIcon(FIcons.chevronRight)),
        findsNothing,
      );
      expect(store.state.prefs.homeMode, HomeMode.lastChat);
      expect(find.text(last), findsOneWidget);

      await tapAndSettle(tester, find.text(title));
      final menu = find.byType(LnMenuCard);
      expect(menu, findsOneWidget);
      final rowRect = tester.getRect(row);
      final menuRect = tester.getRect(menu);
      // Lined up with the row's end edge, just below it.
      if (en) {
        expect(menuRect.right, rowRect.right);
      } else {
        expect(menuRect.left, rowRect.left);
      }
      expect(menuRect.top, rowRect.bottom + 4);
      final options = find.descendant(
        of: menu,
        matching: find.byType(LnMenuRow),
      );
      expect(options, findsNWidgets(2));
      for (final option in tester.widgetList<LnMenuRow>(options)) {
        expect(option.checked, option.label == last, reason: option.label);
        expect(
          tester.getSize(find.byWidget(option)).height,
          greaterThanOrEqualTo(LnSize.minTouch),
        );
      }

      await tapAndSettle(
        tester,
        find.descendant(of: menu, matching: find.text(all)),
      );
      expect(find.byType(LnMenuCard), findsNothing);
      expect(store.state.prefs.homeMode, HomeMode.list);
      expect(devicePrefs.getString('lonora.homeMode'), 'list');
      expect(find.text(all), findsOneWidget);
      expect(find.text(last), findsNothing);
    });
  }

  testWidgets('the appearance is picked in place; dismissing keeps it', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    final (_, store) = await pumpSettings(tester);
    final row = find.ancestor(
      of: find.text('Appearance'),
      matching: find.byType(FTile),
    );
    expect(
      find.descendant(of: row, matching: find.byIcon(FIcons.chevronsUpDown)),
      findsOneWidget,
    );
    await tapAndSettle(tester, find.text('Appearance'));
    final menu = find.byType(LnMenuCard);
    expect(
      find.descendant(of: menu, matching: find.byType(LnMenuRow)),
      findsNWidgets(3),
    );
    // The current theme is the selected option for a screen reader too.
    final light = tester
        .getSemantics(find.descendant(of: menu, matching: find.text('Light')))
        .getSemanticsData();
    expect(light.flagsCollection.isSelected, Tristate.isTrue);
    expect(find.byIcon(FIcons.check), findsOneWidget);

    // An outside tap closes it without a change.
    await tester.tapAt(const Offset(200, 800));
    await tester.pumpAndSettle();
    expect(find.byType(LnMenuCard), findsNothing);
    expect(store.state.prefs.themeMode, AppThemeMode.light);

    await tapAndSettle(tester, find.text('Appearance'));
    await tapAndSettle(
      tester,
      find.descendant(of: find.byType(LnMenuCard), matching: find.text('Dark')),
    );
    expect(store.state.prefs.themeMode, AppThemeMode.dark);
    expect(devicePrefs.getString('lonora.theme'), 'dark');
    expect(find.text('Dark'), findsOneWidget);
    semantics.dispose();
  });

  testWidgets('chat experience opens the conversation preferences', (
    tester,
  ) async {
    await pumpSettings(tester);
    await tapAndSettle(tester, find.text('Chat experience'));
    expect(find.text('Chat experience'), findsNWidgets(2));
    expect(find.byType(LnSwitch), findsNWidgets(4));
  });

  testWidgets('clear cache asks first and keeps the outbox', (tester) async {
    final pending = OutgoingMessage(
      nonce: 'n1',
      threadId: 'thread-1',
      body: const {'content': 'not sent yet', 'client_nonce': 'n1'},
      delivery: Delivery.queued,
      createdAt: DateTime.utc(2026, 11, 27),
    );
    final (_, store) = await pumpSettings(tester, outbox: [pending]);
    final scope = LocalStore.scope(testServer, testOwner.id);
    testLocalStore.docs['$scope/shell'] = {'cached': true};
    testLocalStore.docs['$scope/outbox'] = [pending.toJson()];
    // A listed conversation and one no longer listed (archived, deleted): both go.
    testLocalStore.docs['$scope/thread_thread-1'] = {'cached': true};
    testLocalStore.docs['$scope/thread_gone'] = {'cached': true};
    expect(store.state.session.signedIn, isTrue);
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

  for (final locale in ['en', 'ar']) {
    testWidgets('every target is labelled and at least 48 dp; rows are 52 dp '
        '($locale)', (tester) async {
      final semantics = tester.ensureSemantics();
      await pumpSettings(tester, locale: locale);
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      final row = find.ancestor(
        of: find.text(locale == 'en' ? 'Voice' : 'الصوت'),
        matching: find.byType(FTile),
      );
      expect(tester.getSize(row).height, LnSize.tileRow);
      semantics.dispose();
    });
  }

  testWidgets('text at 1.3× lays out without overflow', (tester) async {
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await pumpSettings(tester, locale: 'ar');
    await tester.drag(find.byType(SettingsScreen), const Offset(0, -2000));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      await withRealShadows(() async {
        await pumpSettings(tester, locale: v.locale, theme: v.theme);
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/settings_${v.name}.png'),
        );
      });
    });
  }

  for (final v in [goldenVariants[0], goldenVariants[1]]) {
    testWidgets('golden appearance picker ${v.name}', (tester) async {
      await withRealShadows(() async {
        await pumpSettings(tester, locale: v.locale, theme: v.theme);
        await tapAndSettle(tester, find.text('المظهر'));
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/settings_picker_${v.name}.png'),
        );
      });
    });
  }
}
