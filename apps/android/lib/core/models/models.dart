// Core Lonora domain models shared by every feature. Shapes follow the server contracts
// (docs/android/analysis/lonora-api-contract.md §5–§8). Every model keeps its `raw` JSON so
// feature code can read fields this file does not name, and so a newer server never loses data.
import '../json.dart';

class Agent {
  const Agent({
    required this.id,
    required this.name,
    this.title = '',
    this.description = '',
    this.avatar = 'orb',
    this.color,
    this.instructions = '',
    this.paused = false,
    this.tradingMode = 'ask',
    this.tradesOnItsOwn = false,
    this.role = 'general',
    this.scopeMode,
    this.scopeRevision = 0,
    this.tradingAccountId,
    this.tradingSymbol,
    this.parentId,
    this.createdAt,
    this.raw = const {},
  });

  final String id;
  final String name;
  final String title;
  final String description;
  final String avatar;
  final String? color;
  final String instructions;
  final bool paused;
  final String tradingMode;
  final bool tradesOnItsOwn;
  final String role;
  final String? scopeMode;
  final int scopeRevision;
  final String? tradingAccountId;
  final String? tradingSymbol;
  final String? parentId;
  final DateTime? createdAt;
  final Json raw;

  bool get isPersonal => role == 'personal';

  static Agent fromJson(Json j) => Agent(
    id: asStr(j['id']),
    name: asStr(j['name']),
    title: asStr(j['title']),
    description: asStr(j['description']),
    avatar: asString(j['avatar']) ?? 'orb',
    color: asString(j['color']),
    instructions: asStr(j['instructions']),
    paused: asBool(j['paused']),
    tradingMode: asString(j['trading_mode']) ?? 'ask',
    tradesOnItsOwn: asBool(j['trades_on_its_own']),
    role: asString(j['role']) ?? 'general',
    scopeMode: asString(j['scope_mode']),
    scopeRevision: asInt(j['scope_revision']) ?? 0,
    tradingAccountId: asString(j['trading_account_id']),
    tradingSymbol: asString(j['trading_symbol']),
    parentId: asString(j['parent_id']),
    createdAt: asDate(j['created_at']),
    raw: j,
  );
}

/// Generic server resource (`{id, kind, version, payload, ...}`) used by groups, skills,
/// routines, artifacts and others.
class Resource {
  const Resource({
    required this.id,
    required this.kind,
    required this.version,
    required this.payload,
    this.createdAt,
    this.updatedAt,
    this.raw = const {},
  });

  final String id;
  final String kind;
  final int version;
  final Json payload;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final Json raw;

  static Resource fromJson(Json j) => Resource(
    id: asStr(j['id']),
    kind: asStr(j['kind']),
    version: asInt(j['version']) ?? 0,
    payload: asJson(j['payload']),
    createdAt: asDate(j['created_at']),
    updatedAt: asDate(j['updated_at']),
    raw: j,
  );
}

class Group {
  const Group({
    required this.id,
    required this.name,
    required this.memberIds,
    this.threadId,
    this.version = 0,
    this.leadAgentId,
    this.raw = const {},
  });

  final String id;
  final String name;
  final List<String> memberIds;
  final String? threadId;
  final int version;
  final String? leadAgentId;
  final Json raw;

  static Group fromJson(Json j) {
    final payload = asJson(j['payload']);
    final source = payload.isEmpty ? j : payload;
    return Group(
      id: asStr(j['id']),
      name: asStr(source['name']),
      memberIds: asStringList(source['member_ids']),
      // The server keeps a group's conversation in `state.thread_id` (web groups.ts).
      threadId:
          _nonEmpty(asString(asJson(j['state'])['thread_id'])) ??
          asString(j['thread_id']) ??
          asString(source['thread_id']),
      version: asInt(j['version']) ?? 0,
      leadAgentId: asString(source['lead_agent_id']),
      raw: j,
    );
  }
}

class Thread {
  const Thread({
    required this.id,
    this.agentId,
    this.groupId,
    this.title = '',
    this.webSearch = false,
    this.createdAt,
    this.raw = const {},
  });

  final String id;
  final String? agentId;
  final String? groupId;
  final String title;
  final bool webSearch;
  final DateTime? createdAt;
  final Json raw;

  static Thread fromJson(Json j) => Thread(
    id: asStr(j['id']),
    agentId: asString(j['agent_id']),
    groupId: asString(j['group_id']),
    title: asStr(j['title']),
    webSearch: asBool(asJson(j['options'])['web_search']),
    createdAt: asDate(j['created_at']),
    raw: j,
  );

  Thread copyWith({bool? webSearch}) => Thread(
    id: id,
    agentId: agentId,
    groupId: groupId,
    title: title,
    webSearch: webSearch ?? this.webSearch,
    createdAt: createdAt,
    raw: raw,
  );
}

class InboxLastMessage {
  const InboxLastMessage({
    required this.id,
    required this.role,
    this.agentId,
    this.content = '',
    this.preview = '',
    this.kind = 'text',
    this.seq = 0,
    this.createdAt,
    this.consumed,
    this.attachmentCount = 0,
  });

  final String id;
  final String role;
  final String? agentId;
  final String content;
  final String preview;
  final String kind;
  final int seq;
  final DateTime? createdAt;
  final bool? consumed;
  final int attachmentCount;

  static InboxLastMessage? fromJson(Object? value) {
    final j = asJson(value);
    if (j.isEmpty) return null;
    return InboxLastMessage(
      id: asStr(j['id']),
      role: asStr(j['role'], 'assistant'),
      agentId: asString(j['agent_id']),
      content: asStr(j['content']),
      preview: asStr(j['preview']),
      kind: asStr(j['kind'], 'text'),
      seq: asInt(j['seq']) ?? 0,
      createdAt: asDate(j['created_at']),
      consumed: j['consumed'] is bool ? j['consumed'] as bool : null,
      attachmentCount: asInt(asJson(j['attachments'])['count']) ?? 0,
    );
  }
}

class InboxEntry {
  const InboxEntry({
    required this.threadId,
    this.agentId,
    this.groupId,
    this.lastMessage,
    this.lastActivityAt,
    this.unreadCount = 0,
    this.lastReadSeq = 0,
    this.markedUnread = false,
    this.muted = false,
    this.archived = false,
    this.favourite = false,
    this.pinnedOrder,
    this.hiddenBeforeSeq = 0,
    this.raw = const {},
  });

  final String threadId;
  final String? agentId;
  final String? groupId;
  final InboxLastMessage? lastMessage;
  final DateTime? lastActivityAt;
  final int unreadCount;
  final int lastReadSeq;
  final bool markedUnread;
  final bool muted;
  final bool archived;
  final bool favourite;
  final int? pinnedOrder;
  final int hiddenBeforeSeq;
  final Json raw;

  bool get pinned => pinnedOrder != null;

  static InboxEntry fromJson(Json j) => InboxEntry(
    threadId: asStr(j['thread_id']),
    agentId: asString(j['agent_id']),
    groupId: asString(j['group_id']),
    lastMessage: InboxLastMessage.fromJson(j['last_message']),
    lastActivityAt: asDate(j['last_activity_at']),
    unreadCount: asInt(j['unread_count']) ?? 0,
    lastReadSeq: asInt(j['last_read_seq']) ?? 0,
    markedUnread: asBool(j['marked_unread']),
    muted: asBool(j['muted']),
    archived: asBool(j['archived']),
    favourite: asBool(j['favourite']),
    pinnedOrder: asInt(j['pinned_order']),
    hiddenBeforeSeq: asInt(j['hidden_before_seq']) ?? 0,
    raw: j,
  );

  /// Applies a `ThreadPrefs` payload (thread.read / thread.prefs_updated events).
  InboxEntry withPrefs(Json prefs) {
    final merged = {...raw};
    for (final key in const [
      'last_read_seq',
      'marked_unread',
      'muted',
      'archived',
      'favourite',
      'pinned_order',
      'hidden_before_seq',
    ]) {
      if (prefs.containsKey(key)) merged[key] = prefs[key];
    }
    final lastSeq = lastMessage?.seq ?? 0;
    final read = asInt(merged['last_read_seq']) ?? lastReadSeq;
    if (prefs.containsKey('last_read_seq') && read >= lastSeq) {
      merged['unread_count'] = 0;
    }
    return InboxEntry.fromJson(merged);
  }
}

class ChatList {
  const ChatList({
    required this.id,
    required this.name,
    this.position = 0,
    this.threadIds = const [],
    this.raw = const {},
  });

  final String id;
  final String name;
  final int position;
  final List<String> threadIds;
  final Json raw;

  static ChatList fromJson(Json j) => ChatList(
    id: asStr(j['id']),
    name: asStr(j['name']),
    position: asInt(j['position']) ?? 0,
    threadIds: asStringList(j['thread_ids']),
    raw: j,
  );
}

class Reaction {
  const Reaction({required this.reactor, required this.emoji, this.createdAt});

  final String reactor;
  final String emoji;
  final DateTime? createdAt;

  static Reaction fromJson(Json j) => Reaction(
    reactor: asStr(j['reactor']),
    emoji: asStr(j['emoji']),
    createdAt: asDate(j['created_at']),
  );
  Json toJson() => {
    'reactor': reactor,
    'emoji': emoji,
    'created_at': createdAt?.toUtc().toIso8601String(),
  };
}

/// The six reactions the server accepts (packages/contracts/src/domain.ts:45-47).
const reactionEmojis = ['👍', '❤️', '😂', '😮', '😢', '🙏'];

class Message {
  const Message({
    required this.id,
    required this.threadId,
    required this.role,
    this.agentId,
    this.seq = 0,
    this.content = '',
    this.richContent,
    this.replyTo,
    this.mentionAgentIds = const [],
    this.mentionAll = false,
    this.attachmentIds = const [],
    this.createdAt,
    this.clientNonce,
    this.origin = 'owner',
    this.uiSubmit,
    this.uiState,
    this.suggestedReply,
    this.editedFrom,
    this.supersededBy,
    this.reactions = const [],
    this.consumed,
    this.raw = const {},
  });

  final String id;
  final String threadId;
  final String role;
  final String? agentId;
  final int seq;
  final String content;
  final Json? richContent;
  final String? replyTo;
  final List<String> mentionAgentIds;
  final bool mentionAll;
  final List<String> attachmentIds;
  final DateTime? createdAt;
  final String? clientNonce;
  final String origin;
  final Json? uiSubmit;
  final Json? uiState;
  final String? suggestedReply;
  final String? editedFrom;
  final String? supersededBy;
  final List<Reaction> reactions;
  final bool? consumed;
  final Json raw;

  bool get fromOwner => role == 'user';
  bool get fromAgent => role == 'assistant';

  List<Json> get parts => asJsonList(richContent?['parts']);

  static Message fromJson(Json j) {
    final mentions = asJson(j['mentions']);
    final rich = asJson(j['rich_content']);
    return Message(
      id: asStr(j['id']),
      threadId: asStr(j['thread_id']),
      role: asStr(j['role'], 'assistant'),
      agentId: asString(j['agent_id']),
      seq: asInt(j['seq']) ?? 0,
      content: asStr(j['content']),
      richContent: rich.isEmpty ? null : rich,
      replyTo: asString(j['reply_to']),
      mentionAgentIds: asStringList(mentions['agent_ids']),
      mentionAll: asBool(mentions['all']),
      attachmentIds: asStringList(j['attachment_ids']),
      createdAt: asDate(j['created_at']),
      clientNonce: asString(j['client_nonce']),
      origin: asStr(j['origin'], 'owner'),
      uiSubmit: j['ui_submit'] is Map ? asJson(j['ui_submit']) : null,
      uiState: j['ui_state'] is Map ? asJson(j['ui_state']) : null,
      suggestedReply: asString(j['suggested_reply']),
      editedFrom: asString(j['edited_from']),
      supersededBy: asString(j['superseded_by']),
      reactions: asJsonList(j['reactions'])
          .map(Reaction.fromJson)
          .toList(growable: false),
      consumed: j['consumed'] is bool ? j['consumed'] as bool : null,
      raw: j,
    );
  }

  Json toJson() => raw;

  Message withReactions(List<Reaction> value) => Message.fromJson({
    ...raw,
    'reactions': value.map((r) => r.toJson()).toList(),
  });
}

class InputChoice {
  const InputChoice({required this.id, required this.label});
  final String id;
  final String label;
}

class InputRequest {
  const InputRequest({
    required this.id,
    required this.runId,
    required this.question,
    required this.choices,
    this.messageId,
    this.status = 'pending',
    this.selectedChoiceId,
  });

  final String id;
  final String runId;
  final String? messageId;
  final String question;
  final List<InputChoice> choices;
  final String status;
  final String? selectedChoiceId;

  bool get pending => status == 'pending';

  static InputRequest fromJson(Json j) => InputRequest(
    id: asStr(j['id']),
    runId: asStr(j['run_id']),
    messageId: asString(j['message_id']),
    question: asStr(j['question']),
    choices: asJsonList(j['choices'])
        .map((c) => InputChoice(id: asStr(c['id']), label: asStr(c['label'])))
        .toList(growable: false),
    status: asStr(j['status'], 'pending'),
    selectedChoiceId: asString(j['selected_choice_id']),
  );
}

class Run {
  const Run({
    required this.id,
    required this.threadId,
    required this.agentId,
    required this.status,
    this.parentRunId,
    this.trigger = 'user',
    this.background = false,
    this.inputSeq,
    this.errorCode,
    this.failure,
    this.result,
    this.modelMetadata = const {},
    this.stream,
    this.inputRequests = const [],
    this.createdAt,
    this.updatedAt,
    this.raw = const {},
  });

  final String id;
  final String threadId;
  final String agentId;
  final String status;
  final String? parentRunId;
  final String trigger;
  final bool background;
  final int? inputSeq;
  final String? errorCode;
  final Json? failure;
  final String? result;
  final Json modelMetadata;
  final Json? stream;
  final List<InputRequest> inputRequests;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final Json raw;

  static const terminal = {'completed', 'failed', 'cancelled'};
  static const active = {'queued', 'leased', 'running'};

  bool get isTerminal => terminal.contains(status);
  bool get isActive => active.contains(status);
  bool get waiting => status == 'waiting_input' || status == 'waiting_takeover';

  static Run fromJson(Json j) => Run(
    id: asStr(j['id']),
    threadId: asStr(j['thread_id']),
    agentId: asStr(j['agent_id']),
    status: asStr(j['status'], 'queued'),
    parentRunId: asString(j['parent_run_id']),
    trigger: asStr(j['trigger'], 'user'),
    background: asBool(j['background']),
    inputSeq: asInt(j['input_seq']),
    errorCode: asString(j['error_code']),
    failure: j['failure'] is Map ? asJson(j['failure']) : null,
    result: asString(j['result']),
    modelMetadata: asJson(j['model_metadata']),
    stream: j['stream'] is Map ? asJson(j['stream']) : null,
    inputRequests: asJsonList(j['input_requests'])
        .map(InputRequest.fromJson)
        .toList(growable: false),
    createdAt: asDate(j['created_at']),
    updatedAt: asDate(j['updated_at']),
    raw: j,
  );

  Run withStatus(String value, {Json? extra}) =>
      Run.fromJson({...raw, 'status': value, ...?extra});
}

class Owner {
  const Owner({required this.id, required this.email});
  final String id;
  final String email;
}

String? _nonEmpty(String? s) => s == null || s.isEmpty ? null : s;
