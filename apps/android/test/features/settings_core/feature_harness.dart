// Test harness for the WP-A1 screens (auth, Me, core settings): a scripted API, in-memory
// services, the app's localisation and themes with real fonts, and a router whose other
// destinations are stubs that print their location.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/app/app_strings.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/auth/auth_strings.dart';
import 'package:lonora/features/me/me_strings.dart';
import 'package:lonora/features/settings/settings_core_strings.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../design/fonts.dart';
import '../../design/harness.dart';

const testServer = 'https://lonora.example.com';
const testOwner = Owner(id: 'owner-1', email: 'owner@example.com');

/// One recorded request.
typedef ApiCall = ({String method, String path, Object? body});

/// Answers requests from [routes] (`'GET /owner/profile'` → handler). A handler may throw an
/// `ApiError`. Unknown GETs answer an empty object; unknown writes answer `{}` too, except an
/// order (`POST /trading/execute`), which fails loudly.
class ScriptedApi extends ApiClient {
  ScriptedApi() : super(userAgent: 'Lonora-Android/test');

  final Map<String, Object? Function(Object? body)> routes = {};
  final List<ApiCall> calls = [];

  /// `GET {server}/api/onboarding` and other unauthenticated probes.
  Object? Function(String server, String path, Object? body)? onProbe;

  void on(String route, Object? Function(Object? body) handler) =>
      routes[route] = handler;

  Future<dynamic> _answer(String method, String path, Object? body) async {
    calls.add((method: method, path: path, body: body));
    final handler = routes['$method $path'];
    if (handler == null) {
      // An order is never answered by default: only a test's own handler may.
      if (path == '/trading/execute') {
        throw StateError('unexpected $method $path');
      }
      return <String, Object?>{};
    }
    return handler(body);
  }

  List<ApiCall> callsTo(String method, String path) => [
    for (final c in calls)
      if (c.method == method && c.path == path) c,
  ];

  @override
  Future<dynamic> get(
    String path, {
    Map<String, Object?>? query,
    Duration? timeout,
  }) => _answer('GET', path, null);

  @override
  Future<dynamic> post(String path, [Object? body]) =>
      _answer('POST', path, body);

  @override
  Future<dynamic> postWithin(String path, Object body, Duration timeout) =>
      _answer('POST', path, body);

  @override
  Future<dynamic> put(String path, [Object? body]) =>
      _answer('PUT', path, body);

  @override
  Future<dynamic> patch(String path, [Object? body]) =>
      _answer('PATCH', path, body);

  @override
  Future<dynamic> delete(String path, {Map<String, Object?>? query}) =>
      _answer('DELETE', path, null);

  @override
  Future<dynamic> probe(
    String server,
    String path, {
    Object? body,
    String method = 'GET',
  }) async {
    calls.add((method: method, path: 'probe:$server$path', body: body));
    final handler = onProbe;
    if (handler == null) return {'owner_initialized': true};
    return handler(server, path, body);
  }
}

class MemorySecureStore extends SecureStore {
  MemorySecureStore() : super(const FlutterSecureStorage());
  StoredSession? session;
  String? server;
  String? email;

  @override
  Future<StoredSession?> readSession() async => session;
  @override
  Future<void> writeSession(StoredSession s) async {
    session = s;
    server = s.server;
    email = s.email;
  }

  @override
  Future<void> clearSession() async => session = null;
  @override
  Future<String?> lastServer() async => server;
  @override
  Future<String?> lastEmail() async => email;
  @override
  Future<void> rememberServer(String value) async => server = value;
}

late L10n testL10n;

/// Fonts, catalogs and platform-channel stubs, once per test file.
Future<void> setUpFeatureTests() async {
  await loadAppFonts();
  testL10n = await L10n.load();
  registerAppStrings();
  registerAuthStrings(testL10n);
  registerMeStrings(testL10n);
  registerSettingsCoreStrings(testL10n);
}

/// Fresh services for one test. [permission] is the `PermissionStatus` index the
/// permission_handler channel answers (1 = granted, 0 = denied).
Future<ScriptedApi> setUpServices({
  Map<String, Object> prefs = const {},
  int permission = 1,
  StoredSession? stored,
}) async {
  SharedPreferences.setMockInitialValues(prefs);
  final api = ScriptedApi();
  final secure = MemorySecureStore()
    ..session = stored
    ..server = stored?.server;
  await registerServices(
    apiClient: api,
    secure: secure,
    local: testLocalStore = MemoryLocalStore(),
    prefs: await SharedPreferences.getInstance(),
    info: const AppInfo(
      version: '1.0.0',
      buildNumber: '7',
      packageName: 'ai.lonora.android',
    ),
  );
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(
    const MethodChannel('ai.lonora.android/platform'),
    (call) async => switch (call.method) {
      'openNotificationSettings' => true,
      'timeZone' => 'Asia/Riyadh',
      _ => null,
    },
  );
  messenger.setMockMethodCallHandler(
    const MethodChannel('flutter.baseflow.com/permissions/methods'),
    (call) async => switch (call.method) {
      'checkPermissionStatus' => permission,
      'requestPermissions' => {
        for (final p in (call.arguments as List).cast<int>()) p: 1,
      },
      _ => null,
    },
  );
  return api;
}

/// A signed-in store (or signed-out with [signedIn] false) with the given prefs.
Store<AppState> testStore({
  bool signedIn = true,
  String locale = 'ar',
  AppThemeMode theme = AppThemeMode.light,
  SessionState? session,
  ShellState shell = const ShellState(),
  List<OutgoingMessage> outbox = const [],
}) {
  final store = Store<AppState>(
    initialState: AppState(
      session:
          session ??
          (signedIn
              ? const SessionState(
                  status: SessionStatus.signedIn,
                  server: testServer,
                  owner: testOwner,
                  lastServer: testServer,
                  lastEmail: 'owner@example.com',
                )
              : const SessionState(
                  status: SessionStatus.signedOut,
                  lastServer: testServer,
                  lastEmail: 'owner@example.com',
                )),
      prefs: PrefsState(themeMode: theme, locale: locale),
      shell: shell,
      outbox: outbox,
    ),
  );
  realtime = RealtimeController(store);
  return store;
}

/// Every route a WP-A1 screen can open, as a stub page printing its location.
GoRouter testRouter(
  Widget home, {
  Map<String, WidgetBuilder> pages = const {},
  String initialLocation = '/home',
}) {
  final paths = {
    Routes.signIn,
    Routes.server,
    Routes.connect,
    Routes.chats,
    Routes.me,
    Routes.agents,
    '/routines',
    Routes.tasks,
    '/files',
    '/charts',
    Routes.ownerKnowledge,
    Routes.settings,
    Routes.recovery,
    Routes.account,
    Routes.integrations,
    Routes.models,
    Routes.notifications,
    Routes.voice,
    Routes.running,
    Routes.appearance,
    Routes.usage,
    Routes.about,
    Routes.agentSettings('agent-1'),
  };
  return GoRouter(
    initialLocation: initialLocation,
    routes: [
      GoRoute(path: '/home', builder: (_, _) => home),
      for (final p in paths)
        GoRoute(
          path: p,
          builder: (context, s) =>
              pages[p]?.call(context) ?? StubPage(location: s.uri.toString()),
        ),
    ],
  );
}

class StubPage extends StatelessWidget {
  const StubPage({super.key, required this.location});
  final String location;

  @override
  Widget build(BuildContext context) => Center(child: Text('stub:$location'));
}

/// The app's shell around [router]: locale and theme from the store, as LonoraApp does, with
/// the test fonts.
Widget featureApp(Store<AppState> store, GoRouter router) =>
    StoreProvider<AppState>(
      store: store,
      child: StoreConnector<AppState, ({AppThemeMode mode, String locale})>(
        converter: (s) =>
            (mode: s.state.prefs.themeMode, locale: s.state.prefs.locale),
        builder: (context, vm) {
          final locale = Locale(vm.locale);
          testL10n.setLocale(locale);
          return MaterialApp.router(
            debugShowCheckedModeBanner: false,
            routerConfig: router,
            locale: locale,
            supportedLocales: L10n.supportedLocales,
            localizationsDelegates: [
              testL10n.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
              ...FLocalizations.localizationsDelegates,
            ],
            themeMode: switch (vm.mode) {
              AppThemeMode.system => ThemeMode.light,
              AppThemeMode.light => ThemeMode.light,
              AppThemeMode.dark => ThemeMode.dark,
            },
            theme: lnMaterialTheme(
              LnPalette.light,
              fontFamily: testFontFamily,
              fontFamilyFallback: testFontFallback,
            ),
            darkTheme: lnMaterialTheme(
              LnPalette.dark,
              fontFamily: testFontFamily,
              fontFamilyFallback: testFontFallback,
            ),
            builder: (context, child) {
              final dark = vm.mode == AppThemeMode.dark;
              final palette = dark ? LnPalette.dark : LnPalette.light;
              return LnTheme(
                data: testTheme(dark ? Brightness.dark : Brightness.light),
                child: FTheme(
                  data: lnForuiTheme(
                    palette,
                    fontFamily: testFontFamily,
                    fontFamilyFallback: testFontFallback,
                  ),
                  child: FToaster(child: child ?? const SizedBox.shrink()),
                ),
              );
            },
          );
        },
      ),
    );

/// Golden viewport (393 × 852 dp, DPR 2) with a 24 dp status bar.
void setFeatureViewport(WidgetTester tester) {
  setGoldenViewport(tester);
  tester.view.padding = const FakeViewPadding(top: 48);
  tester.view.viewPadding = const FakeViewPadding(top: 48);
}

/// The four golden variants: (light|dark) × (ar|en).
const goldenVariants = [
  (theme: AppThemeMode.light, locale: 'ar', name: 'light_ar'),
  (theme: AppThemeMode.dark, locale: 'ar', name: 'dark_ar'),
  (theme: AppThemeMode.light, locale: 'en', name: 'light_en'),
  (theme: AppThemeMode.dark, locale: 'en', name: 'dark_en'),
];

/// An owner profile answer as the server sends it.
Map<String, Object?> profileJson({
  String? name,
  String? address,
  String? replyLanguage,
  String channel = 'message',
  List<Map<String, String>> devices = const [],
  int? quietStart,
  int? quietEnd,
}) => {
  'content': '',
  'version': 1,
  'reply_language': replyLanguage,
  'name': name,
  'address': address,
  'reach_me': {
    'channel': channel,
    'enabled': channel == 'call',
    'device_id': channel == 'call' && devices.isNotEmpty
        ? devices.first['id']
        : null,
    'opportunities': false,
    'action_required': channel == 'call',
    'critical': true,
    'timezone': 'Asia/Riyadh',
    'quiet_start_hour': quietStart == null ? null : quietStart ~/ 60,
    'quiet_end_hour': quietEnd == null ? null : quietEnd ~/ 60,
    'quiet_start_minute': quietStart,
    'quiet_end_minute': quietEnd,
    'ttl_seconds': 45,
    'minimum_interval_seconds': 300,
  },
  'devices': devices,
  'delivery': 'in_app_only',
  'shared_with': 'every_agent',
};

/// The page's own scroll view (tile groups have inner scrollables).
Finder get pageScrollable => find.byType(Scrollable).first;

/// Scrolls the page until [finder] is built, then brings it to the top of the viewport (clear
/// of the floating tab bar).
Future<void> scrollTo(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 120, scrollable: pageScrollable);
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
}

/// LocalStore in memory: real file IO never completes inside `testWidgets`' fake async zone.
class MemoryLocalStore implements LocalStore {
  final Map<String, Object?> docs = {};

  @override
  Future<Object?> read(String scope, String name) async => docs['$scope/$name'];

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

late MemoryLocalStore testLocalStore;

/// Taps [finder] and lets press feedback timers and animations finish.
Future<void> tapAndSettle(WidgetTester tester, Finder finder) async {
  await tester.tap(finder);
  await tester.pump(const Duration(milliseconds: 300));
  await tester.pumpAndSettle();
}
