// Shared harness of the agent profile, agent settings, memory, skills, routines, tasks and
// knowledge tests (work package E): real fonts and catalogs, a fake API that records every
// call, a store with a fixture owner snapshot, and a router whose other destinations are
// placeholders printing their location. Animations are off (static avatars, no tickers).
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../design/fonts.dart';
import '../../design/harness.dart';

export '../../design/harness.dart' show withRealShadows;

/// One recorded request.
typedef Call = ({
  String method,
  String path,
  Object? body,
  Map<String, Object?>? query,
});

typedef Handler = Object? Function(Object? body, Map<String, Object?>? query);

/// Answers requests from [handlers] (`'GET /agents'` → body; a handler may throw an
/// `ApiError`) and records every call. Unknown reads answer `{}`; unknown writes `{}`.
class FakeApi extends ApiClient {
  FakeApi() : super(userAgent: 'test') {
    configure(server: 'http://test', token: 'token');
  }

  final calls = <Call>[];
  final handlers = <String, Handler>{};

  void on(String route, Handler handler) => handlers[route] = handler;

  Future<dynamic> _answer(
    String method,
    String path, {
    Object? body,
    Map<String, Object?>? query,
  }) async {
    calls.add((method: method, path: path, body: body, query: query));
    final handler = handlers['$method $path'];
    if (handler == null) return <String, Object?>{};
    return handler(body, query);
  }

  List<Call> callsTo(String method, String path) => [
    for (final c in calls)
      if (c.method == method && c.path == path) c,
  ];

  @override
  Future<dynamic> get(
    String path, {
    Map<String, Object?>? query,
    Duration? timeout,
  }) => _answer('GET', path, query: query);

  @override
  Future<dynamic> post(String path, [Object? body]) =>
      _answer('POST', path, body: body);

  @override
  Future<dynamic> put(String path, [Object? body]) =>
      _answer('PUT', path, body: body);

  @override
  Future<dynamic> patch(String path, [Object? body]) =>
      _answer('PATCH', path, body: body);

  @override
  Future<dynamic> delete(String path, {Map<String, Object?>? query}) =>
      _answer('DELETE', path, query: query);
}

class _MemorySecureStore extends SecureStore {
  _MemorySecureStore() : super(const FlutterSecureStorage());
  @override
  Future<StoredSession?> readSession() async => null;
  @override
  Future<void> writeSession(StoredSession s) async {}
  @override
  Future<void> clearSession() async {}
  @override
  Future<String?> lastServer() async => null;
  @override
  Future<String?> lastEmail() async => null;
  @override
  Future<void> rememberServer(String value) async {}
}

class _MemoryLocalStore implements LocalStore {
  final Map<String, Object?> docs = {};
  @override
  Future<Object?> read(String scope, String name) async => docs['$scope/$name'];
  @override
  Future<void> write(String scope, String name, Object? value) async =>
      docs['$scope/$name'] = value;
  @override
  Future<void> clearScope(String scope) async =>
      docs.removeWhere((key, _) => key.startsWith('$scope/'));
}

late FakeApi fakeApi;

/// Fonts and catalogs, once per test file.
Future<void> setUpWpeHarness() async {
  await loadAppFonts();
  await L10n.load();
}

/// Fresh services and an empty fake API, before each test.
Future<void> resetWpe() async {
  SharedPreferences.setMockInitialValues({});
  fakeApi = FakeApi();
  await registerServices(
    apiClient: fakeApi,
    secure: _MemorySecureStore(),
    local: _MemoryLocalStore(),
    prefs: await SharedPreferences.getInstance(),
    info: const AppInfo(
      version: '1.0.0',
      buildNumber: '1',
      packageName: 'ai.lonora.android',
    ),
  );
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(
        const MethodChannel('ai.lonora.android/platform'),
        (call) async => call.method == 'timeZone' ? 'Asia/Riyadh' : null,
      );
}

const owner = Owner(id: 'owner-1', email: 'owner@example.com');

/// Fixture agents: Lonora (personal), a trading desk (cyan shell → the blue hub), a researcher
/// (violet: neutral hub) and a paused writer.
final fixtureAgents = <Json>[
  {
    'id': 'a-lonora',
    'name': 'Lonora',
    'avatar': 'orb',
    'color': '#8B5CF6',
    'role': 'personal',
    'scope_mode': 'fixed_market',
    'trading_mode': 'ask',
  },
  {
    'id': 'a-gold',
    'name': 'Gold desk',
    'title': 'Gold trader · XAUUSD',
    'description': 'Watches gold around the London and New York sessions.',
    'instructions':
        'Trade only XAUUSD.\nAsk before any new position larger than 0.5 lots.',
    'avatar': 'face-focused',
    'color': '#06B6D4',
    'role': 'general',
    'template': 'trading',
    'scope_mode': 'flexible',
    'scope_revision': 2,
    'trading_account_id': 'acct-1',
    'trading_symbol': 'XAUUSD',
    'trading_mode': 'ask',
  },
  {
    'id': 'a-research',
    'name': 'Research',
    'title': 'Market research',
    'avatar': 'face-thoughtful',
    'color': '#8B5CF6',
    'role': 'general',
    'template': 'research',
    'scope_mode': 'flexible',
    'trading_mode': 'ask',
  },
  {
    'id': 'a-writer',
    'name': 'Writer',
    'title': 'Weekly reports',
    'avatar': 'face-smile',
    'color': '#F97316',
    'role': 'general',
    'template': 'general',
    'scope_mode': 'flexible',
    'paused': true,
  },
];

/// A signed-in store holding the fixture agents.
Store<AppState> wpeStore({
  String locale = 'ar',
  List<Json>? agents,
  List<Json> inbox = const [],
}) {
  final list = (agents ?? fixtureAgents).map(Agent.fromJson).toList();
  return Store<AppState>(
    initialState: AppState(
      session: const SessionState(
        status: SessionStatus.signedIn,
        server: 'http://test',
        owner: owner,
      ),
      prefs: PrefsState(locale: locale),
      shell: ShellState(
        agents: {for (final a in list) a.id: a},
        agentOrder: [for (final a in list) a.id],
        inbox: inbox.map(InboxEntry.fromJson).toList(),
        loaded: true,
      ),
    ),
  );
}

/// [home] at `/home`, the routes it may open as placeholders printing `route:<location>`.
GoRouter wpeRouter(Widget home, {Map<String, Widget> pages = const {}}) {
  Widget stub(GoRouterState s) =>
      pages[s.uri.path] ?? Center(child: Text('route:${s.uri}'));
  final paths = [
    '/agent/:id',
    '/agent/:id/settings',
    '/agent/:id/memory',
    '/agent/:id/skills',
    '/routines',
    '/chats/thread/:id',
    '/files',
    '/charts',
    Routes.voice,
    Routes.notifications,
    Routes.agents,
    Routes.tasks,
    Routes.me,
    Routes.chats,
  ];
  return GoRouter(
    initialLocation: '/home',
    routes: [
      GoRoute(path: '/home', builder: (_, _) => home),
      for (final p in paths) GoRoute(path: p, builder: (_, s) => stub(s)),
    ],
  );
}

/// The app around [router]: themes, forui, toaster, localisation (Arabic RTL or English), a
/// 24 dp status inset, animations off.
Widget wpeApp({
  required Store<AppState> store,
  required GoRouter router,
  Brightness brightness = Brightness.light,
  String locale = 'ar',
  double textScale = 1,
}) {
  final palette = brightness == Brightness.dark
      ? LnPalette.dark
      : LnPalette.light;
  L10n.instance.setLocale(Locale(locale));
  return StoreProvider<AppState>(
    store: store,
    child: MaterialApp.router(
      debugShowCheckedModeBanner: false,
      routerConfig: router,
      locale: Locale(locale),
      supportedLocales: L10n.supportedLocales,
      localizationsDelegates: [
        L10n.instance.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        ...FLocalizations.localizationsDelegates,
      ],
      theme: lnMaterialTheme(
        palette,
        fontFamily: testFontFamily,
        fontFamilyFallback: testFontFallback,
      ),
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(
          padding: const EdgeInsets.only(top: 48),
          viewPadding: const EdgeInsets.only(top: 48),
          disableAnimations: true,
          textScaler: TextScaler.linear(textScale),
        ),
        child: FTheme(
          data: lnForuiTheme(
            palette,
            fontFamily: testFontFamily,
            fontFamilyFallback: testFontFallback,
          ),
          child: LnTheme(
            data: testTheme(brightness),
            child: FToaster(child: child!),
          ),
        ),
      ),
    ),
  );
}

/// Pumps [screen] in the golden viewport (393 × 852 dp, DPR 2) and settles.
Future<Store<AppState>> pumpScreen(
  WidgetTester tester,
  Widget screen, {
  Brightness brightness = Brightness.light,
  String locale = 'ar',
  Store<AppState>? store,
  double textScale = 1,
  Size size = goldenSize,
}) async {
  setGoldenViewport(tester, size: size);
  final s = store ?? wpeStore(locale: locale);
  realtime = RealtimeController(s);
  await tester.pumpWidget(
    wpeApp(
      store: s,
      router: wpeRouter(screen),
      brightness: brightness,
      locale: locale,
      textScale: textScale,
    ),
  );
  await tester.pumpAndSettle();
  return s;
}

/// The current router location printed by a placeholder page.
String? shownRoute(WidgetTester tester) {
  final texts = find.textContaining('route:').evaluate();
  if (texts.isEmpty) return null;
  return (texts.first.widget as Text).data!.substring('route:'.length);
}

/// Lets a shown toast time out, so the next test starts without one.
Future<void> settleToasts(WidgetTester tester) async {
  await tester.pump(const Duration(seconds: 4));
  await tester.pumpAndSettle();
}

/// Taps [finder] and lets press feedback and the route settle.
Future<void> tapAndSettle(WidgetTester tester, Finder finder) async {
  await tester.tap(finder);
  await tester.pump(const Duration(milliseconds: 300));
  await tester.pumpAndSettle();
}

/// The four golden variants: (light|dark) × (ar|en).
const goldenVariants = [
  (brightness: Brightness.light, locale: 'ar', name: 'light_ar'),
  (brightness: Brightness.dark, locale: 'ar', name: 'dark_ar'),
  (brightness: Brightness.light, locale: 'en', name: 'light_en'),
  (brightness: Brightness.dark, locale: 'en', name: 'dark_en'),
];

/// A fixed "now" for schedule lines and times in goldens: Thursday 27 Nov 2026, 10:00.
final fixtureNow = DateTime(2026, 11, 27, 10);
