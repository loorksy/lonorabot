// What a Lonora notification carries and where its tap goes. Pure: unit-tested, and shared by
// the app isolate and the background (WorkManager) isolate.
//
// A payload names only a conversation, the card's position in it, or the call, never money
// facts and never an action: a tap opens the conversation, where the live record decides
// (apps/mobile/lib/push.native.ts:66-80, VISION 11.4). No notification approves anything.
import 'dart:convert';

import '../../app/routes.dart';
import '../../core/json.dart';

/// Android notification channels (created at start-up, names in the app's language).
abstract final class LnChannels {
  /// Agents' answers while the app is in the background.
  static const messages = 'messages';

  /// Owner decisions (approvals, secrets, mandates, broker health). Same id as the server's
  /// Expo push channel (`push.py` `channelId: "attention"`), so a future push lands there too.
  static const attention = 'attention';

  /// The ongoing voice call (foreground service, silent).
  static const calls = 'calls';

  /// Quiet notices: informational attention items, an available update.
  static const status = 'status';
}

/// Fixed notification ids (per-thread and per-item ids come from [notificationIdFor]).
abstract final class LnNotificationIds {
  static const messagesSummary = 1;
  static const attentionSummary = 2;
  static const call = 7001;
  static const update = 7002;
}

/// Android groups (one bundle per kind; each conversation is one notification in it).
abstract final class LnNotificationGroups {
  static const messages = 'ai.lonora.android.MESSAGES';
  static const attention = 'ai.lonora.android.ATTENTION';
}

enum NotificationTarget { thread, attention, agent, call, update }

/// The data a notification tap brings back.
class NotificationPayload {
  const NotificationPayload._(this.target, {this.id, this.around});

  const NotificationPayload.thread(String threadId, {int? around})
    : this._(NotificationTarget.thread, id: threadId, around: around);

  /// An attention item; [threadId] is the conversation holding its card, when known.
  const NotificationPayload.attention({String? threadId, int? around})
    : this._(NotificationTarget.attention, id: threadId, around: around);

  const NotificationPayload.agent(String agentId)
    : this._(NotificationTarget.agent, id: agentId);

  const NotificationPayload.call() : this._(NotificationTarget.call);

  /// An available update: the tap opens the update sheet (nothing installs from a tap).
  const NotificationPayload.update() : this._(NotificationTarget.update);

  final NotificationTarget target;
  final String? id;
  final int? around;

  String encode() =>
      jsonEncode({'t': target.name, 'id': ?id, 'around': ?around});

  /// Null for anything that is not a payload this app wrote (or carries an unsafe id).
  static NotificationPayload? decode(String? raw) {
    if (raw == null || raw.isEmpty) return null;
    Json j;
    try {
      j = asJson(jsonDecode(raw));
    } catch (_) {
      return null;
    }
    final target = NotificationTarget.values
        .where((t) => t.name == j['t'])
        .firstOrNull;
    if (target == null) return null;
    final id = asString(j['id']);
    if (id != null && !_safeId.hasMatch(id)) return null;
    final rawAround = asInt(j['around']);
    final around = rawAround != null && rawAround > 0 ? rawAround : null;
    return switch (target) {
      NotificationTarget.thread =>
        id == null ? null : NotificationPayload.thread(id, around: around),
      NotificationTarget.attention => NotificationPayload.attention(
        threadId: id,
        around: around,
      ),
      NotificationTarget.agent =>
        id == null ? null : NotificationPayload.agent(id),
      NotificationTarget.call => const NotificationPayload.call(),
      NotificationTarget.update => const NotificationPayload.update(),
    };
  }

  /// The route a tap opens; null for the call (its tap only brings the call back) and the
  /// update (its tap opens the update sheet).
  String? get location => switch (target) {
    NotificationTarget.thread => Routes.thread(id!, around: around),
    NotificationTarget.attention =>
      id == null ? Routes.attention : Routes.thread(id!, around: around),
    NotificationTarget.agent => Routes.agent(id!),
    NotificationTarget.call || NotificationTarget.update => null,
  };

  @override
  bool operator ==(Object other) =>
      other is NotificationPayload &&
      other.target == target &&
      other.id == id &&
      other.around == around;

  @override
  int get hashCode => Object.hash(target, id, around);

  @override
  String toString() => 'NotificationPayload(${encode()})';
}

/// Server ids are UUIDs; anything else never reaches the router.
final _safeId = RegExp(r'^[A-Za-z0-9_-]{1,80}$');

/// A stable positive 31-bit id for [key] (FNV-1a), the same in every isolate and every run
/// (`String.hashCode` is neither). Ids below 10 000 are reserved for [LnNotificationIds].
int notificationIdFor(String key) {
  var hash = 0x811c9dc5;
  for (final unit in utf8.encode(key)) {
    hash ^= unit;
    hash = (hash * 0x01000193) & 0xffffffff;
  }
  final id = hash & 0x7fffffff;
  return id < 10000 ? id + 10000 : id;
}

int threadNotificationId(String threadId) =>
    notificationIdFor('thread:$threadId');

int attentionNotificationId(String attentionId) =>
    notificationIdFor('attention:$attentionId');
