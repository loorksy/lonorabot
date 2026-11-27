// Account, notifications, voice and about pages: what they read, what they write, and one
// golden of each.
//
// Regenerate goldens with: flutter test --update-goldens test/features/settings_core
import 'dart:async';

import 'package:flutter/foundation.dart'
    show LicenseEntryWithLineBreaks, LicenseRegistry;
import 'package:async_redux/async_redux.dart' show Store;
import 'package:flutter/material.dart' show TextField;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FIcons, FTheme, FTile, FTileGroup;
import 'package:lonora/app/routes.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/design/design.dart'
    show LnIcons, LnPalette, LnSize, LnSpace;
import 'package:lonora/features/me/me_screen.dart' show OwnerInitialAvatar;
import 'package:lonora/features/settings/about_screen.dart';
import 'package:lonora/features/settings/account_screen.dart';
import 'package:lonora/features/settings/notifications_screen.dart';
import 'package:lonora/features/settings/settings_common.dart'
    show SettingsNote;
import 'package:lonora/features/settings/voice_settings_screen.dart';
import 'package:lonora/l10n/l10n.dart' show ltr;
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart';
import 'feature_harness.dart';

void main() {
  setUpAll(setUpFeatureTests);

  /// The store of the last [pumpPage].
  late Store<AppState> pageStore;

  Future<ScriptedApi> pumpPage(
    WidgetTester tester,
    Widget page, {
    String locale = 'en',
    AppThemeMode theme = AppThemeMode.light,
    void Function(ScriptedApi api)? routes,
    int permission = 1,
    ShellState shell = const ShellState(),
  }) async {
    final api = await setUpServices(
      permission: permission,
      stored: StoredSession(
        server: testServer,
        token: 'secret-token-never-shown',
        ownerId: testOwner.id,
        email: testOwner.email,
        expiresAt: DateTime(2026, 11, 28, 9, 30),
      ),
    );
    routes?.call(api);
    final store = pageStore = testStore(
      locale: locale,
      theme: theme,
      shell: shell,
    );
    setFeatureViewport(tester);
    await tester.pumpWidget(featureApp(store, testRouter(page)));
    await tester.pumpAndSettle();
    return api;
  }

  group('account', () {
    void routes(ScriptedApi api) {
      api.on(
        'GET /owner/profile',
        (_) => profileJson(
          name: 'Ahmed',
          devices: [
            {'id': 'dev-1', 'name': 'Pixel 8'},
          ],
        ),
      );
      api.on(
        'PUT /owner/preferences',
        (body) => profileJson(
          name: 'Ahmed',
          address: asString(asJson(body)['address']),
          devices: [
            {'id': 'dev-1', 'name': 'Pixel 8'},
          ],
        ),
      );
    }

    testWidgets('shows the owner, server, session end and passkey devices', (
      tester,
    ) async {
      await pumpPage(tester, const AccountScreen(), routes: routes);
      expect(find.textContaining('owner@example.com'), findsOneWidget);
      expect(find.text('Ahmed'), findsOneWidget);
      expect(find.textContaining('lonora.example.com'), findsOneWidget);
      expect(find.textContaining('Nov 28 9:30 AM'), findsOneWidget);
      await scrollTo(tester, find.text('Pixel 8'));
      expect(find.text('Pixel 8'), findsOneWidget);
      expect(find.textContaining('secret-token'), findsNothing);
    });

    testWidgets('ms:C13 the title is not repeated as the first label', (
      tester,
    ) async {
      await pumpPage(tester, const AccountScreen(), routes: routes);
      expect(find.text('Account'), findsOneWidget);
    });

    testWidgets('sign-out is text only, in the error colour, on a card of '
        'its own 32 dp below the last group (Arabic)', (tester) async {
      await pumpPage(
        tester,
        const AccountScreen(),
        routes: routes,
        locale: 'ar',
      );
      final signOut = find.text('تسجيل الخروج');
      await scrollTo(tester, signOut);
      expect(find.byIcon(LnIcons.logOut), findsNothing);
      final row = find.ancestor(of: signOut, matching: find.byType(FTile));
      expect(
        find.descendant(of: row, matching: find.byType(Icon)),
        findsNothing,
      );
      expect(tester.widget<Text>(signOut).style?.color, LnPalette.light.error);
      // Start-aligned: in Arabic, 16 dp in from the card's right edge.
      expect(tester.getRect(row).right - tester.getRect(signOut).right, 16);
      final groups = find.byType(FTileGroup);
      final card = tester.getRect(groups.last);
      expect(card.height, LnSize.tileRow);
      final before = tester.getRect(
        groups.at(tester.widgetList(groups).length - 2),
      );
      // The passkey group's footnote sits between them.
      expect(card.top, greaterThan(before.bottom + LnSpace.xxl - 1));
    });

    for (final locale in ['en', 'ar']) {
      testWidgets('the owner\'s initial, Ø64, centred above the first '
          'group; detail rows carry no icon ($locale)', (tester) async {
        await pumpPage(
          tester,
          const AccountScreen(),
          routes: routes,
          locale: locale,
        );
        final avatar = find.byType(OwnerInitialAvatar);
        expect(tester.getSize(avatar), const Size.square(64));
        expect(tester.getCenter(avatar).dx, 393 / 2);
        final first = tester.getRect(find.byType(FTileGroup).first);
        expect(first.top - tester.getRect(avatar).bottom, LnSpace.xl);
        // No «tap to change» line: Lonora has no owner picture to upload. The initial is the
        // only text above the first group.
        final texts = find.descendant(
          of: find.byType(ListView),
          matching: find.byType(Text),
        );
        final above = [
          for (var i = 0; i < texts.evaluate().length; i++)
            if (tester.getRect(texts.at(i)).top < first.top)
              tester.widget<Text>(texts.at(i)).data,
        ];
        expect(above, ['A']);
        for (final tile in tester.widgetList<FTile>(
          find.descendant(
            of: find.byType(FTileGroup).first,
            matching: find.byType(FTile),
          ),
        )) {
          expect(
            find.descendant(
              of: find.byWidget(tile),
              matching: find.byWidgetPredicate(
                (w) =>
                    w is Icon &&
                    w.icon != FIcons.chevronRight &&
                    w.icon != FIcons.chevronLeft,
              ),
            ),
            findsNothing,
          );
        }
      });
    }

    testWidgets('identity rows: name, form of address, email, user id; the '
        'user id is a Latin value with no chevron (Arabic)', (tester) async {
      await pumpPage(
        tester,
        const AccountScreen(),
        routes: routes,
        locale: 'ar',
      );
      final group = find.byType(FTileGroup).first;
      final titles = [
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
              .data,
      ];
      expect(titles, [
        'الاسم',
        'طريقة المخاطبة',
        'البريد الإلكتروني',
        'معرّف المستخدم',
      ]);
      expect(find.text(ltr('owner-1')), findsOneWidget);
      final idRow = find.ancestor(
        of: find.text('معرّف المستخدم'),
        matching: find.byType(FTile),
      );
      expect(
        find.descendant(of: idRow, matching: find.byIcon(FIcons.chevronRight)),
        findsNothing,
      );
    });

    testWidgets('sign out asks first, then revokes the session', (
      tester,
    ) async {
      final api = await pumpPage(tester, const AccountScreen(), routes: routes);
      final store = pageStore;
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

    testWidgets('sign-out cannot run twice while the server is slow', (
      tester,
    ) async {
      final api = await pumpPage(tester, const AccountScreen(), routes: routes);
      final store = pageStore;
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

    testWidgets('form of address is saved alone', (tester) async {
      final api = await pumpPage(tester, const AccountScreen(), routes: routes);
      await tapAndSettle(tester, find.text('Form of address'));
      await tester.enterText(find.byType(EditableText), 'Abu Khalid');
      await tapAndSettle(tester, find.text('Save'));
      final put = api.callsTo('PUT', '/owner/preferences').single;
      expect(put.body, {'address': 'Abu Khalid'});
      expect(find.text('Abu Khalid'), findsOneWidget);
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
    });

    testWidgets('offline profile read offers a retry, never «not set»', (
      tester,
    ) async {
      final api = await pumpPage(
        tester,
        const AccountScreen(),
        routes: (api) =>
            api.on('GET /owner/profile', (_) => throw ApiError.network()),
      );
      expect(find.textContaining('Could not connect'), findsOneWidget);
      // Unknown is not «Not set», «Automatic» or «no devices».
      expect(find.text('Not set'), findsNothing);
      expect(find.textContaining('Automatic'), findsNothing);
      expect(find.textContaining('No devices'), findsNothing);
      routes(api);
      await tapAndSettle(tester, find.textContaining('Could not connect'));
      expect(find.text('Ahmed'), findsOneWidget);
    });

    testWidgets('a failed refresh keeps the page and says why', (tester) async {
      final api = await pumpPage(tester, const AccountScreen(), routes: routes);
      api.on('GET /owner/profile', (_) => throw ApiError.network());
      await tester.fling(pageScrollable, const Offset(0, 400), 1000);
      await tester.pumpAndSettle();
      expect(find.text('Ahmed'), findsOneWidget);
      expect(find.textContaining('Could not connect'), findsOneWidget);
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
    });

    testWidgets('time zone: this phone’s, saved in the reach-me policy', (
      tester,
    ) async {
      final api = await pumpPage(
        tester,
        const AccountScreen(),
        routes: (api) {
          routes(api);
          api.on(
            'GET /owner/profile',
            (_) => {
              ...profileJson(name: 'Ahmed'),
              'reach_me': {
                ...asJson(profileJson()['reach_me']),
                'timezone': 'UTC',
              },
            },
          );
        },
      );
      await tapAndSettle(tester, find.text('Time zone'));
      expect(find.text('This phone’s time zone'), findsOneWidget);
      // The phone answers Asia/Riyadh (feature_harness).
      await tapAndSettle(tester, find.textContaining('Asia/Riyadh'));
      final body = asJson(api.callsTo('PUT', '/owner/preferences').single.body);
      expect(body.keys, ['reach_me']);
      final sent = asJson(body['reach_me']);
      expect(sent['timezone'], 'Asia/Riyadh');
      expect(sent['channel'], 'message');
      expect(sent.containsKey('enabled'), isFalse);
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
    });

    testWidgets('time zone: another one typed; an unknown one is refused', (
      tester,
    ) async {
      final api = await pumpPage(tester, const AccountScreen(), routes: routes);
      api.on(
        'PUT /owner/preferences',
        (_) => throw ApiError(status: 422, code: 'invalid_timezone'),
      );
      await tapAndSettle(tester, find.text('Time zone'));
      await tapAndSettle(tester, find.text('Another time zone…'));
      // An identifier: left to right, never auto-corrected.
      expect(
        tester
            .widget<TextField>(
              find.ancestor(
                of: find.byType(EditableText),
                matching: find.byType(TextField),
              ),
            )
            .autocorrect,
        isFalse,
      );
      expect(
        tester
            .state<EditableTextState>(find.byType(EditableText))
            .renderEditable
            .textDirection,
        TextDirection.ltr,
      );
      await tester.enterText(find.byType(EditableText), 'Mars/Olympus');
      await tapAndSettle(tester, find.text('Save'));
      final sent = asJson(
        asJson(
          api.callsTo('PUT', '/owner/preferences').single.body,
        )['reach_me'],
      );
      expect(sent['timezone'], 'Mars/Olympus');
      expect(
        find.text('Choose a valid time zone, such as Asia/Riyadh.'),
        findsOneWidget,
      );
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
    });

    testWidgets('golden light_ar', (tester) async {
      await withRealShadows(() async {
        await pumpPage(
          tester,
          const AccountScreen(),
          locale: 'ar',
          routes: routes,
        );
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/account_light_ar.png'),
        );
      });
    });

    testWidgets('golden dark_ar', (tester) async {
      await withRealShadows(() async {
        await pumpPage(
          tester,
          const AccountScreen(),
          locale: 'ar',
          theme: AppThemeMode.dark,
          routes: routes,
        );
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/account_dark_ar.png'),
        );
      });
    });
  });

  group('notifications', () {
    late Json reach;
    void routes(
      ScriptedApi api, {
      List<Map<String, String>> devices = const [],
    }) {
      reach = asJson(profileJson(devices: devices)['reach_me']);
      api.on(
        'GET /owner/profile',
        (_) => {...profileJson(devices: devices), 'reach_me': reach},
      );
      api.on('PUT /owner/preferences', (body) {
        reach = {...reach, ...asJson(asJson(body)['reach_me'])};
        reach['enabled'] = reach['channel'] == 'call';
        return {...profileJson(devices: devices), 'reach_me': reach};
      });
      api.on(
        'GET /attention/policy',
        (_) => {'opportunities': true, 'informational': false, 'locale': 'ar'},
      );
      api.on('PUT /attention/policy', (body) => body);
    }

    testWidgets('reach-me choice saves without the derived flag', (
      tester,
    ) async {
      final api = await pumpPage(
        tester,
        const NotificationsScreen(),
        routes: routes,
      );
      expect(find.text('Notifications on'), findsOneWidget);
      await tapAndSettle(tester, find.text('Notify me'));
      final body = asJson(api.callsTo('PUT', '/owner/preferences').single.body);
      final sent = asJson(body['reach_me']);
      expect(sent['channel'], 'notify');
      expect(sent.containsKey('enabled'), isFalse);
      expect(body.keys, ['reach_me']);
    });

    testWidgets('calls need a registered device', (tester) async {
      final api = await pumpPage(
        tester,
        const NotificationsScreen(),
        routes: routes,
      );
      await tapAndSettle(tester, find.text('Call me'));
      expect(api.callsTo('PUT', '/owner/preferences'), isEmpty);
      expect(
        find.textContaining('Register your device from Lonora on the web'),
        findsOneWidget,
      );
    });

    testWidgets('choosing calls picks the enrolled device', (tester) async {
      final api = await pumpPage(
        tester,
        const NotificationsScreen(),
        routes: (api) => routes(
          api,
          devices: [
            {'id': 'dev-1', 'name': 'Pixel 8'},
          ],
        ),
      );
      await tapAndSettle(tester, find.text('Call me'));
      final sent = asJson(
        asJson(
          api.callsTo('PUT', '/owner/preferences').single.body,
        )['reach_me'],
      );
      expect(sent['channel'], 'call');
      expect(sent['device_id'], 'dev-1');
      expect(sent['action_required'], isTrue);
      expect(find.text('Pixel 8'), findsOneWidget);
    });

    testWidgets('quiet hours turn on with the phone time zone', (tester) async {
      final api = await pumpPage(
        tester,
        const NotificationsScreen(),
        routes: routes,
      );
      await scrollTo(tester, find.text('Mute notifications at night'));
      await tapAndSettle(tester, find.text('Mute notifications at night'));
      final sent = asJson(
        asJson(
          api.callsTo('PUT', '/owner/preferences').single.body,
        )['reach_me'],
      );
      expect(sent['quiet_start_minute'], 22 * 60);
      expect(sent['quiet_end_minute'], 8 * 60);
      expect(sent['quiet_start_hour'], 22);
      expect(sent['timezone'], 'Asia/Riyadh');
      await scrollTo(tester, find.text('Urgent always arrives'));
      expect(find.text('Urgent always arrives'), findsOneWidget);
    });

    testWidgets('offline first read: retry, or pull to refresh', (
      tester,
    ) async {
      final api = await pumpPage(
        tester,
        const NotificationsScreen(),
        routes: (api) {
          routes(api);
          api.on('GET /owner/profile', (_) => throw ApiError.network());
        },
      );
      expect(find.textContaining('Could not connect'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
      routes(api);
      await tester.fling(pageScrollable, const Offset(0, 400), 1000);
      await tester.pumpAndSettle();
      expect(api.callsTo('GET', '/owner/profile'), hasLength(2));
      expect(find.text('Message me'), findsOneWidget);
    });

    testWidgets('quiet hours read in the date digits: Arabic-Indic in Arabic', (
      tester,
    ) async {
      await pumpPage(
        tester,
        const NotificationsScreen(),
        locale: 'ar',
        routes: (api) {
          routes(api);
          reach = {
            ...reach,
            'quiet_start_minute': 22 * 60,
            'quiet_end_minute': 8 * 60 + 30,
            'quiet_start_hour': 22,
            'quiet_end_hour': 8,
          };
        },
      );
      await scrollTo(tester, find.text(ltr('٠٨:٣٠')));
      expect(find.text(ltr('٢٢:٠٠')), findsOneWidget);
      expect(find.text(ltr('٠٨:٣٠')), findsOneWidget);
      expect(find.textContaining('22:00'), findsNothing);
      expect(find.textContaining('من ${ltr('٢٢:٠٠')} إلى'), findsOneWidget);
    });

    testWidgets('quiet hours: a new start time keeps the end', (tester) async {
      final api = await pumpPage(
        tester,
        const NotificationsScreen(),
        routes: (api) {
          routes(api);
          reach = {
            ...reach,
            'quiet_start_minute': 22 * 60,
            'quiet_end_minute': 8 * 60,
            'quiet_start_hour': 22,
            'quiet_end_hour': 8,
          };
        },
      );
      await scrollTo(tester, find.text('From'));
      await tapAndSettle(tester, find.text('From'));
      // The wheel starts at 22:00; one hour down is 23:00.
      await tester.drag(find.text('22').last, const Offset(0, -40));
      await tester.pumpAndSettle();
      await tapAndSettle(tester, find.text('Save'));
      final sent = asJson(
        asJson(
          api.callsTo('PUT', '/owner/preferences').single.body,
        )['reach_me'],
      );
      expect(sent['quiet_start_minute'], 23 * 60);
      expect(sent['quiet_start_hour'], 23);
      expect(sent['quiet_end_minute'], 8 * 60);
      expect(sent['timezone'], 'Asia/Riyadh');
      await scrollTo(tester, find.text('From'));
      expect(find.textContaining('23:00'), findsWidgets);
    });

    testWidgets('confirmed opportunities: one save at a time', (tester) async {
      final answer = Completer<Object?>();
      final api = await pumpPage(
        tester,
        const NotificationsScreen(),
        routes: (api) {
          routes(api);
          api.on('PUT /attention/policy', (_) => answer.future);
        },
      );
      final row = find.text('Notify me about confirmed opportunities');
      await scrollTo(tester, row);
      await tester.tap(row);
      await tester.pump();
      await tester.tap(row, warnIfMissed: false);
      await tester.pump();
      expect(api.callsTo('PUT', '/attention/policy'), hasLength(1));
      expect(asJson(api.callsTo('PUT', '/attention/policy').single.body), {
        'opportunities': false,
        'informational': false,
        'locale': 'en',
      });
      answer.complete({
        'opportunities': false,
        'informational': false,
        'locale': 'en',
      });
      await tester.pumpAndSettle();
    });

    testWidgets('per agent: whether each agent alerts; opens its settings', (
      tester,
    ) async {
      await pumpPage(
        tester,
        const NotificationsScreen(),
        shell: const ShellState(
          agents: {
            'agent-1': Agent(id: 'agent-1', name: 'Atlas'),
            'agent-2': Agent(id: 'agent-2', name: 'Nora'),
          },
          agentOrder: ['agent-1', 'agent-2'],
        ),
        routes: (api) {
          routes(api);
          api.on(
            'GET /agents/notifications',
            (_) => {
              'agent-1': {'in_app': false, 'calls': true, 'daily_limit': null},
            },
          );
        },
      );
      await scrollTo(tester, find.text('Per agent'));
      await scrollTo(tester, find.textContaining('Nora'));
      expect(find.text('Notifications off'), findsOneWidget);
      expect(find.text('Notifications on'), findsWidgets);
      await tapAndSettle(tester, find.textContaining('Atlas'));
      expect(
        find.text('stub:${Routes.agentSettings('agent-1')}'),
        findsOneWidget,
      );
    });

    testWidgets('per agent: a row without its state is still 48 dp', (
      tester,
    ) async {
      await pumpPage(
        tester,
        const NotificationsScreen(),
        shell: const ShellState(
          agents: {'agent-1': Agent(id: 'agent-1', name: 'Atlas')},
          agentOrder: ['agent-1'],
        ),
        routes: (api) {
          routes(api);
          api.on(
            'GET /agents/notifications',
            (_) => throw ApiError(status: 500, code: 'request_failed'),
          );
        },
      );
      await scrollTo(tester, find.textContaining('Atlas'));
      expect(find.text('Notifications on'), findsNothing);
      expect(
        tester
            .getSize(
              find.ancestor(
                of: find.textContaining('Atlas'),
                matching: find.byType(FTile),
              ),
            )
            .height,
        greaterThanOrEqualTo(LnSize.minTouch),
      );
    });

    testWidgets('golden light_ar', (tester) async {
      await withRealShadows(() async {
        await pumpPage(
          tester,
          const NotificationsScreen(),
          locale: 'ar',
          routes: routes,
        );
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/notifications_light_ar.png'),
        );
      });
    });

    testWidgets('golden dark_en, permission off', (tester) async {
      await withRealShadows(() async {
        await pumpPage(
          tester,
          const NotificationsScreen(),
          theme: AppThemeMode.dark,
          permission: 0,
          routes: routes,
        );
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/notifications_dark_en.png'),
        );
      });
    });
  });

  testWidgets('notifications and account at 1.3× text without overflow', (
    tester,
  ) async {
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await pumpPage(
      tester,
      const NotificationsScreen(),
      locale: 'ar',
      routes: (api) => api.on(
        'GET /owner/profile',
        (_) => profileJson(
          channel: 'call',
          devices: [
            {'id': 'dev-1', 'name': 'Pixel 8'},
          ],
          quietStart: 22 * 60,
          quietEnd: 7 * 60 + 30,
        ),
      ),
    );
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -3000));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  group('voice', () {
    void routes(ScriptedApi api) => api.on(
      'GET /voice/status',
      (_) => {
        'transport': 'gpt_live',
        'transport_configured': false,
        'model': 'gpt-live-1',
      },
    );

    testWidgets('shows the server status and the routing link', (tester) async {
      await pumpPage(tester, const VoiceSettingsScreen(), routes: routes);
      expect(find.text('Not configured'), findsOneWidget);
      expect(find.textContaining('gpt-live-1'), findsOneWidget);
      expect(
        find.textContaining('Start a call from the call button'),
        findsOneWidget,
      );
      await tapAndSettle(tester, find.text('Global model routing'));
      expect(find.text('stub:/settings/models'), findsOneWidget);
    });

    testWidgets('ms:C12 the call hint is in the section footers\' style', (
      tester,
    ) async {
      await pumpPage(tester, const VoiceSettingsScreen(), routes: routes);
      final note = find.descendant(
        of: find.byType(SettingsNote),
        matching: find.byType(Text),
      );
      final footer = FTheme.of(tester.element(note))
          .tileGroupStyle
          .descriptionTextStyle
          .resolve(const {});
      expect(tester.widget<Text>(note).style, footer);
      // In from the page edge as far as the footers, 16 dp inside the cards.
      final page = tester.getRect(find.byType(VoiceSettingsScreen));
      expect(
        tester.getRect(note).left - page.left,
        LnSpace.pageGutter + LnSpace.md,
      );
    });

    testWidgets('golden dark_ar', (tester) async {
      await withRealShadows(() async {
        await pumpPage(
          tester,
          const VoiceSettingsScreen(),
          locale: 'ar',
          theme: AppThemeMode.dark,
          routes: routes,
        );
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/voice_dark_ar.png'),
        );
      });
    });
  });

  group('about', () {
    void routes(ScriptedApi api) => api.on(
      'GET /version',
      (_) => {'version': '0.2.0', 'build': '1a2b3c4d5e6f'},
    );

    testWidgets('app and server versions', (tester) async {
      await pumpPage(tester, const AboutScreen(), routes: routes);
      expect(find.textContaining('1.0.0 (7)'), findsOneWidget);
      expect(find.textContaining('0.2.0 · 1a2b3c4'), findsOneWidget);
    });

    testWidgets('the web link leaves the app: an up-right arrow that '
        'does not mirror, no chevron', (tester) async {
      await pumpPage(tester, const AboutScreen(), routes: routes, locale: 'ar');
      final row = find.ancestor(
        of: find.text('فتح Lonora على الويب'),
        matching: find.byType(FTile),
      );
      await scrollTo(tester, row);
      final arrow = find.descendant(
        of: row,
        matching: find.byIcon(FIcons.arrowUpRight),
      );
      expect(arrow, findsOneWidget);
      expect(FIcons.arrowUpRight.matchTextDirection, isFalse);
      expect(
        find.descendant(of: row, matching: find.byIcon(FIcons.chevronRight)),
        findsNothing,
      );
    });

    testWidgets('licenses in the app\'s own pages', (tester) async {
      LicenseRegistry.addLicense(
        () => Stream.value(
          const LicenseEntryWithLineBreaks([
            'a_test_package',
          ], 'Test license text.'),
        ),
      );
      await pumpPage(tester, const AboutScreen(), routes: routes);
      await tapAndSettle(tester, find.text('Open-source licenses'));
      // The registry is read off the fake clock.
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 300)),
      );
      await tester.pumpAndSettle();
      expect(find.text('Open-source licenses'), findsOneWidget);
      await tapAndSettle(tester, find.text('a_test_package'));
      expect(find.text('Test license text.'), findsOneWidget);
      await tapAndSettle(tester, find.bySemanticsLabel('Back'));
      expect(find.text('a_test_package'), findsOneWidget);
    });

    testWidgets('golden light_en', (tester) async {
      await withRealShadows(() async {
        await pumpPage(tester, const AboutScreen(), routes: routes);
        // The logo is decoded off the fake clock, so the image matches in any test order.
        await tester.runAsync(
          () => precacheImage(
            const AssetImage('assets/brand/logo.png'),
            tester.element(find.byType(AboutScreen)),
          ),
        );
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/about_light_en.png'),
        );
      });
    });
  });
}
