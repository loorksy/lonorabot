import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';

import '../json.dart';
import 'lonora_event.dart';

/// The owner's live event feed over `wss://<server>/api/ws/events`.
///
/// Protocol (docs/android/analysis/lonora-api-contract.md §4.2, apps/mobile/lib/events.ts):
/// - send `{token, cursor, live}` within 10 s; first connect uses `live: true, cursor: 0`,
///   reconnects send the last consumed cursor without `live`;
/// - the server answers `{type: ready, cursor}`; after every ready the app refetches its
///   snapshots (closes the admission gap);
/// - events arrive one per frame; duplicates (`cursor <= last`) are dropped; `{type: ping}`
///   arrives every 15 s; 45 s of silence replaces the socket;
/// - close code 1008 means the token was rejected (revoked/expired).
class EventStream {
  EventStream({required this.onEvent, required this.onReady, this.onRejected});

  /// Handles one event; the cursor advances only after it returns.
  final FutureOr<void> Function(LonoraEvent event) onEvent;

  /// Called after every accepted `ready` (first connect and every reconnect).
  final FutureOr<void> Function() onReady;

  /// The server closed with 1008 (token no longer valid).
  final void Function()? onRejected;

  final ValueNotifier<StreamStatus> status = ValueNotifier(StreamStatus.idle);

  static const readyTimeout = Duration(seconds: 10);
  static const idleTimeout = Duration(seconds: 45);
  static const baseReconnectDelay = Duration(milliseconds: 1500);

  Uri? _uri;
  String? _token;
  int _cursor = 0;
  bool _everReady = false;
  bool _running = false;
  int _attempt = 0;
  int _epoch = 0;

  WebSocket? _socket;
  StreamSubscription<dynamic>? _sub;
  Timer? _watchdog;
  Timer? _retry;
  Future<void> _chain = Future<void>.value();

  int get cursor => _cursor;

  /// Starts (or restarts for a new session) the feed.
  void start(Uri uri, String token) {
    final changed = uri != _uri || token != _token;
    _uri = uri;
    _token = token;
    if (changed) {
      _cursor = 0;
      _everReady = false;
    }
    _running = true;
    _reconnectNow();
  }

  /// Closes the socket and stops reconnecting (background, sign-out).
  void pause() {
    _running = false;
    _teardown();
    status.value = StreamStatus.idle;
  }

  /// Resumes from the last consumed cursor (foreground, network back).
  void resume() {
    if (_uri == null || _token == null) return;
    _running = true;
    _reconnectNow();
  }

  void stop() {
    pause();
    _uri = null;
    _token = null;
    _cursor = 0;
    _everReady = false;
  }

  void _reconnectNow() {
    _attempt = 0;
    _teardown();
    unawaited(_connect());
  }

  Future<void> _connect() async {
    final uri = _uri;
    final token = _token;
    if (!_running || uri == null || token == null) return;
    final epoch = ++_epoch;
    status.value = _everReady
        ? StreamStatus.reconnecting
        : StreamStatus.connecting;
    try {
      final socket = await WebSocket.connect(uri.toString())
          .timeout(readyTimeout);
      if (epoch != _epoch || !_running) {
        unawaited(socket.close(1000));
        return;
      }
      _socket = socket;
      final hello = <String, Object>{'token': token, 'cursor': _cursor};
      if (_cursor == 0) hello['live'] = true;
      socket.add(jsonEncode(hello));
      _arm(readyTimeout, epoch);
      var ready = false;
      _sub = socket.listen(
        (dynamic frame) {
          if (epoch != _epoch) return;
          _arm(idleTimeout, epoch);
          Json data;
          try {
            data = asJson(jsonDecode(frame as String));
          } catch (_) {
            // Malformed frame: resume from the last consumed cursor on a fresh socket.
            _scheduleReconnect(epoch);
            return;
          }
          final type = data['type'];
          if (type == 'ping') return;
          if (type == 'ready') {
            final readyCursor = asInt(data['cursor']) ?? 0;
            if (readyCursor < _cursor) {
              _scheduleReconnect(epoch);
              return;
            }
            ready = true;
            _everReady = true;
            _attempt = 0;
            _cursor = readyCursor;
            status.value = StreamStatus.connected;
            _enqueue(() async => onReady());
            return;
          }
          if (!ready) return;
          final event = LonoraEvent.fromJson(data);
          if (event == null) return;
          _enqueue(() async {
            if (event.cursor <= _cursor) return;
            try {
              await onEvent(event);
            } catch (error, stack) {
              FlutterError.reportError(
                FlutterErrorDetails(
                  exception: error,
                  stack: stack,
                  library: 'lonora realtime',
                ),
              );
            }
            if (event.cursor > _cursor) _cursor = event.cursor;
          });
        },
        onError: (Object _) => _scheduleReconnect(epoch),
        onDone: () {
          if (epoch != _epoch) return;
          if (socket.closeCode == 1008) {
            _running = false;
            status.value = StreamStatus.offline;
            onRejected?.call();
            return;
          }
          _scheduleReconnect(epoch);
        },
        cancelOnError: true,
      );
    } catch (_) {
      _scheduleReconnect(epoch);
    }
  }

  void _enqueue(Future<void> Function() task) {
    _chain = _chain.then((_) => task()).catchError((Object _) {});
  }

  void _arm(Duration timeout, int epoch) {
    _watchdog?.cancel();
    _watchdog = Timer(timeout, () => _scheduleReconnect(epoch));
  }

  void _scheduleReconnect(int epoch) {
    if (epoch != _epoch) return;
    _teardown();
    if (!_running) return;
    status.value = StreamStatus.reconnecting;
    final factor = pow(2, min(_attempt, 3)).toInt();
    _attempt++;
    final delay =
        baseReconnectDelay * factor +
        Duration(milliseconds: Random().nextInt(400));
    _retry = Timer(delay, () => unawaited(_connect()));
  }

  void _teardown() {
    _epoch++;
    _watchdog?.cancel();
    _retry?.cancel();
    final sub = _sub;
    final socket = _socket;
    _sub = null;
    _socket = null;
    unawaited(sub?.cancel());
    unawaited(socket?.close(1000));
  }

  void dispose() {
    stop();
    status.dispose();
  }
}
