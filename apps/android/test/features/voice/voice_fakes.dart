// Fakes for the voice tests: a scripted API and a WebRTC transport that reports what the test
// tells it to.
import 'package:async_redux/async_redux.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/features/voice/voice_transport.dart';
import 'package:lonora/state/app_state.dart';

typedef Call = ({String method, String path, Object? body});

class FakeApi extends ApiClient {
  FakeApi() : super(userAgent: 'test');

  final calls = <Call>[];
  final Map<String, Object? Function(Object? body)> routes = {};

  void on(String route, Object? Function(Object? body) answer) =>
      routes[route] = answer;

  Future<dynamic> _answer(String method, String path, Object? body) async {
    calls.add((method: method, path: path, body: body));
    final handler = routes['$method $path'];
    if (handler == null) return <String, Object?>{};
    final value = handler(body);
    if (value is ApiError) throw value;
    return value;
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
  Future<dynamic> delete(String path, {Map<String, Object?>? query}) =>
      _answer('DELETE', path, null);
}

class FakeTransport implements VoiceTransport {
  FakeTransport(this.callbacks, this.api);

  final VoiceTransportCallbacks callbacks;
  final ApiClient api;
  bool connected = false;
  bool? muted;
  bool? speaker;
  bool closed = false;
  bool? finalized;
  String? incomingCallId;

  @override
  String get nonce => 'nonce-1';
  @override
  String? sessionId;

  @override
  Future<void> connect({
    required String agentId,
    required String threadId,
    String? incomingCallId,
  }) async {
    this.incomingCallId = incomingCallId;
    connected = true;
  }

  @override
  Future<void> setMuted(bool value) async => muted = value;
  @override
  Future<void> setSpeaker(bool on) async => speaker = on;

  @override
  Future<void> close({bool finalize = true}) async {
    if (closed) return;
    closed = true;
    finalized = finalize;
    if (finalize) await api.delete('/voice/sessions/s1');
    callbacks.onClosed();
  }
}

Store<AppState> voiceStore({bool signedIn = true}) => Store<AppState>(
  initialState: AppState(
    session: signedIn
        ? const SessionState(
            status: SessionStatus.signedIn,
            server: 'https://lonora.example.com',
            owner: Owner(id: 'owner-1', email: 'o@example.com'),
          )
        : const SessionState(status: SessionStatus.signedOut),
    shell: ShellState(
      agents: {
        'a-sara': Agent.fromJson({
          'id': 'a-sara',
          'name': 'Sara',
          'avatar': 'orb',
          'color': 'blue',
        }),
      },
      agentOrder: const ['a-sara'],
      loaded: true,
    ),
  ),
);
