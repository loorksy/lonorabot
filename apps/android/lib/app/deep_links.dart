import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:async_redux/async_redux.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';

import '../core/api/api_client.dart';
import '../core/json.dart';
import '../state/app_state.dart';
import 'routes.dart';

/// Content shared into Lonora from another app ("Send to Lonora"). The chats feature shows a
/// conversation picker while this is set; once a conversation is picked ([targetThreadId]),
/// that conversation's composer consumes it.
class SharedPayload {
  const SharedPayload({this.text, this.files = const [], this.targetThreadId});
  final String? text;
  final List<SharedFile> files;

  /// The conversation the owner picked; null while the picker is still to be shown.
  final String? targetThreadId;

  SharedPayload withTarget(String threadId) =>
      SharedPayload(text: text, files: files, targetThreadId: threadId);

  static SharedPayload? fromChannel(Object? value) {
    final j = asJson(value);
    if (j.isEmpty) return null;
    final files = asJsonList(j['files'])
        .map(
          (f) => SharedFile(
            path: asStr(f['path']),
            name: asStr(f['name'], 'file'),
            mimeType: asString(f['mimeType']),
            size: asInt(f['size']) ?? 0,
          ),
        )
        .where((f) => f.path.isNotEmpty)
        .toList();
    final text = asString(j['text']);
    if ((text == null || text.isEmpty) && files.isEmpty) return null;
    return SharedPayload(text: text, files: files);
  }
}

class SharedFile {
  const SharedFile({
    required this.path,
    required this.name,
    this.mimeType,
    this.size = 0,
  });
  final String path;
  final String name;
  final String? mimeType;
  final int size;
}

/// Set by the share intake; cleared by whoever consumes it.
final ValueNotifier<SharedPayload?> pendingShare = ValueNotifier(null);

const _platform = MethodChannel('ai.lonora.android/platform');
const _shares = EventChannel('ai.lonora.android/shares');

/// `lonora://` links and shared content → router locations.
///
/// - `lonora://connect?server=https://…[&token=…]` → connect confirmation
/// - `lonora://thread/<id>[?around=<seq>]` → conversation (notification taps use the same)
/// - `lonora://agent/<id>` → agent profile
class DeepLinks {
  DeepLinks({required this.store, required this.router});

  final Store<AppState> store;
  final GoRouter router;
  final _appLinks = AppLinks();
  StreamSubscription<Uri>? _linkSub;
  StreamSubscription<dynamic>? _shareSub;
  StreamSubscription<AppState>? _sessionSub;
  String? _held;

  void start() {
    _linkSub = _appLinks.uriLinkStream.listen(open, onError: (Object _) {});
    _shareSub = _shares.receiveBroadcastStream().listen(
      (value) => _onShare(value),
      onError: (Object _) {},
    );
    _platform
        .invokeMethod<Object?>('takeInitialShare')
        .then(_onShare)
        .catchError((Object _) {});
  }

  void _onShare(Object? value) {
    final payload = SharedPayload.fromChannel(value);
    if (payload == null) return;
    pendingShare.value = payload;
    if (store.state.session.signedIn) router.go(Routes.chats);
  }

  void open(Uri uri) {
    final location = locationFor(uri);
    if (location == null) return;
    if (store.state.session.status != SessionStatus.unknown) {
      router.go(location);
      return;
    }
    // A cold start (the website's "Open in the app" launches Lonora): the link arrives while the
    // stored session is still being read, and until then the router shows the splash for every
    // location. The newest link is held and opened once the session is known.
    _held = location;
    _sessionSub ??= store.onChange.listen((state) {
      if (state.session.status == SessionStatus.unknown) return;
      _sessionSub?.cancel();
      _sessionSub = null;
      router.go(_held!);
    });
  }

  /// Pure mapping, unit-tested.
  static String? locationFor(Uri uri) {
    if (uri.scheme != 'lonora') return null;
    final host = uri.host;
    final segments = uri.pathSegments.where((s) => s.isNotEmpty).toList();
    switch (host) {
      case 'connect':
        final server = normalizeServerUrl(uri.queryParameters['server'] ?? '');
        if (server == null) return Routes.connect;
        final parsed = Uri.parse(server);
        if (parsed.scheme != 'https' && !isLocalHost(parsed.host)) {
          return Routes.connect;
        }
        final token = uri.queryParameters['token'];
        final validToken =
            token != null && RegExp(r'^[A-Za-z0-9_-]{20,128}$').hasMatch(token)
            ? token
            : null;
        return Uri(
          path: Routes.connect,
          queryParameters: {'server': server, 'token': ?validToken},
        ).toString();
      case 'thread':
        if (segments.isEmpty) return Routes.chats;
        return Routes.thread(
          segments.first,
          around: int.tryParse(uri.queryParameters['around'] ?? ''),
        );
      case 'agent':
        return segments.isEmpty ? Routes.agents : Routes.agent(segments.first);
      case 'chats':
        return Routes.chats;
      default:
        return null;
    }
  }

  void dispose() {
    _linkSub?.cancel();
    _shareSub?.cancel();
    _sessionSub?.cancel();
  }
}
