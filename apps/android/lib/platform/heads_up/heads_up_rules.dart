// The heads-up banner's rules, a port of apps/mobile/lib/heads-up.ts with the delivery rules of
// packages/core/src/chat-rows.ts (`headsUpAllowed`, `inQuietHours`, `attentionAlwaysShows`).
// Pure: the controller feeds it events and the shell snapshot; the background poll reuses the
// quiet-hours and urgency rules.
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../core/realtime/lonora_event.dart';
import '../../features/chats/chat_text.dart' show plainLine;
import '../../features/trading/recovery_link.dart';
import '../../state/app_state.dart';

/// One plain line, as Web and Expo cut it.
const headsUpMaxChars = 120;

/// The owner's quiet hours (reach-me policy), in minutes after midnight; crossing midnight
/// when [start] > [end]. No window, or start == end, means no quiet hours.
class QuietHours {
  const QuietHours({
    this.start,
    this.end,
    this.timezone = 'UTC',
    this.offsetMinutes,
  });

  final int? start;
  final int? end;
  final String timezone;

  /// [timezone]'s UTC offset as the phone resolved it, when it is not the phone's own zone
  /// (HeadsUpController); null reads the window on the phone's clock (or UTC's).
  final int? offsetMinutes;

  bool get utc => timezone == 'UTC' || timezone == 'Etc/UTC';

  QuietHours withOffset(int? minutes) => QuietHours(
    start: start,
    end: end,
    timezone: timezone,
    offsetMinutes: minutes,
  );

  /// `reach_me` of `GET /owner/profile` (minutes when the server sent them, else hours).
  static QuietHours? fromJson(Object? value) {
    final j = asJson(value);
    if (j.isEmpty) return null;
    int? minutes(String minute, String hour) {
      final m = asInt(j[minute]);
      if (m != null) return m;
      final h = asInt(j[hour]);
      return h == null ? null : h * 60;
    }

    return QuietHours(
      start: minutes('quiet_start_minute', 'quiet_start_hour'),
      end: minutes('quiet_end_minute', 'quiet_end_hour'),
      timezone: asStr(j['timezone'], 'UTC'),
      offsetMinutes: asInt(j['offset_minutes']),
    );
  }

  /// The policy's fields; `offset_minutes` only rides along in the background check's file.
  Json toJson() => {
    'quiet_start_minute': start,
    'quiet_end_minute': end,
    'timezone': timezone,
    'offset_minutes': ?offsetMinutes,
  };
}

/// Whether [now] falls in the owner's quiet hours, read in the policy's zone as Web and Expo
/// do (`Intl` with `policy.timezone`).
///
/// Dart has no time-zone database: a zone other than the phone's carries the offset the phone
/// resolved for it ([QuietHours.offsetMinutes]); otherwise the window reads on the phone's
/// clock (the owner's zone whenever the policy was saved from this phone, or an unknown zone),
/// and a policy kept in `UTC` on the UTC clock, as the server and Expo's fallback do.
bool inQuietHours(QuietHours? policy, DateTime now) {
  if (policy == null) return false;
  final start = policy.start, end = policy.end;
  if (start == null || end == null || start == end) return false;
  final offset = policy.offsetMinutes;
  final clock = offset != null
      ? now.toUtc().add(Duration(minutes: offset))
      : policy.utc
      ? now.toUtc()
      : now.toLocal();
  final minute = (clock.hour % 24) * 60 + clock.minute;
  return start < end
      ? minute >= start && minute < end
      : minute >= start || minute < end;
}

/// Critical and action-required items always show, quiet hours included (Q4, Q47).
bool attentionAlwaysShows(String? importance) =>
    importance == 'critical' || importance == 'action_required';

/// Mute and archive suppress a message's heads-up (`headsUpAllowed`).
bool headsUpAllowed(InboxEntry? entry) =>
    entry != null && !entry.muted && !entry.archived;

const brokerHealthCodes = {
  'broker_token_rejected',
  'broker_account_undeployed',
  'broker_connection_lost',
  'broker_rate_limited',
};

/// The owner's delivery rules: quiet hours and the agents whose in-app rule is off
/// (`GET /owner/profile` `reach_me`, `GET /agents/notifications`).
class DeliveryRules {
  const DeliveryRules({this.quiet, this.off = const {}});

  final QuietHours? quiet;
  final Set<String> off;

  static Set<String> offFrom(Object? notifications) => {
    for (final MapEntry(:key, :value) in asJson(notifications).entries)
      if (asJson(value)['in_app'] == false) key,
  };
}

enum HeadsUpKind {
  /// An agent's answer (the toast's default look, with the agent's avatar).
  message,

  /// An item that needs the owner (the notice look).
  attention,
}

/// What the banner shows: the conversation it opens, its words and who said them.
class HeadsUpBanner {
  const HeadsUpBanner({
    required this.threadId,
    required this.text,
    required this.kind,
    required this.key,
    this.agentId,
    this.groupId,
    this.who,
    this.around,
    this.location,
  });

  final String threadId;
  final String? agentId;
  final String? groupId;

  /// The speaker in a group, shown apart from the words («{speaker}:»).
  final String? who;
  final String text;
  final HeadsUpKind kind;

  /// The card's position for an attention item (opens the conversation there).
  final int? around;

  /// Identity of what is announced (message id or attention id).
  final String key;

  /// Where a tap goes instead of the conversation: «التعطل والاستعادة» for a broker health
  /// problem (apps/web shell/lists/HeadsUp.tsx), its button reading that page's name.
  final String? location;

  /// The same banner with other words (the preview switched off).
  HeadsUpBanner withText(String text, {String? who}) => HeadsUpBanner(
    threadId: threadId,
    agentId: agentId,
    groupId: groupId,
    text: text,
    who: who,
    kind: kind,
    key: key,
    around: around,
    location: location,
  );
}

/// An agent's answer in another chat: none for the open chat, a muted or archived chat, the
/// owner's quiet hours, an agent whose in-app rule is off, or anything from before the app
/// opened (5 s slack). (`messageBanner`, apps/mobile/lib/heads-up.ts:27-58)
HeadsUpBanner? messageBanner(
  LonoraEvent event, {
  required ShellState shell,
  required String? current,
  required DeliveryRules rules,
  required DateTime openedAt,
  required DateTime now,
  required String newMessage,
}) {
  final p = event.payload;
  if (event.kind != 'message.created' || p['role'] != 'assistant') return null;
  final threadId = asString(p['thread_id']) ?? event.threadId;
  if (threadId == null || threadId.isEmpty || threadId == current) return null;
  final created = asDate(p['created_at']) ?? event.createdAt;
  if (created == null ||
      created.isBefore(openedAt.subtract(const Duration(seconds: 5)))) {
    return null;
  }
  if (inQuietHours(rules.quiet, now)) return null;
  final entry = shell.entryFor(threadId);
  if (!headsUpAllowed(entry)) return null;
  final agentId = asString(p['agent_id']) ?? event.agentId;
  if (agentId != null && rules.off.contains(agentId)) return null;
  final content = plainLine(asStr(p['content']), max: headsUpMaxChars);
  final group = entry!.groupId;
  final speaker = group != null && agentId != null
      ? shell.agents[agentId]?.name
      : null;
  return HeadsUpBanner(
    threadId: threadId,
    agentId: entry.agentId ?? agentId,
    groupId: group,
    text: content.isEmpty ? newMessage : content,
    who: content.isEmpty || speaker == null ? null : '$speaker:',
    kind: HeadsUpKind.message,
    key: asStr(p['id'], 'event:${event.cursor}'),
  );
}

/// An urgent attention item (critical or action required) always shows, quiet hours
/// included, on its group's or agent's conversation; a broker health problem with no row of
/// its own on the personal agent's (`attentionBanner`, heads-up.ts:60-83). A broker health
/// problem's tap opens «التعطل والاستعادة» on its account (apps/web HeadsUp.tsx:190-207).
/// [title] is the item's catalog line (`attentionTitle`).
HeadsUpBanner? attentionBanner(
  Json item, {
  required ShellState shell,
  required DateTime openedAt,
  required String title,
}) {
  if (!attentionAlwaysShows(asString(item['importance']))) return null;
  final created = asDate(item['created_at']);
  if (created == null ||
      created.isBefore(openedAt.subtract(const Duration(seconds: 5)))) {
    return null;
  }
  final params = asJson(item['parameters']);
  final threadId = attentionThread(item, shell);
  if (threadId == null) return null;
  final text = plainLine(
    asString(params['summary'])?.trim().isNotEmpty == true
        ? asStr(params['summary'])
        : title,
    max: headsUpMaxChars,
  );
  if (text.isEmpty) return null;
  final entry = shell.entryFor(threadId);
  return HeadsUpBanner(
    threadId: threadId,
    agentId: entry?.agentId ?? asString(item['agent_id']),
    groupId: entry?.groupId,
    text: text,
    kind: HeadsUpKind.attention,
    key: asStr(item['id']),
    location: brokerHealthCodes.contains(asString(item['code']))
        ? recoveryLocation(account: attentionAccount(item))
        : null,
  );
}

/// The broker connection an attention item names (`parameters.account_id`), if any.
String? attentionAccount(Json item) =>
    asString(asJson(item['parameters'])['account_id']) ??
    asString(item['account_id']);

/// The conversation an attention item belongs to: its group's, its own thread, its agent's,
/// or — for a broker health problem without one — the personal agent's.
String? attentionThread(Json item, ShellState shell) {
  final params = asJson(item['parameters']);
  final groupId = asString(params['group_id']) ?? asString(item['group_id']);
  if (groupId != null) {
    final groupThread = shell.groups[groupId]?.threadId;
    if (groupThread != null) return groupThread;
    for (final e in shell.inbox) {
      if (e.groupId == groupId) return e.threadId;
    }
  }
  final own = asString(item['thread_id']);
  if (own != null && shell.entryFor(own) != null) return own;
  final agentId = asString(item['agent_id']);
  String? agentThread(String? id) {
    if (id == null) return null;
    for (final e in shell.inbox) {
      if (e.agentId == id && e.groupId == null) return e.threadId;
    }
    return null;
  }

  final found = agentThread(agentId);
  if (found != null) return found;
  if (brokerHealthCodes.contains(asString(item['code']))) {
    final personal = shell.orderedAgents.where((a) => a.isPersonal).firstOrNull;
    return agentThread(personal?.id);
  }
  return own;
}
