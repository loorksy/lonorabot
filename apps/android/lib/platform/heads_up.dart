// The platform layer of the app: the overlay above every screen (heads-up banners, the
// incoming call, the call page / minimized call pill) and the services that run while the
// owner is signed in (notification channels and taps, the background check, incoming calls,
// update checks), all stopped on sign-out.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:permission_handler/permission_handler.dart';

import '../app/router.dart' show rootNavigatorKey;
import '../app/services.dart';
import '../design/design.dart';
import '../features/voice/call_overlay.dart';
import '../features/voice/incoming_call.dart';
import '../features/voice/voice_api.dart';
import '../features/voice/voice_strings.dart';
import '../l10n/l10n.dart';
import '../state/actions/session_actions.dart';
import '../state/app_state.dart';
import '../state/realtime.dart';
import 'background/background_sync.dart';
import 'background/poll_store.dart';
import 'heads_up/heads_up_banner.dart';
import 'heads_up/heads_up_controller.dart';
import 'navigation.dart';
import 'notifications/local_notifications.dart';
import 'notifications/notification_payload.dart';
import 'platform_strings.dart';
import 'updates/update_service.dart';
import 'updates/update_sheet.dart';

/// App-wide overlay host for in-app heads-up banners (answers in other conversations, urgent
/// attention), the minimized voice-call pill and the incoming-call overlay.
class PlatformOverlayHost extends StatelessWidget {
  const PlatformOverlayHost({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Stack(
    fit: StackFit.expand,
    children: [
      child,
      CallPresenter(controller: VoiceCalls.controller),
      IncomingCallLayer(controller: IncomingCallController.instance),
      HeadsUpLayer(controller: HeadsUpController.instance),
    ],
  );
}

/// Starts notification channels, background sync and incoming-call polling once the owner is
/// signed in; stops them on sign-out.
abstract final class PlatformServices {
  static bool _started = false;
  static _Lifecycle? _lifecycle;
  static StreamSubscription<AppState>? _changes;
  static PollStore store = FilePollStore();

  @visibleForTesting
  static DateTime Function() clock = DateTime.now;

  /// Removes a conversation's notification ([remaining]: conversations still notified).
  @visibleForTesting
  static Future<void> Function(String threadId, int remaining) cancelThread = (
    id,
    remaining,
  ) => LnNotifications.cancelThread(id, remaining: remaining);

  static Future<void> init() async {
    if (_started) return;
    _started = true;
    final Store<AppState> app = appStore;
    registerPlatformStrings();
    registerVoiceStrings();
    PlatformNavigation.ready = () => appStore.state.session.signedIn;
    LnNotifications.onOpen = (payload) {
      final location = payload.location;
      if (location == null) return;
      VoiceCalls.controller.minimize();
      PlatformNavigation.open(location);
    };
    LnNotifications.onHangUp = () => unawaited(VoiceCalls.end());
    LnNotifications.onCallTap = VoiceCalls.controller.expand;
    LnNotifications.onUpdateTap = () => unawaited(_openUpdate());
    UpdateService.instance.readyToRestart.addListener(_updateDownloaded);
    signOutHooks.add(_signOut);
    _lifecycle = _Lifecycle()..attach();

    var signedIn = false;
    String? openThread;
    String locale = app.state.prefs.locale;
    var shell = app.state.shell;
    _changes = app.onChange.listen((state) {
      if (state.session.signedIn != signedIn) {
        signedIn = state.session.signedIn;
        if (signedIn) unawaited(_signedIn(app));
      }
      if (state.openThreadId != openThread) {
        openThread = state.openThreadId;
        final id = openThread;
        if (id != null) unawaited(_threadOpened(id));
      }
      if (state.prefs.locale != locale) {
        locale = state.prefs.locale;
        // Renamed after the app rebuilt in the new language (the catalog follows the app).
        WidgetsBinding.instance.addPostFrameCallback(
          (_) => unawaited(LnNotifications.createChannels(L10n.instance)),
        );
      }
      if (!identical(state.shell, shell)) {
        shell = state.shell;
        // Only while the owner is in the app: a refresh that lands in the background (a late
        // read, a call keeping the process alive) must not pass for presence or advance the
        // cursors past messages the owner has not seen.
        if (signedIn && _inForeground) unawaited(_heartbeat(app.state));
      }
    });

    await LnNotifications.init(L10n.instance);
    await BackgroundSync.initialize();
    if (app.state.session.signedIn && !signedIn) {
      signedIn = true;
      unawaited(_signedIn(app));
    }
  }

  static Future<void> _signedIn(Store<AppState> app) async {
    HeadsUpController.instance.start(app, realtime.events);
    IncomingCallController.instance.start(app, realtime.events);
    PlatformNavigation.flush();
    await BackgroundSync.schedule();
    await _heartbeat(app.state, force: true);
    await _askNotificationsOnce();
    unawaited(_checkForUpdate(app.state.prefs.locale));
  }

  static bool get _inForeground =>
      WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed;

  /// An open conversation never keeps a notification, nor lines for the next one; the bundle's
  /// summary goes with the last conversation (cancelling a summary would also take the other
  /// conversations' notifications with it).
  static Future<void> _threadOpened(String threadId) async {
    var remaining = 0;
    try {
      final stored = await store.read();
      if (stored != null) {
        final notified = {...stored.notified}..remove(threadId);
        remaining = notified.length;
        if (notified.length != stored.notified.length) {
          await store.write(stored.copyWith(notified: notified));
        }
      }
    } catch (_) {}
    await cancelThread(threadId, remaining);
  }

  /// The automatic check (sign-in, foreground; throttled by the service). A new version is
  /// announced once, as a quiet notice whose tap opens the update sheet.
  static const _announcedKey = 'lonora.update.announced';
  static Future<void> _checkForUpdate(String lang) async {
    final info = await UpdateService.instance.check(lang: lang);
    if (info == null) return;
    try {
      if (devicePrefs.getInt(_announcedKey) == info.versionCode) return;
      await devicePrefs.setInt(_announcedKey, info.versionCode);
    } catch (_) {}
    await _postUpdate(info);
  }

  static Future<void> _postUpdate(UpdateInfo info) async {
    final l10n = L10n.instance;
    registerPlatformStrings(l10n);
    final ready =
        info.downloaded || UpdateService.instance.readyToRestart.value;
    await LnNotifications.showUpdate(
      title: l10n.t('pf_updateAvailable'),
      body: ready
          ? l10n.t('pf_updateReady')
          : info.versionName.isNotEmpty
          ? l10n.t('pf_updateVersion', [info.versionName])
          : l10n.t('pf_updateTap'),
      l10n: l10n,
    );
  }

  /// Play finished the download: the owner restarts when they choose (a toast with
  /// «Restart» while the app is open, and the notice for later).
  static void _updateDownloaded() {
    final info = UpdateService.instance.available.value;
    if (!UpdateService.instance.readyToRestart.value || info == null) return;
    unawaited(_postUpdate(info));
    final context = _rootContext();
    if (context == null || !_inForeground) return;
    registerPlatformStrings(context.l10n);
    LnToast.show(
      context,
      context.t('pf_updateReady'),
      kind: LnToastKind.notice,
      duration: const Duration(seconds: 8),
      action: (
        context.t('pf_restart'),
        () => unawaited(UpdateService.instance.install(info)),
      ),
    );
  }

  static Future<void> _openUpdate() async {
    final info = UpdateService.instance.available.value;
    final context = _rootContext();
    if (info == null || context == null) return;
    VoiceCalls.controller.minimize();
    await showUpdateSheet(context, info);
  }

  /// Below the root navigator (its overlay): sheets and toasts find the app's theme there.
  static BuildContext? _rootContext() {
    final navigator = rootNavigatorKey.currentState;
    final context = navigator?.overlay?.context ?? navigator?.context;
    return context != null && context.mounted ? context : null;
  }

  /// Android 13+: the system prompt is shown once (respecting a denial; Settings changes it).
  static const _askedKey = 'lonora.notifications.asked';
  static Future<void> _askNotificationsOnce() async {
    try {
      if (devicePrefs.getBool(_askedKey) ?? false) return;
      final status = await Permission.notification.status;
      if (status.isGranted || status.isPermanentlyDenied) return;
      await devicePrefs.setBool(_askedKey, true);
      await Permission.notification.request();
    } catch (_) {}
  }

  static DateTime? _beatAt;

  /// The background check's baseline while the owner is in the app (at most once a minute),
  /// and once more, as «background», when the app leaves the foreground.
  static Future<void> _heartbeat(
    AppState state, {
    bool force = false,
    bool foreground = true,
  }) async {
    if (!state.session.signedIn || !state.shell.loaded) return;
    final now = clock();
    final last = _beatAt;
    if (!force && last != null && now.difference(last).inSeconds < 60) return;
    _beatAt = now;
    final previous = await store.read();
    final next = foregroundSnapshot(
      state,
      now: now,
      foreground: foreground,
      previous: previous,
      rules: HeadsUpController.instance.rules,
    );
    await store.write(next);
    // A conversation read since the last beat (here, «mark all as read», or on another device)
    // drops out of [PollState.notified]: its tray notification goes too.
    if (previous != null &&
        previous.ownerId == next.ownerId &&
        previous.server == next.server) {
      for (final id in previous.notified.keys) {
        if (!next.notified.containsKey(id)) {
          await LnNotifications.cancelThread(
            id,
            remaining: next.notified.length,
          );
        }
      }
    }
  }

  static void _resumed() {
    final app = appStore;
    if (!app.state.session.signedIn) return;
    unawaited(_heartbeat(app.state, force: true));
    unawaited(HeadsUpController.instance.refreshRules(force: true));
    IncomingCallController.instance.setForeground(true);
    unawaited(_checkForUpdate(app.state.prefs.locale));
  }

  static void _paused() {
    final app = appStore;
    IncomingCallController.instance.setForeground(false);
    HeadsUpController.instance.dismiss();
    if (!app.state.session.signedIn) return;
    unawaited(_heartbeat(app.state, force: true, foreground: false));
  }

  /// The app is closing: the call ends (a microphone never outlives the app).
  static void _detached() => unawaited(VoiceCalls.end());

  static Future<void> _signOut() async {
    // SignOutAction drops the token before its hooks run, so here the call closes on this
    // phone only. On an owner sign-out the server-side close ran alongside `POST /auth/logout`
    // (the beforeSignOutHooks entry in lib/app/teardown.dart); this one stays the fallback for
    // an expired session.
    await VoiceCalls.end(finalize: api.token != null);
    HeadsUpController.instance.stop();
    IncomingCallController.instance.stop();
    PlatformNavigation.clear();
    await BackgroundSync.cancel();
    await store.clear();
    await LnNotifications.cancelAll();
    _beatAt = null;
  }

  /// Opens what a notification payload names (tests and the lead's own wiring).
  static void open(NotificationPayload payload) {
    final location = payload.location;
    if (location != null) PlatformNavigation.open(location);
  }

  @visibleForTesting
  static Future<void> resetForTest() async {
    _started = false;
    _lifecycle?.detach();
    _lifecycle = null;
    await _changes?.cancel();
    _changes = null;
    _beatAt = null;
    signOutHooks.remove(_signOut);
    UpdateService.instance.readyToRestart.removeListener(_updateDownloaded);
    clock = DateTime.now;
  }
}

class _Lifecycle with WidgetsBindingObserver {
  void attach() => WidgetsBinding.instance.addObserver(this);
  void detach() => WidgetsBinding.instance.removeObserver(this);

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        PlatformServices._resumed();
      case AppLifecycleState.paused:
        PlatformServices._paused();
      case AppLifecycleState.detached:
        PlatformServices._detached();
      case AppLifecycleState.inactive:
      case AppLifecycleState.hidden:
        break;
    }
  }
}
