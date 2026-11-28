// Shared harness of the market, charts, attention and files tests (work package F): real fonts
// and catalogs, a fake API that records every call (bytes and downloads included), a signed-in
// store with fixture agents, and a router whose other destinations are placeholders printing
// their location. Animations are off.
import 'dart:async';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:dio/dio.dart' show CancelToken;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/app/app_strings.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../design/fonts.dart';
import '../../design/harness.dart';

export '../../design/harness.dart' show goldenSize, withRealShadows;

typedef Call = ({
  String method,
  String path,
  Object? body,
  Map<String, Object?>? query,
});

typedef Handler = Object? Function(Object? body, Map<String, Object?>? query);

/// Answers requests from [handlers] (`'GET /charts'` → body; a handler may throw an
/// [ApiError]) and records every call. Unknown reads answer `[]` for list routes is not
/// guessed: they answer `{}`. [files] answers `bytes`/`downloadTo` by path.
class FakeApi extends ApiClient {
  FakeApi() : super(userAgent: 'test') {
    configure(server: 'http://test', token: 'token');
  }

  final calls = <Call>[];
  final handlers = <String, Handler>{};
  final files = <String, Uint8List>{};

  void on(String route, Handler handler) => handlers[route] = handler;

  Future<dynamic> _answer(
    String method,
    String path, {
    Object? body,
    Map<String, Object?>? query,
  }) async {
    calls.add((method: method, path: path, body: body, query: query));
    final handler = handlers['$method $path'];
    if (handler == null) {
      // An order is never answered by default: only a test's own handler may.
      if (path == '/trading/execute') {
        throw StateError('unexpected $method $path');
      }
      return <String, Object?>{};
    }
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
  Future<dynamic> postWithin(String path, Object body, Duration timeout) =>
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

  @override
  Future<Uint8List> bytes(
    String path, {
    Map<String, Object?>? query,
    void Function(int, int)? onProgress,
  }) async {
    calls.add((method: 'BYTES', path: path, body: null, query: query));
    final data = files[path];
    if (data == null) {
      throw ApiError(status: 404, code: 'artifact_file_missing');
    }
    return data;
  }

  @override
  Future<void> downloadTo(
    String path,
    String savePath, {
    Map<String, Object?>? query,
    void Function(int, int)? onProgress,
  }) async {
    calls.add((method: 'DOWNLOAD', path: path, body: savePath, query: query));
    final data = files[path];
    if (data == null) {
      throw ApiError(status: 404, code: 'artifact_file_missing');
    }
    await File(savePath).writeAsBytes(data);
  }

  @override
  Future<dynamic> upload(
    String path, {
    required String filePath,
    required String fileName,
    String? mimeType,
    Map<String, String> fields = const {},
    void Function(int sent, int total)? onProgress,
    CancelToken? cancelToken,
  }) => _answer(
    'UPLOAD',
    path,
    body: {'file': fileName, 'mime': mimeType, ...fields},
  );
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

/// The owner event feed of a test: [emit] hands an event to every screen listening.
class FakeRealtime extends RealtimeController {
  FakeRealtime(super.store);

  final _feed = StreamController<LonoraEvent>.broadcast();
  int _cursor = 0;

  @override
  Stream<LonoraEvent> get events => _feed.stream;

  void emit(String kind, [Json payload = const {}]) =>
      _feed.add(LonoraEvent(cursor: ++_cursor, kind: kind, payload: payload));
}

late FakeRealtime fakeRealtime;

Future<void> setUpWpf() async {
  await loadAppFonts();
  await L10n.load();
  registerAppStrings();
}

/// [api] replaces the lenient [FakeApi] (the order tests answer unknown routes with an error).
Future<void> resetWpf({FakeApi? api}) async {
  SharedPreferences.setMockInitialValues({});
  fakeApi = api ?? FakeApi();
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

final fixtureAgents = <Json>[
  {
    'id': 'a-lonora',
    'name': 'Lonora',
    'avatar': 'orb',
    'color': '#8B5CF6',
    'role': 'personal',
    'trading_mode': 'ask',
  },
  {
    'id': 'a-gold',
    'name': 'Gold desk',
    'avatar': 'face-focused',
    'color': '#06B6D4',
    'role': 'general',
    'scope_mode': 'fixed_market',
    'trading_account_id': 'acct-1',
    'trading_symbol': 'XAUUSD',
    'trading_mode': 'ask',
  },
  {
    'id': 'a-research',
    'name': 'محلل الأبحاث',
    'avatar': 'face-thoughtful',
    'color': '#F97316',
    'role': 'general',
    'scope_mode': 'flexible',
  },
];

Store<AppState> wpfStore({
  String locale = 'ar',
  List<Json>? agents,
  List<Json> inbox = const [],
  List<Json> attention = const [],
  List<Json> attentionView = const [],
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
        attention: attention,
        attentionView: attentionView,
        attentionUnseen: attentionView.where((r) => r['seen'] != true).length,
        loaded: true,
      ),
    ),
  );
}

/// [home] at `/home`; every other location renders `route:<location>`.
GoRouter wpfRouter(
  Widget home, {
  Map<String, Widget Function(GoRouterState)> pages = const {},
}) {
  Widget stub(BuildContext _, GoRouterState s) {
    for (final e in pages.entries) {
      if (s.uri.path == e.key) return e.value(s);
    }
    return Center(child: Text('route:${s.uri}'));
  }

  return GoRouter(
    initialLocation: '/home',
    routes: [
      GoRoute(path: '/home', builder: (_, _) => home),
      GoRoute(path: '/chats/thread/:id', builder: stub),
      GoRoute(path: '/files', builder: stub),
      GoRoute(path: '/files/:id', builder: stub),
      GoRoute(path: '/files/:id/image', builder: stub),
      GoRoute(path: '/charts', builder: stub),
      GoRoute(path: '/settings/integrations', builder: stub),
      GoRoute(path: '/settings/recovery', builder: stub),
      GoRoute(path: '/agent/:id', builder: stub),
      GoRoute(path: '/market', builder: stub),
      GoRoute(path: '/me', builder: stub),
      GoRoute(path: '/chats', builder: stub),
    ],
  );
}

Widget wpfApp({
  required Store<AppState> store,
  required GoRouter router,
  Brightness brightness = Brightness.light,
  String locale = 'ar',
  double textScale = 1,
  EdgeInsets padding = const EdgeInsets.only(top: 48, bottom: 24),
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
          padding: padding,
          viewPadding: padding,
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
Future<Store<AppState>> pumpWpf(
  WidgetTester tester,
  Widget screen, {
  Brightness brightness = Brightness.light,
  String locale = 'ar',
  Store<AppState>? store,
  double textScale = 1,
  Map<String, Widget Function(GoRouterState)> pages = const {},
  bool settle = true,
}) async {
  setGoldenViewport(tester);
  final s = store ?? wpfStore(locale: locale);
  realtime = fakeRealtime = FakeRealtime(s);
  await tester.pumpWidget(
    wpfApp(
      store: s,
      router: wpfRouter(screen, pages: pages),
      brightness: brightness,
      locale: locale,
      textScale: textScale,
    ),
  );
  if (settle) {
    await tester.pumpAndSettle();
  } else {
    // A spinner never settles: let the reads finish instead.
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
  }
  return s;
}

/// The current location printed by a placeholder page.
String? shownRoute(WidgetTester tester) {
  final texts = find.textContaining('route:').evaluate();
  if (texts.isEmpty) return null;
  return (texts.first.widget as Text).data!.substring('route:'.length);
}

Future<void> settleToasts(WidgetTester tester) async {
  await tester.pump(const Duration(seconds: 4));
  await tester.pumpAndSettle();
}

Future<void> tapAndSettle(WidgetTester tester, Finder finder) async {
  await tester.tap(finder);
  await tester.pump(const Duration(milliseconds: 300));
  await tester.pumpAndSettle();
}

/// Lets real IO finish (file writes, image decoding): the test clock does not run it, and
/// each step of a chain of IO calls needs a real turn then a pump. Runs [rounds] turns, or
/// until [until] holds.
Future<void> settleIo(
  WidgetTester tester, {
  bool Function()? until,
  int rounds = 8,
}) async {
  for (var i = 0; i < (until == null ? rounds : 400); i++) {
    if (until?.call() ?? false) break;
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 5)),
    );
    await tester.pump();
  }
  await tester.pumpAndSettle();
}

/// Scrolls the page's vertical list until [finder] is visible.
Future<void> scrollTo(
  WidgetTester tester,
  Finder finder, {
  double delta = 200,
}) => tester.scrollUntilVisible(
  finder,
  delta,
  scrollable: find
      .byWidgetPredicate(
        (w) => w is Scrollable && w.axisDirection == AxisDirection.down,
      )
      .first,
);

/// Unmounts the screen so its timers stop before the test ends.
Future<void> unmount(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(seconds: 1));
}

/// A tab-root screen under the floating tab bar, as HomeShell shows it.
class TabFrame extends StatelessWidget {
  const TabFrame({super.key, required this.child, this.index = 1});

  final Widget child;

  /// Selected tab (0 chats, 1 market, 2 me); -1 selects the attention circle.
  final int index;

  @override
  Widget build(BuildContext context) => Stack(
    children: [
      Positioned.fill(child: child),
      Positioned(
        left: 0,
        right: 0,
        bottom: 0,
        child: FloatingTabBar(
          selectedIndex: index,
          onSelect: (_) {},
          items: const [
            LnTabItem(
              icon: LnGlyph(LnGlyphs.chats),
              selectedIcon: LnGlyph(LnGlyphs.chatsFilled),
              label: 'chats',
            ),
            LnTabItem(
              icon: LnGlyph(LnGlyphs.market),
              selectedIcon: LnGlyph(LnGlyphs.marketFilled),
              label: 'market',
            ),
            LnTabItem(
              icon: LnGlyph(LnGlyphs.me),
              selectedIcon: LnGlyph(LnGlyphs.meFilled),
              label: 'me',
            ),
          ],
          actionIcon: const LnGlyph(LnGlyphs.attention),
          actionSelectedIcon: const LnGlyph(LnGlyphs.attentionFilled),
          actionLabel: 'attention',
          actionSelected: index == -1,
          onAction: () {},
        ),
      ),
    ],
  );
}

const goldenVariants = [
  (brightness: Brightness.light, locale: 'ar', name: 'light_ar'),
  (brightness: Brightness.dark, locale: 'ar', name: 'dark_ar'),
  (brightness: Brightness.light, locale: 'en', name: 'light_en'),
  (brightness: Brightness.dark, locale: 'en', name: 'dark_en'),
];
