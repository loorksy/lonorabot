// Lonora's local notifications (flutter_local_notifications): the four channels with Lonora's
// small icon, one notification per conversation bundled under a summary, attention items,
// the ongoing-call foreground service, and taps routed through the app router.
//
// Used from the app isolate and from the background (WorkManager) isolate; only the app
// isolate handles taps. Nothing here logs a payload's words or any token.
import 'dart:async';
import 'dart:isolate';
import 'dart:ui' show IsolateNameServer;

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../../design/tokens.dart' show LnPalette;
import '../../l10n/l10n.dart';
import '../background/poll_logic.dart';
import '../platform_strings.dart';
import 'notification_payload.dart';

/// The «End call» action of the ongoing-call notification.
const hangUpActionId = 'hang_up';

/// The app isolate's port for actions tapped while a background isolate handles them.
const _callPortName = 'ai.lonora.android/call-actions';

/// Lonora's brand tint for the small icon.
final _accent = LnPalette.light.brand;

/// Notification taps and actions that arrive on a background isolate: «End call» is sent to
/// the app isolate's port (the call lives there). Must stay a top-level entry point.
@pragma('vm:entry-point')
void lonoraNotificationBackgroundResponse(NotificationResponse response) {
  if (response.actionId == hangUpActionId) {
    IsolateNameServer.lookupPortByName(_callPortName)?.send(hangUpActionId);
  }
}

abstract final class LnNotifications {
  static FlutterLocalNotificationsPlugin plugin =
      FlutterLocalNotificationsPlugin();

  static bool _ready = false;
  static ReceivePort? _port;

  /// A tap on a conversation or attention notification (the app isolate).
  static void Function(NotificationPayload payload)? onOpen;

  /// «End call» on the call notification.
  static void Function()? onHangUp;

  /// A tap on the call notification: bring the call back.
  static void Function()? onCallTap;

  /// A tap on the update notification: the update sheet.
  static void Function()? onUpdateTap;

  static AndroidFlutterLocalNotificationsPlugin? get _android => plugin
      .resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin
      >();

  /// Initializes the plugin and the channels. [appIsolate] also routes taps, including the
  /// tap that launched the app.
  static Future<void> init(L10n l10n, {bool appIsolate = true}) async {
    if (defaultTargetPlatform != TargetPlatform.android) return;
    registerPlatformStrings(l10n);
    if (!_ready) {
      _ready = true;
      try {
        await plugin.initialize(
          settings: const InitializationSettings(
            android: AndroidInitializationSettings('ic_stat_lonora'),
          ),
          onDidReceiveNotificationResponse: appIsolate ? _handle : null,
          onDidReceiveBackgroundNotificationResponse:
              lonoraNotificationBackgroundResponse,
        );
      } catch (_) {
        _ready = false;
        return;
      }
      if (appIsolate) {
        _listenForActions();
        try {
          final launch = await plugin.getNotificationAppLaunchDetails();
          final response = launch?.notificationResponse;
          if (launch?.didNotificationLaunchApp == true && response != null) {
            _handle(response);
          }
        } catch (_) {}
      }
    }
    await createChannels(l10n);
  }

  static void _listenForActions() {
    IsolateNameServer.removePortNameMapping(_callPortName);
    final port = _port ??= ReceivePort();
    IsolateNameServer.registerPortWithName(port.sendPort, _callPortName);
    port.listen((message) {
      if (message == hangUpActionId) onHangUp?.call();
    });
  }

  static void _handle(NotificationResponse response) {
    if (response.actionId == hangUpActionId) {
      onHangUp?.call();
      return;
    }
    final payload = NotificationPayload.decode(response.payload);
    if (payload == null) return;
    switch (payload.target) {
      case NotificationTarget.call:
        onCallTap?.call();
      case NotificationTarget.update:
        onUpdateTap?.call();
      case _:
        onOpen?.call(payload);
    }
  }

  /// Creates (or renames, after a language change) Lonora's channels.
  static Future<void> createChannels(L10n l10n) async {
    final android = _android;
    if (android == null) return;
    final channels = [
      AndroidNotificationChannel(
        LnChannels.messages,
        l10n.t('pf_channelMessages'),
        description: l10n.t('pf_channelMessagesDesc'),
        importance: Importance.high,
      ),
      AndroidNotificationChannel(
        LnChannels.attention,
        l10n.t('sh_updates'),
        description: l10n.t('pf_channelAttentionDesc'),
        importance: Importance.high,
      ),
      AndroidNotificationChannel(
        LnChannels.calls,
        l10n.t('pf_channelCalls'),
        description: l10n.t('pf_channelCallsDesc'),
        importance: Importance.low,
        playSound: false,
        enableVibration: false,
        showBadge: false,
      ),
      AndroidNotificationChannel(
        LnChannels.status,
        l10n.t('pf_channelStatus'),
        description: l10n.t('pf_channelStatusDesc'),
        importance: Importance.low,
        playSound: false,
        enableVibration: false,
      ),
    ];
    for (final channel in channels) {
      try {
        await android.createNotificationChannel(channel);
      } catch (_) {}
    }
  }

  /// Whether the system lets Lonora post (Android 13+ permission, or switched off).
  static Future<bool> enabled() async {
    try {
      return await _android?.areNotificationsEnabled() ?? false;
    } catch (_) {
      return false;
    }
  }

  /// Posts or updates one planned notification, then the bundle's summary.
  static Future<void> show(
    PlannedNotification note,
    L10n l10n, {
    int messagesInBundle = 0,
  }) async {
    if (!_ready) return;
    final message = note.kind == PlannedKind.message;
    final me = const Person(name: 'Lonora', key: 'owner');
    final style = message
        ? MessagingStyleInformation(
            me,
            conversationTitle: note.groupConversation ? note.title : null,
            groupConversation: note.groupConversation,
            messages: [
              for (final line in note.lines)
                Message(
                  line.text,
                  note.when ?? DateTime.now(),
                  Person(
                    name: line.who ?? note.title,
                    key: line.who ?? note.title,
                    bot: true,
                  ),
                ),
            ],
          )
        : BigTextStyleInformation(note.body);
    final details = AndroidNotificationDetails(
      note.channel,
      _channelName(note.channel, l10n),
      icon: 'ic_stat_lonora',
      color: _accent,
      importance: note.channel == LnChannels.status
          ? Importance.low
          : Importance.high,
      priority: note.channel == LnChannels.status
          ? Priority.low
          : Priority.high,
      category: message
          ? AndroidNotificationCategory.message
          : AndroidNotificationCategory.reminder,
      styleInformation: style,
      groupKey: message
          ? LnNotificationGroups.messages
          : LnNotificationGroups.attention,
      number: message ? note.count : null,
      when: note.when?.millisecondsSinceEpoch,
      showWhen: note.when != null,
      onlyAlertOnce: false,
      autoCancel: true,
      visibility: NotificationVisibility.private,
    );
    try {
      await plugin.show(
        id: note.id,
        title: note.title,
        body: note.body,
        notificationDetails: NotificationDetails(android: details),
        payload: note.payload.encode(),
      );
      if (message && messagesInBundle > 1) {
        await _summary(messagesInBundle, l10n);
      }
    } catch (_) {
      // Posting is best effort (permission revoked, channel blocked).
    }
  }

  static Future<void> _summary(int conversations, L10n l10n) => plugin.show(
    id: LnNotificationIds.messagesSummary,
    title: 'Lonora',
    body: l10n.t('pf_newMessages', [conversations]),
    notificationDetails: NotificationDetails(
      android: AndroidNotificationDetails(
        LnChannels.messages,
        l10n.t('pf_channelMessages'),
        icon: 'ic_stat_lonora',
        color: _accent,
        groupKey: LnNotificationGroups.messages,
        setAsGroupSummary: true,
        groupAlertBehavior: GroupAlertBehavior.children,
        onlyAlertOnce: true,
        visibility: NotificationVisibility.private,
      ),
    ),
  );

  static String _channelName(String channel, L10n l10n) => switch (channel) {
    LnChannels.messages => l10n.t('pf_channelMessages'),
    LnChannels.attention => l10n.t('sh_updates'),
    LnChannels.calls => l10n.t('pf_channelCalls'),
    _ => l10n.t('pf_channelStatus'),
  };

  /// Removes a conversation's notification (opened, or read elsewhere).
  static Future<void> cancelThread(String threadId, {int remaining = 0}) async {
    if (!_ready) return;
    try {
      await plugin.cancel(id: threadNotificationId(threadId));
      if (remaining == 0) {
        await plugin.cancel(id: LnNotificationIds.messagesSummary);
      }
    } catch (_) {}
  }

  static Future<void> cancelAttention(String attentionId) async {
    if (!_ready) return;
    try {
      await plugin.cancel(id: attentionNotificationId(attentionId));
    } catch (_) {}
  }

  /// A quiet notice that an update is available or downloaded; its tap opens the sheet.
  static Future<void> showUpdate({
    required String title,
    required String body,
    required L10n l10n,
  }) async {
    if (!_ready) return;
    try {
      await plugin.show(
        id: LnNotificationIds.update,
        title: title,
        body: body,
        notificationDetails: NotificationDetails(
          android: AndroidNotificationDetails(
            LnChannels.status,
            l10n.t('pf_channelStatus'),
            icon: 'ic_stat_lonora',
            color: _accent,
            importance: Importance.low,
            priority: Priority.low,
            category: AndroidNotificationCategory.recommendation,
            onlyAlertOnce: true,
            autoCancel: true,
            visibility: NotificationVisibility.public,
          ),
        ),
        payload: const NotificationPayload.update().encode(),
      );
    } catch (_) {}
  }

  /// Everything Lonora posted (sign-out).
  static Future<void> cancelAll() async {
    if (!_ready) return;
    try {
      await plugin.cancelAll();
    } catch (_) {}
  }

  /// The ongoing call as a microphone foreground service: the call keeps its microphone while
  /// the app is in the background, visibly, with «End call» on the notification.
  static Future<bool> startCall({
    required String title,
    required String body,
    required String endLabel,
    required L10n l10n,
    DateTime? connectedAt,
  }) async {
    final android = _android;
    if (!_ready || android == null) return false;
    try {
      await android.startForegroundService(
        id: LnNotificationIds.call,
        title: title,
        body: body,
        payload: const NotificationPayload.call().encode(),
        foregroundServiceTypes: {
          AndroidServiceForegroundType.foregroundServiceTypeMicrophone,
        },
        startType: AndroidServiceStartType.startNotSticky,
        notificationDetails: AndroidNotificationDetails(
          LnChannels.calls,
          l10n.t('pf_channelCalls'),
          icon: 'ic_stat_lonora',
          color: _accent,
          importance: Importance.low,
          priority: Priority.low,
          category: AndroidNotificationCategory.call,
          ongoing: true,
          autoCancel: false,
          onlyAlertOnce: true,
          playSound: false,
          enableVibration: false,
          usesChronometer: connectedAt != null,
          when: connectedAt?.millisecondsSinceEpoch,
          showWhen: connectedAt != null,
          visibility: NotificationVisibility.public,
          actions: [
            AndroidNotificationAction(
              hangUpActionId,
              endLabel,
              cancelNotification: false,
              semanticAction: SemanticAction.call,
            ),
          ],
        ),
      );
      return true;
    } catch (_) {
      return false;
    }
  }

  static Future<void> stopCall() async {
    try {
      await _android?.stopForegroundService();
    } catch (_) {}
  }

  @visibleForTesting
  static void reset() {
    _ready = false;
    _port?.close();
    _port = null;
    onOpen = null;
    onHangUp = null;
    onCallTap = null;
    onUpdateTap = null;
  }

  @visibleForTesting
  static void handleForTest(NotificationResponse response) => _handle(response);
}
