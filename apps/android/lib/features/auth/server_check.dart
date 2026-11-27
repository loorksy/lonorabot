// Server address rules and the first-run probe (apps/mobile/lib/api.ts `normalizeServer`,
// `onboardingStatus`; apps/mobile/lib/connect-link.ts for the https rule).
import '../../app/services.dart';
import '../../core/api/api_client.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';

/// A server address checked as typed: [server] is the normalised address, or [error] is the
/// label key that says why it cannot be used.
typedef ServerAddress = ({String? server, String? error});

/// Normalises [input] (http/https only, no credentials, query or fragment, trailing `/api`
/// removed). Remote servers must use https; plain http is accepted only for local addresses
/// (localhost, *.local, 10/8, 172.16/12, 192.168/16, 127/8, [::1]).
ServerAddress checkServerAddress(String input) {
  final server = normalizeServerUrl(input);
  if (server == null) return (server: null, error: 'invalid_server');
  final uri = Uri.parse(server);
  if (uri.scheme != 'https' && !isLocalHost(uri.host)) {
    return (server: null, error: 'auth_httpsRequired');
  }
  return (server: server, error: null);
}

/// Whether two addresses name the same server (apps/mobile/lib/connect-link.ts `sameServer`).
bool sameServer(String a, String b) {
  final x = normalizeServerUrl(a);
  return x != null && x == normalizeServerUrl(b);
}

/// The host shown to the owner («lonora.example.com», «192.168.1.4:8840»).
String serverHost(String server) {
  final uri = Uri.tryParse(server);
  if (uri == null || uri.host.isEmpty) return server;
  final host = uri.host.contains(':') ? '[${uri.host}]' : uri.host;
  final port = uri.hasPort ? ':${uri.port}' : '';
  final path = uri.path == '/' ? '' : uri.path;
  return '$host$port$path';
}

/// `GET {server}/api/onboarding` without touching the session: true when the server already
/// has its owner (sign in), false for a first run (owner setup). Only a boolean
/// `owner_initialized` counts; any other answer is not a Lonora server (`auth_notLonora`).
Future<bool> probeOwnerInitialized(String server) async {
  final Object? answer;
  try {
    answer = await api.probe(server, '/onboarding');
  } on ApiError catch (e) {
    // A server without the route is not Lonora; Lonora's own failures keep their code.
    if (e.isNotFound) throw ApiError(status: 404, code: 'auth_notLonora');
    rethrow;
  }
  final data = asJson(answer);
  final initialized = data['owner_initialized'];
  if (initialized is! bool) {
    throw ApiError(status: 200, code: 'auth_notLonora');
  }
  return initialized;
}
