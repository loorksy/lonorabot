// The background check's decisions, pure (unit-tested): what changed since the stored cursor
// in `GET /threads/inbox` and `GET /attention`, which of it becomes a local notification, and
// the next cursor.
//
// Lonora's server pushes only through Expo (lonora-api-contract.md §15), so this app has no
// push: while it is in the background a WorkManager task reads these two endpoints at most
// every 15 minutes and posts local notifications. The rules are the in-app ones (heads-up
// rules of apps/mobile/lib/heads-up.ts): an agent's answer in a chat that is not muted or
// archived, not read elsewhere, from an agent whose in-app rule is on, outside quiet hours;
// an urgent attention item always.
import '../../core/json.dart';
import '../../features/chats/chat_text.dart' show plainLine;
import '../heads_up/heads_up_rules.dart';
import '../notifications/notification_payload.dart';

/// The attention codes the server would push (packages/gateway/src/lonora_gateway/push.py
/// `PUSH_CODES`): they use the high-importance attention channel even when the item's
/// importance is lower.
const pushAttentionCodes = {
  'approval_required',
  'operation_uncertain',
  'secret_requested',
  'mandate_proposed',
  ...brokerHealthCodes,
  'gateway_stopped',
  'model_access_failed',
};

/// Lines kept in one conversation's notification (newest last).
const maxNotificationLines = 5;
const _maxSeenAttention = 300;

/// The foreground counts as present while its heartbeat is this fresh: a background run then
/// skips (the live feed and the heads-up banners cover it).
const foregroundFresh = Duration(minutes: 3);

class NoteLine {
  const NoteLine(this.text, {this.who});
  final String text;
  final String? who;

  Json toJson() => {'t': text, 'w': ?who};
  static NoteLine fromJson(Json j) =>
      NoteLine(asStr(j['t']), who: asString(j['w']));

  @override
  bool operator ==(Object other) =>
      other is NoteLine && other.text == text && other.who == who;
  @override
  int get hashCode => Object.hash(text, who);
}

/// What the background check remembers between runs (a small JSON file; never a token).
class PollState {
  const PollState({
    required this.ownerId,
    required this.server,
    required this.since,
    this.seqs = const {},
    this.seenAttention = const [],
    this.notified = const {},
    this.notifiedAttention = const {},
    this.titles = const {},
    this.agentNames = const {},
    this.lang = 'ar',
    this.quiet,
    this.off = const {},
    this.foregroundAt,
  });

  final String ownerId;
  final String server;

  /// Nothing created before this is news (the last time the owner had the app open).
  final DateTime since;

  /// Last seen `last_message.seq` per conversation.
  final Map<String, int> seqs;
  final List<String> seenAttention;

  /// Lines of each conversation's live notification.
  final Map<String, List<NoteLine>> notified;

  /// Attention ids with a live notification.
  final Set<String> notifiedAttention;

  /// Conversation names (agent or group) and agent names, cached by the foreground.
  final Map<String, String> titles;
  final Map<String, String> agentNames;
  final String lang;
  final QuietHours? quiet;
  final Set<String> off;

  /// The foreground's heartbeat; null once the app went to the background.
  final DateTime? foregroundAt;

  bool foregroundActive(DateTime now) =>
      foregroundAt != null && now.difference(foregroundAt!) < foregroundFresh;

  PollState copyWith({
    DateTime? since,
    Map<String, int>? seqs,
    List<String>? seenAttention,
    Map<String, List<NoteLine>>? notified,
    Set<String>? notifiedAttention,
    Map<String, String>? titles,
    Map<String, String>? agentNames,
    String? lang,
    Object? quiet = _keep,
    Set<String>? off,
    Object? foregroundAt = _keep,
  }) => PollState(
    ownerId: ownerId,
    server: server,
    since: since ?? this.since,
    seqs: seqs ?? this.seqs,
    seenAttention: seenAttention ?? this.seenAttention,
    notified: notified ?? this.notified,
    notifiedAttention: notifiedAttention ?? this.notifiedAttention,
    titles: titles ?? this.titles,
    agentNames: agentNames ?? this.agentNames,
    lang: lang ?? this.lang,
    quiet: identical(quiet, _keep) ? this.quiet : quiet as QuietHours?,
    off: off ?? this.off,
    foregroundAt: identical(foregroundAt, _keep)
        ? this.foregroundAt
        : foregroundAt as DateTime?,
  );

  Json toJson() => {
    'v': 1,
    'owner': ownerId,
    'server': server,
    'since': since.toUtc().toIso8601String(),
    'seqs': seqs,
    'seen_attention': seenAttention,
    'notified': {
      for (final MapEntry(:key, :value) in notified.entries)
        key: [for (final l in value) l.toJson()],
    },
    'notified_attention': notifiedAttention.toList(),
    'titles': titles,
    'agent_names': agentNames,
    'lang': lang,
    'quiet': quiet?.toJson(),
    'off': off.toList(),
    'foreground_at': foregroundAt?.toUtc().toIso8601String(),
  };

  static PollState? fromJson(Object? value) {
    final j = asJson(value);
    final owner = asString(j['owner']);
    final server = asString(j['server']);
    final since = asDate(j['since']);
    if (owner == null || server == null || since == null) return null;
    return PollState(
      ownerId: owner,
      server: server,
      since: since,
      seqs: {
        for (final MapEntry(:key, :value) in asJson(j['seqs']).entries)
          if (asInt(value) case final int seq) key: seq,
      },
      seenAttention: asStringList(j['seen_attention']),
      notified: {
        for (final MapEntry(:key, :value) in asJson(j['notified']).entries)
          key: asJsonList(value).map(NoteLine.fromJson).toList(),
      },
      notifiedAttention: asStringList(j['notified_attention']).toSet(),
      titles: asJson(j['titles']).map((k, v) => MapEntry(k, asStr(v))),
      agentNames: asJson(j['agent_names']).map((k, v) => MapEntry(k, asStr(v))),
      lang: asStr(j['lang'], 'ar'),
      quiet: QuietHours.fromJson(j['quiet']),
      off: asStringList(j['off']).toSet(),
      foregroundAt: asDate(j['foreground_at']),
    );
  }
}

const _keep = Object();

enum PlannedKind { message, attention }

/// One local notification to post (or update in place: same [id]).
class PlannedNotification {
  const PlannedNotification({
    required this.kind,
    required this.id,
    required this.channel,
    required this.title,
    required this.lines,
    required this.payload,
    this.threadId,
    this.count = 1,
    this.groupConversation = false,
    this.when,
  });

  final PlannedKind kind;
  final int id;
  final String channel;
  final String title;
  final List<NoteLine> lines;
  final NotificationPayload payload;
  final String? threadId;
  final int count;
  final bool groupConversation;
  final DateTime? when;

  String get body => lines.isEmpty ? '' : lines.last.text;
}

class PollResult {
  const PollResult({
    required this.next,
    this.notes = const [],
    this.clearThreads = const [],
    this.clearAttention = const [],
  });

  final PollState next;
  final List<PlannedNotification> notes;

  /// Conversations read elsewhere: their notification goes.
  final List<String> clearThreads;

  /// Attention items no longer waiting: their notification goes.
  final List<String> clearAttention;
}

/// The cursor of a first run (no stored state, or another owner): everything that exists now
/// is the baseline and nothing is announced.
PollState baselineState({
  required String ownerId,
  required String server,
  required List<Json> inbox,
  required List<Json> attention,
  required DateTime now,
  PollState? previous,
}) {
  final keep =
      previous != null &&
          previous.ownerId == ownerId &&
          previous.server == server
      ? previous
      : null;
  return PollState(
    ownerId: ownerId,
    server: server,
    since: now,
    seqs: {
      for (final row in inbox)
        if (asString(row['thread_id']) case final String id)
          id: asInt(asJson(row['last_message'])['seq']) ?? 0,
    },
    seenAttention: [
      for (final item in attention)
        if (asString(item['id']) case final String id) id,
    ],
    titles: keep?.titles ?? const {},
    agentNames: keep?.agentNames ?? const {},
    lang: keep?.lang ?? 'ar',
    quiet: keep?.quiet,
    off: keep?.off ?? const {},
  );
}

/// One background check: compares [inbox] and [attention] with [state].
///
/// [attentionText] is the catalog line of an attention code (`attentionTitle`);
/// [newMessage] the line of an answer without words (a voice note, a card).
PollResult computePoll(
  PollState state, {
  required List<Json> inbox,
  required List<Json> attention,
  required DateTime now,
  required String Function(String code, Json item) attentionText,
  required String newMessage,
  String fallbackTitle = 'Lonora',
}) {
  final quiet = inQuietHours(state.quiet, now);
  final seqs = {...state.seqs};
  final notified = {...state.notified};
  final notes = <PlannedNotification>[];
  final clearThreads = <String>[];

  for (final row in inbox) {
    final threadId = asString(row['thread_id']);
    if (threadId == null) continue;
    final unread = asInt(row['unread_count']) ?? 0;
    if (unread == 0 && notified.containsKey(threadId)) {
      notified.remove(threadId);
      clearThreads.add(threadId);
    }
    final last = asJson(row['last_message']);
    final seq = asInt(last['seq']);
    if (seq == null) continue;
    final previous = state.seqs[threadId];
    if (previous != null && seq <= previous) continue;
    seqs[threadId] = seq;
    if (last['role'] != 'assistant' || unread == 0) continue;
    if (asBool(row['muted']) || asBool(row['archived'])) continue;
    final created = asDate(last['created_at']);
    if (created == null || created.isBefore(state.since)) continue;
    final agentId = asString(last['agent_id']);
    if (agentId != null && state.off.contains(agentId)) continue;
    if (quiet) continue;
    final words = plainLine(
      asStr(last['content'], asStr(last['preview'])),
      max: headsUpMaxChars,
    );
    final group = asString(row['group_id']) != null;
    final speaker = group && agentId != null ? state.agentNames[agentId] : null;
    final line = NoteLine(words.isEmpty ? newMessage : words, who: speaker);
    final lines = [...?notified[threadId], line];
    final kept = lines.length > maxNotificationLines
        ? lines.sublist(lines.length - maxNotificationLines)
        : lines;
    notified[threadId] = kept;
    notes.add(
      PlannedNotification(
        kind: PlannedKind.message,
        id: threadNotificationId(threadId),
        channel: LnChannels.messages,
        title: _title(
          state,
          threadId,
          asString(row['agent_id']),
          fallbackTitle,
        ),
        lines: kept,
        payload: NotificationPayload.thread(threadId),
        threadId: threadId,
        count: unread,
        groupConversation: group,
        when: created,
      ),
    );
  }

  final seen = [...state.seenAttention];
  final seenSet = seen.toSet();
  final notifiedAttention = {...state.notifiedAttention};
  final live = <String>{};
  for (final item in attention) {
    final id = asString(item['id']);
    if (id == null) continue;
    live.add(id);
    if (!seenSet.add(id)) continue;
    seen.add(id);
    final created = asDate(item['created_at']);
    if (created == null || created.isBefore(state.since)) continue;
    final code = asStr(item['code']);
    final urgent =
        attentionAlwaysShows(asString(item['importance'])) ||
        pushAttentionCodes.contains(code);
    if (!urgent && quiet) continue;
    final params = asJson(item['parameters']);
    final summary = asStr(params['summary']).trim();
    final text = plainLine(
      summary.isNotEmpty ? summary : attentionText(code, item),
      max: headsUpMaxChars,
    );
    if (text.isEmpty) continue;
    final threadId = asString(item['thread_id']);
    notifiedAttention.add(id);
    notes.add(
      PlannedNotification(
        kind: PlannedKind.attention,
        id: attentionNotificationId(id),
        channel: urgent ? LnChannels.attention : LnChannels.status,
        title: _title(
          state,
          threadId,
          asString(item['agent_id']),
          fallbackTitle,
        ),
        lines: [NoteLine(text)],
        // A broker health problem opens «التعطل والاستعادة» (the heads-up's own target).
        payload: brokerHealthCodes.contains(code)
            ? NotificationPayload.recovery(account: attentionAccount(item))
            : NotificationPayload.attention(threadId: threadId),
        threadId: threadId,
        when: created,
      ),
    );
  }
  final clearAttention = [
    for (final id in notifiedAttention)
      if (!live.contains(id)) id,
  ];
  notifiedAttention.removeAll(clearAttention);
  final trimmed = seen.length > _maxSeenAttention
      ? seen.sublist(seen.length - _maxSeenAttention)
      : seen;

  return PollResult(
    next: state.copyWith(
      seqs: seqs,
      notified: notified,
      seenAttention: trimmed,
      notifiedAttention: notifiedAttention,
    ),
    notes: notes,
    clearThreads: clearThreads,
    clearAttention: clearAttention,
  );
}

String _title(
  PollState state,
  String? threadId,
  String? agentId,
  String fallback,
) {
  final byThread = threadId == null ? null : state.titles[threadId];
  if (byThread != null && byThread.isNotEmpty) return byThread;
  final byAgent = agentId == null ? null : state.agentNames[agentId];
  if (byAgent != null && byAgent.isNotEmpty) return byAgent;
  return fallback;
}
