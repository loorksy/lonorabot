// Test harness for the conversation: the app's wrappers (store, localization, Lonora theme,
// toaster) around a screen, the floating tab bar as the home shell draws it, a fake API
// client that records requests, and conversation fixtures.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:dio/dio.dart' show CancelToken;
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:forui/forui.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/reply_stream.dart';

import '../../design/harness.dart';

/// Records every request and answers with [answers] (keyed `METHOD path`), else `{}`.
class FakeApi extends ApiClient {
  FakeApi() : super(userAgent: 'Lonora-Android/test');

  final List<({String method, String path, Object? body})> calls = [];
  final Map<String, Object? Function(Object? body)> answers = {};

  Future<dynamic> _answer(String method, String path, Object? body) async {
    calls.add((method: method, path: path, body: body));
    final handler = answers['$method $path'];
    return handler == null ? <String, dynamic>{} : handler(body);
  }

  @override
  Future<dynamic> get(
    String path, {
    Map<String, Object?>? query,
    Duration? timeout,
  }) => _answer('GET', path, query);

  @override
  Future<dynamic> post(String path, [Object? body]) =>
      _answer('POST', path, body);

  @override
  Future<dynamic> put(String path, [Object? body]) =>
      _answer('PUT', path, body);

  @override
  Future<dynamic> delete(String path, {Map<String, Object?>? query}) =>
      _answer('DELETE', path, query);

  /// Uploads in flight: each waits until the test completes its [FakeUpload.done].
  final List<FakeUpload> uploads = [];

  @override
  Future<dynamic> upload(
    String path, {
    required String filePath,
    required String fileName,
    String? mimeType,
    Map<String, String> fields = const {},
    void Function(int sent, int total)? onProgress,
    CancelToken? cancelToken,
  }) {
    calls.add((method: 'UPLOAD', path: path, body: fields));
    final upload = FakeUpload(fileName, fields, onProgress, cancelToken);
    uploads.add(upload);
    return upload.done.future;
  }
}

class FakeUpload {
  FakeUpload(this.fileName, this.fields, this.onProgress, this.token);
  final String fileName;
  final Map<String, String> fields;
  final void Function(int sent, int total)? onProgress;
  final CancelToken? token;
  final Completer<Object?> done = Completer();
}

FakeApi registerFakeApi() {
  final fake = FakeApi();
  if (sl.isRegistered<ApiClient>()) sl.unregister<ApiClient>();
  sl.registerSingleton<ApiClient>(fake);
  return fake;
}

const _tabs = [
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
];

/// The app around [child]: store, `ar`/`en` localization (RTL for Arabic), Lonora theme,
/// toaster, simulated status bar, reduced motion (static avatar and typing frames), and the
/// floating tab bar over the screen as in the home shell.
Widget conversationApp({
  required Store<AppState> store,
  required L10n l10n,
  required Widget child,
  Brightness brightness = Brightness.light,
  String locale = 'en',
  EdgeInsets padding = const EdgeInsets.only(top: 48),
  double textScale = 1,
}) {
  final palette = brightness == Brightness.dark
      ? LnPalette.dark
      : LnPalette.light;
  l10n.setLocale(Locale(locale));
  return StoreProvider<AppState>(
    store: store,
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      locale: Locale(locale),
      supportedLocales: L10n.supportedLocales,
      localizationsDelegates: [
        l10n.delegate,
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
      builder: (context, app) => MediaQuery(
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
            child: FToaster(child: app!),
          ),
        ),
      ),
      home: Builder(
        builder: (context) => ColoredBox(
          color: context.ln.colors.bg,
          child: Stack(
            children: [
              Positioned.fill(child: child),
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: FloatingTabBar(
                  items: _tabs,
                  selectedIndex: 0,
                  onSelect: (_) {},
                  actionIcon: const LnGlyph(LnGlyphs.attention),
                  actionLabel: 'Attention',
                  onAction: () {},
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

const threadId = 'thread-1';
const agentId = 'agent-1';

/// Fixed local times so the time separators read the same on every run.
DateTime at(int minute) => DateTime(2025, 3, 14, 9, minute);
String iso(DateTime d) => d.toIso8601String();

Agent fixtureAgent({bool paused = false, String name = 'Atlas'}) =>
    Agent.fromJson({
      'id': agentId,
      'name': name,
      'avatar': 'orb',
      'color': 'blue',
      'paused': paused,
    });

Json messageJson({
  required String id,
  required int seq,
  required String role,
  required String content,
  required DateTime createdAt,
  String? replyTo,
  List<Json> reactions = const [],
  String? clientNonce,
  List<String> attachments = const [],
  String? supersededBy,
  String? suggestedReply,
}) => {
  'id': id,
  'thread_id': threadId,
  'role': role,
  'agent_id': role == 'assistant' ? agentId : null,
  'seq': seq,
  'content': content,
  'reply_to': replyTo,
  'attachment_ids': attachments,
  'created_at': iso(createdAt),
  'client_nonce': clientNonce,
  'reactions': reactions,
  'superseded_by': supersededBy,
  'suggested_reply': suggestedReply,
};

Message message(
  String id,
  int seq,
  String role,
  String content,
  DateTime createdAt, {
  String? replyTo,
  List<Json> reactions = const [],
  List<String> attachments = const [],
  String? supersededBy,
  String? suggestedReply,
}) => Message.fromJson(
  messageJson(
    id: id,
    seq: seq,
    role: role,
    content: content,
    createdAt: createdAt,
    replyTo: replyTo,
    reactions: reactions,
    attachments: attachments,
    supersededBy: supersededBy,
    suggestedReply: suggestedReply,
  ),
);

Run run(
  String id,
  String status, {
  int? inputSeq,
  DateTime? createdAt,
  List<Json> inputRequests = const [],
  String? errorCode,
  Json? failure,
  String trigger = 'user',
  bool background = false,
}) => Run.fromJson({
  'id': id,
  'thread_id': threadId,
  'agent_id': agentId,
  'status': status,
  'trigger': trigger,
  'background': background,
  'input_seq': inputSeq,
  'error_code': errorCode,
  'failure': failure,
  'input_requests': inputRequests,
  'created_at': iso(createdAt ?? at(10)),
  'updated_at': iso(createdAt ?? at(10)),
});

LiveReplyStream liveStream(String runId, String text, {int inputSeq = 3}) =>
    LiveReplyStream(
      runId: runId,
      threadId: threadId,
      agentId: agentId,
      turnId: 'turn-1',
      fence: 1,
      generation: 1,
      sequence: 3,
      text: text,
      truncated: false,
      phase: 'streaming',
      cursor: 0,
      gap: false,
      chunks: const [],
      inputSeq: inputSeq,
    );

AppState conversationState({
  List<Message> messages = const [],
  Map<String, Run> runs = const {},
  Map<String, LiveReplyStream> streams = const {},
  List<OutgoingMessage> outbox = const [],
  bool loaded = true,
  String? error,
  Agent? agent,
  bool webSearch = false,
  int? focusSeq,
}) {
  final a = agent ?? fixtureAgent();
  return AppState(
    shell: ShellState(agents: {a.id: a}, agentOrder: [a.id], loaded: true),
    outbox: outbox,
    connection: StreamStatus.connected,
    threads: {
      threadId: ThreadState(
        threadId: threadId,
        thread: Thread.fromJson({
          'id': threadId,
          'agent_id': a.id,
          'title': '',
          'options': {'web_search': webSearch},
        }),
        messages: messages,
        runs: runs,
        streams: streams,
        loaded: loaded,
        error: error,
        focusSeq: focusSeq,
      ),
    },
  );
}

/// Local test strings per language.
String pick(String locale, String en, String ar) => locale == 'ar' ? ar : en;

/// [state] with a signed-in owner (the screen loads, marks read and sends).
AppState signedIn(AppState state) => state.copyWith(
  session: const SessionState(
    status: SessionStatus.signedIn,
    server: 'http://127.0.0.1:1',
    owner: Owner(id: 'owner-1', email: 'owner@example.com'),
  ),
);

/// Answers the conversation's snapshot reads with [state]'s thread, so a signed-in screen
/// loads what the test set up.
void serveThread(FakeApi fake, AppState state) {
  final t = state.thread(threadId);
  fake.answers['GET /threads/$threadId'] = (_) =>
      t.thread?.raw ?? <String, Object?>{'id': threadId};
  fake.answers['GET /threads/$threadId/messages'] = (_) => [
    for (final m in t.messages) m.raw,
  ];
  fake.answers['GET /runs'] = (_) => [for (final r in t.runs.values) r.raw];
}
