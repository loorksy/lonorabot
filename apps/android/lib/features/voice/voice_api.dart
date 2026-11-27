// Voice calls with an agent (GPT-Live over WebRTC, `POST /voice/sessions`), as Lonora's Expo client
// runs them (apps/mobile/lib/voice-session.tsx). Controls: Speaker · Mute · End call · Minimize;
// Calling… → connected timer → Call ended; error states.
//
// A call starts only from an explicit owner tap (header, profile, call-back row, an answered
// incoming call); it is provisional speech and never approves, settles or switches anything.
// While it runs: the screen stays awake, the microphone is held by a visible foreground
// service with «End call» on its notification, and it ends on sign-out, on «End call» and
// when the app is closed. On the earpiece (speaker off) the proximity sensor turns the screen
// off at the ear, as Expo's `InCallManager.start({auto: true})` does, so a cheek cannot tap
// End or Mute.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../../app/services.dart';
import '../../core/api/api_client.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../l10n/l10n.dart';
import '../../platform/notifications/local_notifications.dart';
import '../../platform/platform_bridge.dart';
import '../../state/actions/thread_actions.dart';
import '../../state/app_state.dart';
import '../cards/cards_actions.dart'
    show SideKeys, mergeApproval, mergeSideRows, sideList;
import 'voice_strings.dart';
import 'voice_transport.dart';

enum CallPhase {
  idle,

  /// «Calling…»: checks, microphone, offer, `POST /voice/sessions`.
  calling,

  /// Media flows; the timer runs from [VoiceCallState.connectedAt].
  connected,

  /// «Ending call»: finalizing the server session.
  ending,

  /// «Call ended», shown briefly.
  ended,

  /// Could not start or dropped; [VoiceCallState.error] says why.
  failed,
}

@immutable
class VoiceCallState {
  const VoiceCallState({
    this.phase = CallPhase.idle,
    this.agentId,
    this.threadId,
    this.incomingCallId,
    this.startedAt,
    this.connectedAt,
    this.endedAfter,
    this.muted = false,
    this.speaker = true,
    this.minimized = false,
    this.speaking = false,
    this.level = 0,
    this.error,
    this.openSettings = false,
    this.approvalIds = const [],
  });

  final CallPhase phase;
  final String? agentId;
  final String? threadId;
  final String? incomingCallId;
  final DateTime? startedAt;
  final DateTime? connectedAt;

  /// The call's length when it ended (the «Call ended» line keeps it).
  final Duration? endedAfter;
  final bool muted;
  final bool speaker;
  final bool minimized;
  final bool speaking;
  final double level;

  /// An API error code (`voice_permission_denied`, `voice_transport_unconfigured`, …).
  final String? error;

  /// The microphone is refused for good: the error offers the phone's settings.
  final bool openSettings;

  /// Trade approvals of the call's conversation shown under the controls (newest last).
  final List<String> approvalIds;

  /// Connecting, ringing or connected (the public [VoiceCalls.active]).
  bool get active =>
      phase == CallPhase.calling ||
      phase == CallPhase.connected ||
      phase == CallPhase.ending;

  /// Something to show (an active call, its end, or an error).
  bool get visible => phase != CallPhase.idle;

  /// The failure happened before any session existed: «Retry» can start again.
  bool get canRetry => phase == CallPhase.failed && agentId != null;

  VoiceCallState copyWith({
    CallPhase? phase,
    Object? connectedAt = _k,
    Object? endedAfter = _k,
    bool? muted,
    bool? speaker,
    bool? minimized,
    bool? speaking,
    double? level,
    Object? error = _k,
    bool? openSettings,
    List<String>? approvalIds,
  }) => VoiceCallState(
    phase: phase ?? this.phase,
    agentId: agentId,
    threadId: threadId,
    incomingCallId: incomingCallId,
    startedAt: startedAt,
    connectedAt: identical(connectedAt, _k)
        ? this.connectedAt
        : connectedAt as DateTime?,
    endedAfter: identical(endedAfter, _k)
        ? this.endedAfter
        : endedAfter as Duration?,
    muted: muted ?? this.muted,
    speaker: speaker ?? this.speaker,
    minimized: minimized ?? this.minimized,
    speaking: speaking ?? this.speaking,
    level: level ?? this.level,
    error: identical(error, _k) ? this.error : error as String?,
    openSettings: openSettings ?? this.openSettings,
    approvalIds: approvalIds ?? this.approvalIds,
  );
}

const _k = Object();

enum MicPermission { granted, denied, permanentlyDenied }

Future<MicPermission> _requestMicrophone() async {
  try {
    final status = await Permission.microphone.request();
    if (status.isGranted || status.isLimited) return MicPermission.granted;
    return status.isPermanentlyDenied || status.isRestricted
        ? MicPermission.permanentlyDenied
        : MicPermission.denied;
  } catch (_) {
    return MicPermission.denied;
  }
}

/// The one call of the app.
class VoiceCallController extends ChangeNotifier {
  VoiceCallController({
    ApiClient Function()? api,
    Store<AppState> Function()? store,
    VoiceTransportFactory? transport,
    Future<MicPermission> Function()? microphone,
    Future<void> Function(bool on)? keepAwake,
    Future<void> Function(VoiceCallState state)? showOngoing,
    Future<void> Function()? hideOngoing,
    Future<void> Function(bool on)? proximity,
    DateTime Function()? clock,
    this.endedLinger = const Duration(milliseconds: 1600),
    this.approvalsEvery = const Duration(seconds: 2),
  }) : _api = api ?? (() => sl<ApiClient>()),
       _store = store ?? (() => appStore),
       _transport = transport ?? WebRtcVoiceTransport.new,
       _microphone = microphone ?? _requestMicrophone,
       _keepAwake = keepAwake ?? _wakelock,
       _showOngoing = showOngoing ?? _ongoingNotification,
       _hideOngoing = hideOngoing ?? LnNotifications.stopCall,
       _proximity = proximity ?? PlatformBridge.proximityScreenOff,
       _clock = clock ?? DateTime.now;

  final ApiClient Function() _api;
  final Store<AppState> Function() _store;
  final VoiceTransportFactory _transport;
  final Future<MicPermission> Function() _microphone;
  final Future<void> Function(bool on) _keepAwake;
  final Future<void> Function(VoiceCallState state) _showOngoing;
  final Future<void> Function() _hideOngoing;
  final Future<void> Function(bool on) _proximity;
  final DateTime Function() _clock;
  final Duration endedLinger;
  final Duration approvalsEvery;

  VoiceCallState _state = const VoiceCallState();
  VoiceCallState get state => _state;

  VoiceTransport? _join;
  int _generation = 0;
  bool _starting = false;
  bool _holding = false;
  bool _screenOffNear = false;
  Timer? _linger;
  Timer? _approvals;
  final Set<String> _callRequests = {};

  void _set(VoiceCallState next) {
    _state = next;
    VoiceCalls.active.value = next.active;
    final near = next.active && !next.speaker;
    if (near != _screenOffNear) {
      _screenOffNear = near;
      unawaited(_proximity(near));
    }
    notifyListeners();
  }

  /// Starts a call with [agentId] in [threadId], or brings back the call that runs.
  Future<void> start({
    required String agentId,
    required String threadId,
    String? incomingCallId,
  }) async {
    if (_state.active || _starting) {
      expand();
      return;
    }
    final store = _store();
    if (!store.state.session.signedIn) return;
    final ownerId = store.state.session.owner?.id;
    _linger?.cancel();
    final generation = ++_generation;
    _starting = true;
    _callRequests.clear();
    _set(
      VoiceCallState(
        phase: CallPhase.calling,
        agentId: agentId,
        threadId: threadId,
        incomingCallId: incomingCallId,
        startedAt: _clock(),
      ),
    );
    bool stale() =>
        generation != _generation ||
        _store().state.session.owner?.id != ownerId;
    try {
      final status = asJson(await _api().get('/voice/status'));
      if (stale()) return;
      if (status['transport_configured'] != true) {
        _fail('voice_transport_unconfigured');
        return;
      }
      final mic = await _microphone();
      if (stale()) return;
      if (mic != MicPermission.granted) {
        _fail(
          'voice_permission_denied',
          openSettings: mic == MicPermission.permanentlyDenied,
        );
        return;
      }
      _holding = true;
      await _keepAwake(true);
      if (stale()) {
        _released();
        return;
      }
      unawaited(_showOngoing(_state));
      late final VoiceTransport join;
      join = _transport(
        VoiceTransportCallbacks(
          onConnected: () {
            if (_join != join || _state.phase != CallPhase.calling) return;
            _set(
              _state.copyWith(
                phase: CallPhase.connected,
                connectedAt: _clock(),
              ),
            );
            unawaited(_showOngoing(_state));
          },
          onError: (code) {
            if (_join != join) return;
            _fail(code);
          },
          onActivity: (activity) {
            if (_join != join || _state.phase != CallPhase.connected) return;
            _set(
              _state.copyWith(
                speaking: activity.speaking,
                level: activity.level,
              ),
            );
          },
          onClosed: () {
            if (_join != join) return;
            _join = null;
            _released();
            if (_state.active) _finish();
          },
        ),
        _api(),
      );
      _join = join;
      _startApprovals(threadId);
      await join.connect(
        agentId: agentId,
        threadId: threadId,
        incomingCallId: incomingCallId,
      );
    } on SessionRequestCancelled {
      if (!stale()) _finish();
    } on ApiError catch (e) {
      if (!stale()) _fail(e.code);
    } catch (_) {
      if (!stale()) _fail('voice_connection_failed');
    } finally {
      _starting = false;
    }
  }

  void _fail(String code, {bool openSettings = false}) {
    final join = _join;
    _join = null;
    _stopApprovals();
    _set(
      _state.copyWith(
        phase: CallPhase.failed,
        error: code,
        openSettings: openSettings,
        minimized: false,
        speaking: false,
        level: 0,
      ),
    );
    if (join != null) unawaited(join.close());
    _released();
  }

  /// Hangs up (the call's «End call», the notification's, sign-out, app closed). Without
  /// [finalize] the server is not told (the session's token is already gone).
  Future<void> end({bool finalize = true}) async {
    _generation++;
    final join = _join;
    if (join == null) {
      if (_state.phase == CallPhase.calling) _finish();
      return;
    }
    _set(_state.copyWith(phase: CallPhase.ending));
    _stopApprovals();
    try {
      await join.close(finalize: finalize);
    } catch (_) {}
    if (_join == join) {
      _join = null;
      _released();
    }
    if (_state.phase == CallPhase.ending) _finish();
  }

  void _finish() {
    final connected = _state.connectedAt;
    _stopApprovals();
    _set(
      _state.copyWith(
        phase: CallPhase.ended,
        endedAfter: connected == null ? null : _clock().difference(connected),
        speaking: false,
        level: 0,
      ),
    );
    _linger?.cancel();
    _linger = Timer(endedLinger, () {
      if (_state.phase == CallPhase.ended) _set(const VoiceCallState());
    });
  }

  /// Lets the screen sleep and removes the call's foreground notification (once).
  void _released() {
    if (!_holding) return;
    _holding = false;
    unawaited(_keepAwake(false));
    unawaited(_hideOngoing());
  }

  /// Closes the error or «Call ended» state.
  void dismiss() {
    if (_state.active) return;
    _linger?.cancel();
    _set(const VoiceCallState());
  }

  Future<void> retry() async {
    final s = _state;
    if (!s.canRetry) return;
    _set(const VoiceCallState());
    await start(
      agentId: s.agentId!,
      threadId: s.threadId!,
      incomingCallId: s.incomingCallId,
    );
  }

  Future<void> toggleMute() async {
    if (_state.phase != CallPhase.connected &&
        _state.phase != CallPhase.calling) {
      return;
    }
    final muted = !_state.muted;
    _set(_state.copyWith(muted: muted));
    await _join?.setMuted(muted);
  }

  Future<void> toggleSpeaker() async {
    if (!_state.active) return;
    final on = !_state.speaker;
    _set(_state.copyWith(speaker: on));
    await _join?.setSpeaker(on);
  }

  void minimize() {
    if (_state.visible && !_state.minimized) {
      _set(_state.copyWith(minimized: true));
    }
  }

  /// The call page was left (back, or the router replaced the stack): a running call
  /// folds into the pill; an ended or failed one is closed.
  void leavePage() {
    if (_state.active) {
      minimize();
    } else {
      dismiss();
    }
  }

  void expand() {
    if (_state.visible && _state.minimized) {
      _set(_state.copyWith(minimized: false));
    }
  }

  // Trade approvals of the call's conversation (voice-session.tsx:95-153): read every 2 s
  // into the conversation's side store so the fixed approval card shows under the controls.
  // Merged as the cards merge them (`mergeApproval`): a read that left before the owner's tap
  // never takes a decided card back to pending. Only the owner's tap on that card decides;
  // the call itself never does.
  void _startApprovals(String threadId) {
    _stopApprovals();
    Future<void> tick() async {
      try {
        final read = asJsonList(
          await _api().get(
            '/trading/approvals',
            query: {'thread_id': threadId},
          ),
        );
        if (!_state.active || _state.threadId != threadId) return;
        final store = _store();
        store.dispatch(
          PatchThreadAction(
            threadId,
            (t) => t.copyWith(
              side: {
                ...t.side,
                SideKeys.approvals: mergeSideRows(
                  sideList(t, SideKeys.approvals),
                  read,
                  merge: mergeApproval,
                ),
              },
            ),
          ),
        );
        final rows = sideList(store.state.thread(threadId), SideKeys.approvals);
        final since = _state.startedAt ?? _clock();
        final ids = <String>[];
        for (final row in rows) {
          final id = asString(row['id']);
          if (id == null) continue;
          final pending = row['status'] == 'pending';
          if (pending) _callRequests.add(id);
          final created = asDate(row['created_at']);
          if (pending ||
              _callRequests.contains(id) ||
              (created != null && !created.isBefore(since))) {
            ids.add(id);
          }
        }
        final shown = ids.length > 5 ? ids.sublist(ids.length - 5) : ids;
        if (!listEquals(shown, _state.approvalIds)) {
          _set(_state.copyWith(approvalIds: shown));
        }
      } catch (_) {
        // The call does not depend on this read.
      }
    }

    unawaited(tick());
    _approvals = Timer.periodic(approvalsEvery, (_) => unawaited(tick()));
  }

  void _stopApprovals() {
    _approvals?.cancel();
    _approvals = null;
  }

  static Future<void> _wakelock(bool on) async {
    try {
      await (on ? WakelockPlus.enable() : WakelockPlus.disable());
    } catch (_) {}
  }

  static Future<void> _ongoingNotification(VoiceCallState state) async {
    final l10n = L10n.instance;
    registerVoiceStrings(l10n);
    final agent = appStore.state.shell.agents[state.agentId];
    final name = agent?.name ?? 'Lonora';
    await LnNotifications.startCall(
      title: l10n.t('vc_callWith', [name]),
      body: l10n.t(
        state.phase == CallPhase.connected ? 'vc_ongoing' : 'vc_calling',
      ),
      endLabel: l10n.t('endCall'),
      l10n: l10n,
      connectedAt: state.connectedAt,
    );
  }

  @override
  void dispose() {
    _linger?.cancel();
    _stopApprovals();
    super.dispose();
  }
}

/// GPT-Live voice calls with an agent over WebRTC (`POST /api/voice/sessions`).
abstract final class VoiceCalls {
  /// Whether a call is active (connecting, ringing or connected).
  static final ValueNotifier<bool> active = ValueNotifier(false);

  /// The app's call (replaced in tests).
  static VoiceCallController controller = VoiceCallController();

  /// Starts a call with [agentId] in [threadId]; shows the call UI. Errors are shown in-app.
  static Future<void> start(
    BuildContext context, {
    required String agentId,
    required String threadId,
  }) => controller.start(agentId: agentId, threadId: threadId);

  /// Answers an accepted incoming call (`incoming_call_id` links it once).
  static Future<void> answer({
    required String agentId,
    required String threadId,
    required String incomingCallId,
  }) => controller.start(
    agentId: agentId,
    threadId: threadId,
    incomingCallId: incomingCallId,
  );

  /// Hangs up whatever runs (sign-out, app closed, the notification's «End call»).
  static Future<void> end({bool finalize = true}) =>
      controller.end(finalize: finalize);
}
