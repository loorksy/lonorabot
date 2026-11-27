// An agent ringing the owner (apps/mobile/components/incoming-call.tsx, lib/incoming-call.ts):
// foreground only — the server has no push for calls (lonora-api-contract.md §17.2). The
// `voice.incoming.updated` event brings it at once; as on Expo, a poll every 3 s of
// `GET /voice/incoming` (while the owner's policy enables calls, the app is in front and no
// call runs) covers a missed event, and the policy itself is read again every 30 s so calls
// switched on elsewhere start ringing here too.
// «رد» answers (`POST /voice/incoming/{id}/respond {action: accept, device_id}`, then joins
// with `incoming_call_id`), «رفض» declines, «الرد برسالة» steps aside and opens the chat.
// Nothing answers by itself, and an answered call never authorizes trading.
//
// Layout: a card at the top on the toast's surface.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';

import '../../app/routes.dart';
import '../../app/services.dart';
import '../../avatar/avatar.dart';
import '../../core/api/api_client.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../platform/navigation.dart';
import '../../state/app_state.dart';
import 'voice_api.dart';
import 'voice_strings.dart';

/// The first ringing, unexpired call (`visibleIncoming`).
Json? visibleIncoming(Iterable<Json> rows, DateTime now) {
  for (final row in rows) {
    final expires = asDate(row['expires_at']);
    if (row['status'] == 'ringing' && expires != null && expires.isAfter(now)) {
      return row;
    }
  }
  return null;
}

/// An accept the server confirmed, still valid, that authorizes nothing (`acceptedIncoming`).
bool acceptedIncoming(Json row, DateTime now) {
  final expires = asDate(row['expires_at']);
  return row['status'] == 'accepted' &&
      expires != null &&
      expires.isAfter(now) &&
      row['execution_authorized'] == false;
}

class IncomingCallController extends ChangeNotifier {
  IncomingCallController({
    ApiClient Function()? api,
    this.pollEvery = const Duration(seconds: 3),
    this.policyEvery = const Duration(seconds: 30),
    DateTime Function()? clock,
  }) : _api = api ?? (() => sl<ApiClient>()),
       _clock = clock ?? DateTime.now;

  static final instance = IncomingCallController();

  final ApiClient Function() _api;
  final DateTime Function() _clock;
  final Duration pollEvery;
  final Duration policyEvery;
  DateTime? _policyAt;

  Json? _call;
  String? _device;
  bool _enabled = false;
  bool busy = false;
  String? error;
  bool _foreground = true;
  final Set<String> _aside = {};
  Store<AppState>? _store;
  StreamSubscription<LonoraEvent>? _events;
  Timer? _poll;
  Timer? _expiry;
  bool _loading = false;

  /// The ringing call shown, when the policy allows it and no call runs.
  Json? get call => _call != null && _device != null && !VoiceCalls.active.value
      ? _call
      : null;

  void start(Store<AppState> store, Stream<LonoraEvent> events) {
    stop();
    _store = store;
    _events = events.listen(_onEvent);
    VoiceCalls.active.addListener(notifyListeners);
    unawaited(refresh());
    _poll = Timer.periodic(pollEvery, (_) {
      final read = _policyAt;
      unawaited(
        refresh(
          policy: read == null || _clock().difference(read) >= policyEvery,
        ),
      );
    });
  }

  void stop() {
    _events?.cancel();
    _events = null;
    _poll?.cancel();
    _poll = null;
    _expiry?.cancel();
    VoiceCalls.active.removeListener(notifyListeners);
    _store = null;
    _policyAt = null;
    _set(null);
  }

  /// Foreground only: going to the background hides the invitation.
  void setForeground(bool value) {
    _foreground = value;
    if (value) {
      unawaited(refresh());
    } else {
      _set(null);
    }
  }

  void _onEvent(LonoraEvent event) {
    if (event.kind != 'voice.incoming.updated') return;
    final row = asJson(event.payload['call'] ?? event.payload);
    final id = asString(row['id']);
    if (id == null) return;
    if (row['status'] == 'ringing') {
      if (_device == null) {
        unawaited(refresh());
        return;
      }
      if (!_aside.contains(id) && _foreground) {
        final visible = visibleIncoming([row], _clock());
        if (visible != null) _set(visible);
      }
    } else if (asString(_call?['id']) == id) {
      _set(null);
    }
  }

  /// `GET /voice/incoming/policy` (enabled? device), then `GET /voice/incoming`.
  Future<void> refresh({bool policy = true}) async {
    final store = _store;
    if (_loading || store == null || !store.state.session.signedIn) return;
    if (!_foreground || VoiceCalls.active.value) return;
    _loading = true;
    try {
      if (policy || _device == null) {
        final p = asJson(await _api().get('/voice/incoming/policy'));
        _policyAt = _clock();
        _device = asString(p['device_id']);
        _enabled = p['enabled'] == true;
      }
      if (!_enabled) {
        if (_call != null) _set(null);
        return;
      }
      final rows = asJsonList(await _api().get('/voice/incoming'));
      _set(
        visibleIncoming(
          rows.where((r) => !_aside.contains(asString(r['id']))),
          _clock(),
        ),
      );
    } catch (_) {
      // Session recovery owns transport failures; nothing is shown for them.
    } finally {
      _loading = false;
    }
  }

  void _set(Json? value) {
    _expiry?.cancel();
    if (!identical(value, _call)) error = null;
    _call = value;
    final expires = asDate(value?['expires_at']);
    if (expires != null) {
      final left = expires.difference(_clock());
      _expiry = Timer(left.isNegative ? Duration.zero : left, () => _set(null));
    }
    notifyListeners();
  }

  /// «رد» / «رفض». Accept joins the call only when the server confirms it.
  Future<void> respond(bool accept) async {
    final row = _call;
    final device = _device;
    if (row == null || device == null || busy) return;
    busy = true;
    error = null;
    notifyListeners();
    try {
      final id = asStr(row['id']);
      final result = asJson(
        await _api().post(
          '/voice/incoming/${Uri.encodeComponent(id)}/respond',
          {'action': accept ? 'accept' : 'reject', 'device_id': device},
        ),
      );
      _set(null);
      if (accept && acceptedIncoming(result, _clock())) {
        await VoiceCalls.answer(
          agentId: asStr(result['agent_id']),
          threadId: asStr(result['thread_id']),
          incomingCallId: asStr(result['id']),
        );
      }
    } on SessionRequestCancelled {
      _set(null);
    } on ApiError catch (e) {
      error = e.code;
    } catch (_) {
      error = 'request_failed';
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  /// «الرد برسالة»: this call steps aside here and its chat opens.
  void replyWithMessage() {
    final row = _call;
    if (row == null) return;
    _aside.add(asStr(row['id']));
    _set(null);
    PlatformNavigation.open(Routes.thread(asStr(row['thread_id'])));
  }
}

/// The invitation card (pure: goldens render it directly).
class IncomingCallView extends StatelessWidget {
  const IncomingCallView({
    super.key,
    required this.reason,
    this.agent,
    this.error,
    this.busy = false,
    this.onAnswer,
    this.onDecline,
    this.onMessage,
  });

  final String reason;
  final Agent? agent;
  final String? error;
  final bool busy;
  final VoidCallback? onAnswer;
  final VoidCallback? onDecline;
  final VoidCallback? onMessage;

  @override
  Widget build(BuildContext context) {
    registerVoiceStrings(context.l10n);
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final a = agent;
    return Semantics(
      container: true,
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(LnSpace.cardPadding),
        decoration: BoxDecoration(
          color: c.inverseSurface,
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.card)),
          boxShadow: LnShadow.darkChrome,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                if (a != null) ...[
                  LonoraAvatar(
                    agentId: a.id,
                    face: a.avatar,
                    color: a.color,
                    tradesOnItsOwn: a.tradesOnItsOwn,
                    state: LonoraAvatarState.speaking,
                    size: 44,
                    animate: false,
                  ),
                  const SizedBox(width: LnSpace.sm),
                ],
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        l10n.t('vc_incomingTitle'),
                        style: ln.text.captionStrong.copyWith(
                          color: c.onInverse,
                        ),
                      ),
                      if (reason.isNotEmpty)
                        Text(
                          reason,
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                          textDirection: textDirectionFor(
                            reason,
                            Directionality.of(context),
                          ),
                          style: ln.text.footnote.copyWith(
                            color: c.onInverseMuted,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
            if (error != null) ...[
              const SizedBox(height: LnSpace.xs),
              Text(
                l10n.errorText(error),
                style: ln.text.footnote.copyWith(color: c.error),
              ),
            ],
            const SizedBox(height: LnSpace.sm),
            Row(
              children: [
                Expanded(
                  child: _Choice(
                    label: l10n.t('vc_answer'),
                    fill: c.success,
                    ink: c.onAccent,
                    onTap: busy ? null : onAnswer,
                  ),
                ),
                const SizedBox(width: LnSpace.sm),
                Expanded(
                  child: _Choice(
                    label: l10n.t('vc_decline'),
                    fill: c.error,
                    ink: c.onAccent,
                    onTap: busy ? null : onDecline,
                  ),
                ),
              ],
            ),
            const SizedBox(height: LnSpace.xs),
            _Choice(
              label: l10n.t('vc_replyMessage'),
              fill: c.inverseFill,
              ink: c.onInverse,
              onTap: busy ? null : onMessage,
            ),
          ],
        ),
      ),
    );
  }
}

class _Choice extends StatelessWidget {
  const _Choice({
    required this.label,
    required this.fill,
    required this.ink,
    this.onTap,
  });

  final String label;
  final Color fill;
  final Color ink;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => LnTappable(
    onTap: onTap,
    enabled: onTap != null,
    haptic: true,
    semanticLabel: label,
    excludeChildSemantics: true,
    child: Container(
      height: 48,
      alignment: Alignment.center,
      decoration: ShapeDecoration(color: fill, shape: const StadiumBorder()),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: context.ln.text.button.copyWith(color: ink),
      ),
    ),
  );
}

/// The incoming layer of [PlatformOverlayHost].
class IncomingCallLayer extends StatelessWidget {
  const IncomingCallLayer({super.key, required this.controller});

  final IncomingCallController controller;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: controller,
    builder: (context, _) {
      final row = controller.call;
      if (row == null) return const SizedBox.shrink();
      final agent = context.getSelect<AppState, Agent?>(
        (s) => s.shell.agents[asString(row['agent_id'])],
      );
      return PositionedDirectional(
        top: MediaQuery.paddingOf(context).top + LnSpace.sm,
        start: LnSpace.pageGutter,
        end: LnSpace.pageGutter,
        child: IncomingCallView(
          reason: asStr(row['reason']),
          agent: agent,
          error: controller.error,
          busy: controller.busy,
          onAnswer: () => unawaited(controller.respond(true)),
          onDecline: () => unawaited(controller.respond(false)),
          onMessage: controller.replyWithMessage,
        ),
      );
    },
  );
}
