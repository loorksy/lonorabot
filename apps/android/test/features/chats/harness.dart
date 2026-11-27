// Shared harness of the chats, groups, share and agents-list tests: real fonts and catalogs,
// a fake API recording calls, a store with a fixture owner snapshot, and an app shell with a
// small router (the other features' routes are placeholders that show their location).
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/agents/agents_screen.dart';
import 'package:lonora/features/chats/archived_screen.dart';
import 'package:lonora/features/chats/chat_text.dart';
import 'package:lonora/features/chats/chats_screen.dart';
import 'package:lonora/features/chats/chats_strings.dart';
import 'package:lonora/features/chats/search_screen.dart';
import 'package:lonora/features/groups/group_settings_screen.dart';
import 'package:lonora/features/groups/new_group_screen.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../design/fonts.dart';
import '../../design/harness.dart';

export '../../design/harness.dart' show goldenSize, setGoldenViewport;

/// One recorded request.
typedef Call = ({
  String method,
  String path,
  Object? body,
  Map<String, Object?>? query,
});

/// Answers requests from [handlers] (`'GET /agents'` → body) and records every call.
class FakeApi extends ApiClient {
  FakeApi() : super(userAgent: 'test') {
    configure(server: 'http://test', token: 'token');
  }

  final calls = <Call>[];
  final handlers =
      <String, Object? Function(Object? body, Map<String, Object?>? query)>{};

  Future<dynamic> _answer(
    String method,
    String path, {
    Object? body,
    Map<String, Object?>? query,
  }) async {
    calls.add((method: method, path: path, body: body, query: query));
    final handler = handlers['$method $path'];
    if (handler == null) {
      throw ApiError(status: 404, code: 'endpoint_not_found');
    }
    final out = handler(body, query);
    if (out is ApiError) throw out;
    return out;
  }

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

  List<Call> callsTo(String method, String path) =>
      calls.where((c) => c.method == method && c.path == path).toList();
}

class _NoSecureStore extends SecureStore {
  _NoSecureStore() : super(const FlutterSecureStorage());
}

late FakeApi fakeApi;

/// Fixed "now" of every fixture: Friday 27 November 2026, 12:00 local.
final fixtureNow = DateTime(2026, 11, 27, 12);

Future<void> setUpFeatureHarness() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  await loadAppFonts();
  await L10n.load();
  registerChatsStrings();
  chatClock = () => fixtureNow;
  SharedPreferences.setMockInitialValues({});
  final dir = await Directory.systemTemp.createTemp('lonora_chats_test');
  fakeApi = FakeApi();
  await registerServices(
    apiClient: fakeApi,
    secure: _NoSecureStore(),
    local: LocalStore.at(dir),
    prefs: await SharedPreferences.getInstance(),
    info: const AppInfo(
      version: '1.0.0',
      buildNumber: '1',
      packageName: 'ai.lonora.android',
    ),
  );
}

/// Resets the fake API between tests.
void resetFakeApi() {
  fakeApi.calls.clear();
  fakeApi.handlers.clear();
}

String _iso(DateTime d) => d.toUtc().toIso8601String();

Json agentJson(
  String id,
  String name, {
  String role = 'general',
  String title = '',
  String avatar = 'orb',
  String? color,
  bool paused = false,
}) => {
  'id': id,
  'name': name,
  'title': title,
  'description': '',
  'avatar': avatar,
  'color': color,
  'paused': paused,
  'role': role,
  'trading_mode': 'ask',
};

Json inboxJson(
  String threadId, {
  String? agentId,
  String? groupId,
  required String content,
  required DateTime at,
  String role = 'assistant',
  String? speaker,
  int seq = 5,
  int unread = 0,
  bool markedUnread = false,
  bool muted = false,
  bool archived = false,
  bool favourite = false,
  int? pinned,
}) => {
  'thread_id': threadId,
  'agent_id': agentId,
  'group_id': groupId,
  'last_message': {
    'id': 'm-$threadId',
    'role': role,
    'agent_id': speaker ?? agentId,
    'content': content,
    'preview': content,
    'kind': 'text',
    'seq': seq,
    'created_at': _iso(at),
    'attachments': {'count': 0, 'kinds': []},
    'consumed': role == 'user' ? true : null,
  },
  'last_activity_at': _iso(at),
  'unread_count': unread,
  'last_read_seq': unread > 0 ? seq - unread : seq,
  'marked_unread': markedUnread,
  'muted': muted,
  'archived': archived,
  'favourite': favourite,
  'pinned_order': pinned,
  'hidden_before_seq': 0,
};

Json groupJson(
  String id,
  String name,
  List<String> members, {
  String? thread,
  String? lead,
}) => {
  'id': id,
  'version': 2,
  'payload': {
    'name': name,
    'member_ids': members,
    'participation': 'mentions_or_lead',
    'purpose': '',
    'lead_agent_id': ?lead,
  },
  'state': {'thread_id': ?thread},
};

/// The fixture owner: Lonora (personal) and five agents, two groups, a pinned chat, unread
/// counts, a dot, a muted chat, one archived chat, an agent working and a paused agent.
final fixtureAgents = [
  agentJson('a-lonora', 'Lonora', role: 'personal'),
  agentJson(
    'a-gold',
    'Gold desk',
    title: 'XAUUSD analyst',
    avatar: 'face-smile',
    color: '#f5a524',
  ),
  agentJson(
    'a-news',
    'Morning news',
    title: 'Market brief',
    avatar: 'face-wink',
    color: '#3e97f6',
  ),
  agentJson(
    'a-fx',
    'FX watcher',
    title: 'EURUSD watch',
    color: '#f75555',
    paused: true,
  ),
  agentJson(
    'a-research',
    'Research',
    title: 'Reports and filings',
    avatar: 'face-curious',
    color: '#8b5cf6',
  ),
  agentJson('a-old', 'Old helper', title: 'Archived helper', color: '#8c8c8c'),
];

final fixtureGroups = [
  groupJson(
    'g-desk',
    'Trading desk',
    ['a-gold', 'a-fx', 'a-news'],
    thread: 't-desk',
    lead: 'a-gold',
  ),
  groupJson('g-reading', 'Reading club', [
    'a-research',
    'a-news',
  ], thread: 't-reading'),
];

List<Json> fixtureInbox() {
  final today = DateTime(2026, 11, 27);
  return [
    inboxJson(
      't-lonora',
      agentId: 'a-lonora',
      content: 'I created **Gold desk** to watch XAUUSD for you.',
      at: today.add(const Duration(hours: 10, minutes: 12)),
      pinned: 0,
    ),
    inboxJson(
      't-gold',
      agentId: 'a-gold',
      content: 'Gold is +1.2% since the open; the plan holds.',
      at: today.add(const Duration(hours: 11, minutes: 40)),
      unread: 3,
    ),
    inboxJson(
      't-news',
      agentId: 'a-news',
      content: 'Your morning brief is ready.',
      at: today.subtract(const Duration(days: 1, hours: -8)),
      markedUnread: true,
    ),
    inboxJson(
      't-desk',
      groupId: 'g-desk',
      speaker: 'a-news',
      content: 'Rates decision at 14:00 GMT.',
      at: today.subtract(const Duration(days: 2, hours: -9)),
      unread: 1,
      muted: true,
    ),
    inboxJson(
      't-research',
      agentId: 'a-research',
      role: 'user',
      content: 'Summarise the filing please',
      at: today.subtract(const Duration(days: 9)),
    ),
    inboxJson(
      't-old',
      agentId: 'a-old',
      content: 'Done.',
      at: today.subtract(const Duration(days: 30)),
      archived: true,
      unread: 2,
    ),
  ];
}

AppState fixtureState({
  bool loaded = true,
  List<Json>? agents,
  List<Json>? groups,
  List<Json>? inbox,
  List<Json> chatLists = const [],
  bool offline = false,
  String? lastError,
  bool working = true,
}) {
  final agentList = (agents ?? fixtureAgents).map(Agent.fromJson).toList();
  final groupList = (groups ?? fixtureGroups).map(Group.fromJson).toList();
  return AppState(
    session: const SessionState(
      status: SessionStatus.signedIn,
      server: 'http://test',
      owner: Owner(id: 'o1', email: 'owner@example.com'),
    ),
    shell: ShellState(
      agents: {for (final a in agentList) a.id: a},
      agentOrder: [for (final a in agentList) a.id],
      groups: {for (final g in groupList) g.id: g},
      inbox: (inbox ?? fixtureInbox()).map(InboxEntry.fromJson).toList(),
      chatLists: chatLists.map(ChatList.fromJson).toList(),
      keepArchived: true,
      runs: working
          ? [
              Run.fromJson({
                'id': 'r1',
                'thread_id': 't-research',
                'agent_id': 'a-research',
                'status': 'running',
              }),
            ]
          : const [],
      loaded: loaded,
      offline: offline,
      lastError: lastError,
    ),
  );
}

/// Where the placeholder routes print their location.
Widget _placeholder(GoRouterState s) =>
    Center(child: Text('route:${s.uri}', textDirection: TextDirection.ltr));

GoRouter testRouter(
  String initial, {
  GlobalKey<NavigatorState>? navigatorKey,
}) => GoRouter(
  navigatorKey: navigatorKey,
  initialLocation: initial,
  routes: [
    GoRoute(
      path: Routes.chats,
      builder: (_, _) => const ChatsScreen(),
      routes: [
        GoRoute(path: 'thread/:id', builder: (_, s) => _placeholder(s)),
        GoRoute(path: 'archived', builder: (_, _) => const ArchivedScreen()),
      ],
    ),
    GoRoute(path: Routes.search, builder: (_, _) => const SearchScreen()),
    GoRoute(path: Routes.agents, builder: (_, _) => const AgentsScreen()),
    GoRoute(
      path: '/groups/new',
      builder: (_, s) => NewGroupScreen(
        memberIds: (s.uri.queryParameters['members'] ?? '')
            .split(',')
            .where((e) => e.isNotEmpty)
            .toList(),
      ),
    ),
    GoRoute(
      path: '/groups/:id/settings',
      builder: (_, s) => GroupSettingsScreen(groupId: s.pathParameters['id']!),
    ),
    GoRoute(path: '/agent/:id', builder: (_, s) => _placeholder(s)),
    GoRoute(path: '/agent/:id/settings', builder: (_, s) => _placeholder(s)),
    GoRoute(path: Routes.tasks, builder: (_, s) => _placeholder(s)),
    GoRoute(path: '/files/:id', builder: (_, s) => _placeholder(s)),
    GoRoute(path: Routes.integrations, builder: (_, s) => _placeholder(s)),
  ],
);

/// The app around [router]: theme, forui, toaster, localisation (Arabic RTL or English), a 48 dp
/// status inset, animations off (static avatars and skeletons).
Widget featureApp({
  required Store<AppState> store,
  required RouterConfig<Object> router,
  Brightness brightness = Brightness.light,
  String locale = 'ar',
  Widget Function(Widget app)? wrap,
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
            child: FToaster(child: wrap == null ? child! : wrap(child!)),
          ),
        ),
      ),
    ),
  );
}

/// Lets a shown toast time out, so the next test's app starts without one.
Future<void> settleToasts(WidgetTester tester) async {
  await tester.pump(const Duration(seconds: 4));
  await tester.pumpAndSettle();
}

/// The current router location (placeholder routes print it).
String? shownRoute(WidgetTester tester) {
  final texts = find.textContaining('route:').evaluate();
  if (texts.isEmpty) return null;
  return (texts.first.widget as Text).data!.substring('route:'.length);
}
