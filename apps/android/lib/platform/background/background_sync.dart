// The background check: a WorkManager periodic task (every 15 minutes at the earliest, only
// with a network, deferred by Doze and App Standby like any WorkManager job) that reads the
// stored session from secure storage, asks `GET /threads/inbox` and `GET /attention`, and
// turns what changed since the stored cursor into local notifications (poll_logic.dart).
//
// It never runs agents, never writes to the server and never logs a token. It stops when
// the owner signs out (the task is cancelled and the cursor removed) and when the server says
// the session is gone (401).
import 'dart:async';
import 'dart:io' show Platform;
import 'dart:ui' show DartPluginRegistrant;

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:workmanager/workmanager.dart';

import '../../core/api/api_client.dart' show serverAllowed;
import '../../core/json.dart';
import '../../core/storage/secure_store.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/prefs_actions.dart' show readNotifyPrefs;
import '../../state/app_state.dart';
import '../heads_up/heads_up_rules.dart';
import '../notifications/local_notifications.dart';
import '../platform_strings.dart';
import 'poll_logic.dart';
import 'poll_store.dart';

const backgroundTaskName = 'lonora.background-check';
const backgroundUniqueName = 'ai.lonora.android.background-check';

/// WorkManager's entry point (a background isolate). Must stay top-level.
@pragma('vm:entry-point')
void lonoraBackgroundDispatcher() {
  // Plugins with a Dart implementation (local notifications, path_provider) register here:
  // a background engine does not run the app's plugin registrant by itself.
  DartPluginRegistrant.ensureInitialized();
  Workmanager().executeTask((task, input) async {
    try {
      await runBackgroundCheck(BackgroundCheckDeps.device());
    } catch (_) {
      // A failed check is retried at the next period; nothing is reported or logged.
    }
    return true;
  });
}

abstract final class BackgroundSync {
  static bool _initialized = false;

  /// WorkManager is Android's: elsewhere (tests on a desktop host, where the plugin would
  /// install systemd timers) nothing is scheduled.
  static bool get _supported => !kIsWeb && Platform.isAndroid;

  /// Registers the dispatcher (app isolate, once).
  static Future<void> initialize() async {
    if (_initialized || !_supported) return;
    try {
      await Workmanager().initialize(lonoraBackgroundDispatcher);
      _initialized = true;
    } catch (_) {}
  }

  /// Schedules the periodic check (kept if already scheduled).
  static Future<void> schedule() async {
    await initialize();
    if (!_initialized) return;
    try {
      await Workmanager().registerPeriodicTask(
        backgroundUniqueName,
        backgroundTaskName,
        frequency: const Duration(minutes: 15),
        constraints: Constraints(networkType: NetworkType.connected),
        existingWorkPolicy: ExistingPeriodicWorkPolicy.keep,
        backoffPolicy: BackoffPolicy.exponential,
        backoffPolicyDelay: const Duration(minutes: 5),
      );
    } catch (_) {}
  }

  static Future<void> cancel() async {
    if (!_supported) return;
    try {
      await Workmanager().cancelByUniqueName(backgroundUniqueName);
    } catch (_) {}
  }
}

/// A non-2xx answer of the background client.
class BackgroundHttpError implements Exception {
  const BackgroundHttpError(this.status);
  final int? status;
  bool get unauthorized => status == 401;
}

/// What a check needs, injectable for tests.
class BackgroundCheckDeps {
  BackgroundCheckDeps({
    required this.readSession,
    required this.get,
    required this.store,
    required this.l10n,
    required this.show,
    required this.cancelThread,
    required this.cancelAttention,
    required this.cancelSchedule,
    DateTime Function()? now,
    bool Function()? appInForeground,
    Future<bool> Function()? showPreview,
  }) : now = now ?? DateTime.now,
       appInForeground = appInForeground ?? _appResumed,
       showPreview = showPreview ?? _previewOn;

  /// The real device: secure storage, a plain Dio client, the support-directory cursor and
  /// local notifications.
  factory BackgroundCheckDeps.device() {
    final client = Dio(
      BaseOptions(
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 20),
        responseType: ResponseType.json,
        validateStatus: (_) => true,
        headers: {'Accept': 'application/json'},
      ),
    );
    return BackgroundCheckDeps(
      readSession: () => SecureStore().readSessionNoRepair(),
      get: (server, token, path) async {
        final response = await client.get<Object?>(
          '$server/api$path',
          options: Options(headers: {'Authorization': 'Bearer $token'}),
        );
        final status = response.statusCode ?? 0;
        if (status < 200 || status >= 300) throw BackgroundHttpError(status);
        return response.data;
      },
      store: FilePollStore(),
      l10n: (lang) async {
        final l10n = await L10n.load(locale: Locale(lang));
        registerPlatformStrings(l10n);
        await LnNotifications.init(l10n, appIsolate: false);
        return l10n;
      },
      show: (note, l10n, bundle) =>
          LnNotifications.show(note, l10n, messagesInBundle: bundle),
      cancelThread: (id, remaining) =>
          LnNotifications.cancelThread(id, remaining: remaining),
      cancelAttention: LnNotifications.cancelAttention,
      cancelSchedule: BackgroundSync.cancel,
      showPreview: _storedPreview,
    );
  }

  final Future<StoredSession?> Function() readSession;
  final Future<Object?> Function(String server, String token, String path) get;
  final PollStore store;
  final Future<L10n> Function(String lang) l10n;
  final Future<void> Function(PlannedNotification note, L10n l10n, int bundle)
  show;
  final Future<void> Function(String threadId, int remaining) cancelThread;
  final Future<void> Function(String attentionId) cancelAttention;
  final Future<void> Function() cancelSchedule;
  final DateTime Function() now;
  final bool Function() appInForeground;

  /// This phone's «معاينة النص» (device prefs; this isolate has no store).
  final Future<bool> Function() showPreview;

  static Future<bool> _previewOn() async => true;

  /// Read fresh from the app's device prefs; unreadable means no preview.
  static Future<bool> _storedPreview() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.reload();
      return readNotifyPrefs(prefs).preview;
    } catch (_) {
      return false;
    }
  }

  static bool _appResumed() {
    try {
      return WidgetsBinding.instance.lifecycleState ==
          AppLifecycleState.resumed;
    } catch (_) {
      return false;
    }
  }
}

enum BackgroundOutcome {
  noSession,
  foreground,
  baseline,
  checked,
  unauthorized,
  failed,
}

/// One background check (see the file comment).
Future<BackgroundOutcome> runBackgroundCheck(BackgroundCheckDeps d) async {
  final session = await d.readSession();
  final now = d.now();
  // A remote plain-http server never gets the token (the app drops such a session too).
  if (session == null ||
      !serverAllowed(session.server) ||
      (session.expiresAt != null && session.expiresAt!.isBefore(now))) {
    await d.store.clear();
    await d.cancelSchedule();
    return BackgroundOutcome.noSession;
  }
  final stored = await d.store.read();
  if (d.appInForeground() || (stored?.foregroundActive(now) ?? false)) {
    return BackgroundOutcome.foreground;
  }
  List<Json> inbox;
  List<Json> attention;
  try {
    final answers = await Future.wait([
      d.get(session.server, session.token, '/threads/inbox'),
      d.get(session.server, session.token, '/attention'),
    ]);
    inbox = asJsonList(answers[0]);
    attention = asJsonList(answers[1]);
  } on BackgroundHttpError catch (e) {
    if (e.unauthorized) {
      // The session ended on the server: stop checking until the owner signs in again.
      await d.store.clear();
      await d.cancelSchedule();
      return BackgroundOutcome.unauthorized;
    }
    return BackgroundOutcome.failed;
  } catch (_) {
    return BackgroundOutcome.failed;
  }

  final sameOwner =
      stored != null &&
      stored.ownerId == session.ownerId &&
      stored.server == session.server;
  if (!sameOwner) {
    await d.store.write(
      baselineState(
        ownerId: session.ownerId,
        server: session.server,
        inbox: inbox,
        attention: attention,
        now: now,
        previous: stored,
      ),
    );
    return BackgroundOutcome.baseline;
  }

  final l10n = await d.l10n(stored.lang);
  final result = computePoll(
    stored,
    inbox: inbox,
    attention: attention,
    now: now,
    newMessage: l10n.t('newMessage'),
    attentionText: (code, item) {
      final params = asJson(item['parameters']);
      return attentionTitle(
        l10n,
        code,
        reason: asString(params['reason']),
        providerName: asString(params['provider_name']),
      );
    },
  );
  await d.store.write(result.next);
  final bundle = result.next.notified.length;
  for (final id in result.clearThreads) {
    await d.cancelThread(id, bundle);
  }
  for (final id in result.clearAttention) {
    await d.cancelAttention(id);
  }
  final preview = result.notes.isEmpty || await d.showPreview();
  for (final note in result.notes) {
    await d.show(
      preview ? note : _withoutPreview(note, l10n.t('newMessage')),
      l10n,
      bundle,
    );
  }
  return BackgroundOutcome.checked;
}

/// «معاينة النص» off on this phone: «رسالة جديدة» instead of the words, without speakers.
PlannedNotification _withoutPreview(PlannedNotification note, String text) =>
    PlannedNotification(
      kind: note.kind,
      id: note.id,
      channel: note.channel,
      title: note.title,
      lines: [NoteLine(text)],
      payload: note.payload,
      threadId: note.threadId,
      count: note.count,
      groupConversation: note.groupConversation,
      when: note.when,
    );

/// The baseline the app writes while the owner is in it: what the inbox and attention list
/// hold now is seen, the names and rules the background needs, and the foreground heartbeat
/// ([foreground] false when the app goes to the background).
PollState foregroundSnapshot(
  AppState state, {
  required DateTime now,
  required bool foreground,
  PollState? previous,
  DeliveryRules? rules,
}) {
  final shell = state.shell;
  final owner = state.session.owner!.id;
  final server = state.session.server!;
  final keep =
      previous != null && previous.ownerId == owner && previous.server == server
      ? previous
      : null;
  final titles = <String, String>{};
  for (final e in shell.inbox) {
    final name = e.groupId != null
        ? shell.groups[e.groupId]?.name
        : shell.agents[e.agentId]?.name;
    if (name != null && name.isNotEmpty) titles[e.threadId] = name;
  }
  final seen = <String>[
    ...?keep?.seenAttention,
    for (final item in shell.attention)
      if (asString(item['id']) case final String id) id,
  ];
  // A conversation read in the app (or open now) keeps no lines: its next answer starts a
  // fresh notification instead of re-posting what the owner already read.
  final unread = {for (final e in shell.inbox) e.threadId: e.unreadCount};
  final notified = {
    for (final MapEntry(:key, :value) in (keep?.notified ?? const {}).entries)
      if (key != state.openThreadId && (unread[key] ?? 0) > 0) key: value,
  };
  return PollState(
    ownerId: owner,
    server: server,
    since: now,
    seqs: {
      ...?keep?.seqs,
      for (final e in shell.inbox) e.threadId: e.lastMessage?.seq ?? 0,
    },
    seenAttention: seen.toSet().toList(),
    notified: notified,
    notifiedAttention: keep?.notifiedAttention ?? const {},
    titles: titles,
    agentNames: {
      for (final a in shell.agents.values)
        if (a.name.isNotEmpty) a.id: a.name,
    },
    lang: state.prefs.locale,
    quiet: rules?.quiet ?? keep?.quiet,
    off: rules?.off ?? keep?.off ?? const {},
    foregroundAt: foreground ? now : null,
  );
}
