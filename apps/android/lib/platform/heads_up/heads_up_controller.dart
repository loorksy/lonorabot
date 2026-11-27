// The in-app heads-up (apps/mobile/components/heads-up.tsx): while the app is open, an agent's
// answer in another conversation and an urgent attention item slide in at the top for 5.2 s,
// held while pressed and 2.4 s more after release; a tap opens the conversation, a swipe up
// or the time hides it. Mute, archive, quiet hours, an agent's in-app rule and this phone's
// «إشعارات داخل التطبيق» suppress answers (Q4, Q47); urgent attention always shows. With
// «معاينة النص» off a banner says «رسالة جديدة» (apps/web HeadsUp.tsx).
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/foundation.dart';

import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/realtime/lonora_event.dart';
import '../../l10n/l10n.dart';
import '../../state/app_state.dart';
import '../platform_bridge.dart';
import 'heads_up_rules.dart';

/// A banner on screen ([serial] distinguishes two banners with the same words).
class ShownBanner {
  const ShownBanner(this.banner, this.serial);
  final HeadsUpBanner banner;
  final int serial;
}

class HeadsUpController {
  HeadsUpController({
    this.showFor = const Duration(milliseconds: 5200),
    this.afterRelease = const Duration(milliseconds: 2400),
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  /// The app's controller (PlatformServices starts it).
  static final instance = HeadsUpController();

  final Duration showFor;
  final Duration afterRelease;
  final DateTime Function() _clock;

  final ValueNotifier<ShownBanner?> current = ValueNotifier(null);
  DeliveryRules rules = const DeliveryRules();

  Store<AppState>? _store;
  StreamSubscription<LonoraEvent>? _events;
  StreamSubscription<AppState>? _changes;
  Timer? _timer;
  int _serial = 0;
  bool _held = false;
  DateTime _openedAt = DateTime.now();
  DateTime? _rulesReadAt;
  final Set<String> _announced = {};
  List<Json> _lastAttention = const [];

  /// Starts listening for [store]'s owner. [events] is the realtime feed.
  void start(Store<AppState> store, Stream<LonoraEvent> events) {
    stop();
    _store = store;
    _openedAt = _clock();
    _announced
      ..clear()
      ..addAll([
        for (final item in store.state.shell.attention)
          if (asString(item['id']) case final String id) id,
      ]);
    _lastAttention = store.state.shell.attention;
    _events = events.listen(_onEvent);
    _changes = store.onChange.listen(_onState);
    unawaited(refreshRules());
  }

  void stop() {
    _events?.cancel();
    _changes?.cancel();
    _events = null;
    _changes = null;
    _store = null;
    _timer?.cancel();
    current.value = null;
  }

  /// `GET /owner/profile` (quiet hours) and `GET /agents/notifications` (in-app rules), at
  /// start, on foreground ([force]) and at most once a minute with the shell's refreshes.
  Future<void> refreshRules({bool force = false}) async {
    final now = _clock();
    final last = _rulesReadAt;
    if (!force && last != null && now.difference(last).inSeconds < 60) return;
    _rulesReadAt = now;
    QuietHours? quiet = rules.quiet;
    Set<String> off = rules.off;
    try {
      final profile = asJson(await api.get('/owner/profile'));
      quiet = await _withZoneOffset(QuietHours.fromJson(profile['reach_me']));
    } on SessionRequestCancelled {
      return;
    } catch (_) {}
    try {
      off = DeliveryRules.offFrom(await api.get('/agents/notifications'));
    } on SessionRequestCancelled {
      return;
    } catch (_) {}
    rules = DeliveryRules(quiet: quiet, off: off);
  }

  /// The phone's IANA zone and another zone's UTC offset (MainActivity; replaced in tests).
  @visibleForTesting
  Future<String?> Function() phoneZone = PlatformBridge.timeZone;
  @visibleForTesting
  Future<int?> Function(String zone, DateTime at) zoneOffset =
      PlatformBridge.zoneOffsetMinutes;

  /// Web and Expo read the window in the policy's zone. Dart has no zone database: a zone
  /// other than the phone's (a policy saved from Web elsewhere) is resolved to its current
  /// offset by the phone, which the background check also keeps (PollState). The phone's own
  /// zone stays on the phone's clock (daylight saving follows by itself); an unknown zone
  /// falls back to it.
  Future<QuietHours?> _withZoneOffset(QuietHours? quiet) async {
    if (quiet == null || quiet.utc) return quiet;
    try {
      if (await phoneZone() == quiet.timezone) return quiet;
      return quiet.withOffset(await zoneOffset(quiet.timezone, _clock()));
    } catch (_) {
      return quiet;
    }
  }

  void _onEvent(LonoraEvent event) {
    final store = _store;
    if (store == null || !store.state.session.signedIn) return;
    final notify = store.state.prefs.notify;
    if (!notify.inApp) return;
    final now = _clock();
    // After a reconnect the feed replays what was missed: only the last moments are news.
    final opened = now.subtract(const Duration(seconds: 15)).isAfter(_openedAt)
        ? now.subtract(const Duration(seconds: 15))
        : _openedAt;
    final next = messageBanner(
      event,
      shell: store.state.shell,
      current: store.state.openThreadId,
      rules: rules,
      openedAt: opened,
      now: now,
      newMessage: L10n.instance.t('newMessage'),
    );
    if (next != null) show(_withPreview(next, notify));
  }

  void _onState(AppState state) {
    if (!state.session.signedIn) {
      dismiss();
      return;
    }
    final attention = state.shell.attention;
    if (identical(attention, _lastAttention)) return;
    _lastAttention = attention;
    unawaited(refreshRules());
    for (final item in attention) {
      final id = asString(item['id']);
      if (id == null || !_announced.add(id)) continue;
      // A refused model names its failure family and provider in `parameters`.
      final params = asJson(item['parameters']);
      final title = attentionTitle(
        L10n.instance,
        asStr(item['code']),
        reason: asString(params['reason']),
        providerName: asString(params['provider_name']),
      );
      final next = attentionBanner(
        item,
        shell: state.shell,
        openedAt: _openedAt,
        title: title,
      );
      if (next != null && next.threadId != state.openThreadId) {
        show(_withPreview(next, state.prefs.notify));
      }
    }
  }

  /// «معاينة النص» off: «رسالة جديدة» instead of the words, without a speaker.
  HeadsUpBanner _withPreview(HeadsUpBanner banner, NotifyPrefs notify) =>
      notify.preview
      ? banner
      : HeadsUpBanner(
          threadId: banner.threadId,
          agentId: banner.agentId,
          groupId: banner.groupId,
          text: L10n.instance.t('newMessage'),
          kind: banner.kind,
          key: banner.key,
          around: banner.around,
        );

  void show(HeadsUpBanner banner) {
    _serial++;
    _held = false;
    current.value = ShownBanner(banner, _serial);
    _arm(showFor);
  }

  /// Pressed: the banner waits. Released: [afterRelease] more.
  void hold(bool pressed) {
    if (current.value == null) return;
    _held = pressed;
    if (pressed) {
      _timer?.cancel();
    } else {
      _arm(afterRelease);
    }
  }

  void _arm(Duration delay) {
    _timer?.cancel();
    final serial = _serial;
    _timer = Timer(delay, () {
      if (!_held && current.value?.serial == serial) current.value = null;
    });
  }

  void dismiss() {
    _timer?.cancel();
    _held = false;
    current.value = null;
  }

  @visibleForTesting
  DateTime get openedAt => _openedAt;
}
