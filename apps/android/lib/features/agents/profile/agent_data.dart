// Screen-local reads and writes of one agent's own records for the profile, settings and memory
// pages (lonora-api-contract §8–§11). Nothing else in the app keeps them, so they are plain
// calls on `api`; the agent row itself goes back into the shell store after a change.
import 'package:flutter/foundation.dart';

import '../../../app/services.dart';
import '../../../core/json.dart';
import '../../../core/models/models.dart';
import '../../../l10n/l10n.dart';

String _enc(String value) => Uri.encodeComponent(value);

/// `GET /agents/{id}`.
Future<Agent> fetchAgent(String id) async =>
    Agent.fromJson(asJson(await api.get('/agents/${_enc(id)}')));

/// `PATCH /agents/{id}` with only the fields that change (`AgentUpdate`, partial).
Future<Agent> patchAgent(String id, Json body) async =>
    Agent.fromJson(asJson(await api.patch('/agents/${_enc(id)}', body)));

/// `DELETE /agents/{id}`: refused for the personal agent and while its trade is uncertain.
Future<void> deleteAgent(String id) => api.delete('/agents/${_enc(id)}');

/// `GET /agents/{id}/state` (`AgentLiveState`, presentation only).
Future<Json> fetchAgentState(String id) async =>
    asJson(await api.get('/agents/${_enc(id)}/state'));

/// The agent's template (not a named field of [Agent]).
String? agentTemplate(Agent agent) => asString(agent.raw['template']);

/// A trading agent: the trading template, or a team agent bound to an account
/// (apps/web/src/shell/agent/shared.tsx `isTrader`).
bool isTrader(Agent agent) =>
    agentTemplate(agent) == 'trading' ||
    (agent.role != 'personal' &&
        agent.role != 'delegated' &&
        (agent.tradingAccountId ?? '').isNotEmpty);

/// Whether the agent shows a trading mode (packages/core/src/agent-permission.ts
/// `showsTradingControl`). Presentation only.
bool showsTradingControl(Agent agent, {bool? hasTradingAccount}) {
  if (agent.role == 'delegated' || agentTemplate(agent) == 'research') {
    return false;
  }
  if ((agent.tradingAccountId ?? '').isNotEmpty) {
    return hasTradingAccount ?? true;
  }
  return agent.role == 'personal' && hasTradingAccount == true;
}

/// An agent's role line: its title or description; the personal agent's is «مساعدك الشخصي».
String agentRoleLine(L10n l10n, Agent agent) => agent.title.isNotEmpty
    ? agent.title
    : agent.description.isNotEmpty
    ? agent.description
    : agent.isPersonal
    ? l10n.t('sh_personalRole')
    : '';

// Watches (`/watches`, generic resources) ----------------------------------------------------

/// One market watch as `GET /watches?agent_id=` lists it.
@immutable
class Watch {
  const Watch({
    required this.id,
    required this.payload,
    required this.state,
    required this.version,
  });

  factory Watch.fromJson(Json j) => Watch(
    id: asStr(j['id']),
    payload: asJson(j['payload']),
    state: asJson(j['state']),
    version: asInt(j['version']) ?? 0,
  );

  final String id;
  final Json payload;
  final Json state;
  final int version;

  bool get paused => state['code'] == 'watch_paused';

  /// Shown while enabled or paused (apps/web AgentPage.tsx `shownWatches`).
  bool get shown => payload['enabled'] != false || paused;

  /// Watching now: the switch of a conditional schedule.
  bool get on => payload['enabled'] != false && !paused;

  /// The owner's wake prompt (a conditional schedule's task).
  String get prompt => asStr(payload['prompt']);

  /// A conditional schedule in the schedules list: it has a prompt and is neither cancelled
  /// nor expired (apps/web SchedulesPages.tsx `listedWatch`).
  bool listed(DateTime now) {
    final expires = asDate(payload['expires_at']);
    return prompt.isNotEmpty &&
        state['code'] != 'watch_cancelled' &&
        state['lifecycle'] != 'expired' &&
        (expires == null || expires.isAfter(now));
  }
}

Future<List<Watch>> fetchWatches(String agentId) async =>
    asJsonList(await api.get('/watches', query: {'agent_id': agentId}))
        .map(Watch.fromJson)
        .toList();

/// «الشرط»: a price level and its side, e.g. «تحت 2330» or "above 2350" (above by default);
/// null without a number (apps/web SchedulesPages.tsx `parseCondition`).
({String level, bool below})? parsePriceCondition(String value) {
  final digits = value
      .replaceAllMapped(
        RegExp('[٠-٩]'),
        (m) => String.fromCharCode(m[0]!.codeUnitAt(0) - 0x0660 + 0x30),
      )
      .replaceAll('٫', '.');
  final level = RegExp(r'\d+(?:[.,]\d+)?').firstMatch(digits)?[0];
  if (level == null) return null;
  return (
    level: level.replaceFirst(',', '.'),
    below: RegExp(
      r'(تحت|أقل|دون|below|under|<)',
      caseSensitive: false,
    ).hasMatch(value),
  );
}

/// Whether [agent] can be woken by a price condition: a trading agent with its account and
/// symbol (apps/web SchedulesPages.tsx `canWatch`).
bool canWatchPrice(Agent agent) =>
    isTrader(agent) &&
    (agent.tradingAccountId ?? '').isNotEmpty &&
    (agent.tradingSymbol ?? '').isNotEmpty;

/// «عند تحقق شرط»: a market watch that wakes the agent with [prompt]. It carries no trading
/// authority (`POST /watches`, apps/web domain/api.ts `createWatch`).
Future<void> createPriceWatch(
  Agent agent, {
  required String level,
  required bool below,
  required String prompt,
}) => api.post('/watches', {
  'agent_id': agent.id,
  'payload': {
    'kind': 'price',
    'account_id': agent.tradingAccountId,
    'symbol': agent.tradingSymbol,
    'condition': below ? 'below' : 'above',
    'level': level,
    'prompt': prompt,
  },
});

/// `POST /watches/{id}/control {action: pause|resume|cancel}`.
Future<void> controlWatch(String id, String action) =>
    api.post('/watches/${_enc(id)}/control', {'action': action});

// Mandate (trading mode Full / Ask) ------------------------------------------------------------

/// The agent's live Mandate card or null. Reading never raises one.
Future<Json?> fetchMandate(String agentId) async {
  final card = await api.get(
    '/owner-actions/mandate',
    query: {'agent_id': agentId},
  );
  return card is Map ? asJson(card) : null;
}

/// Raises (or returns) the agent's Mandate card.
Future<Json> raiseMandate(String agentId) async => asJson(
  await api.post('/owner-actions/mandate?agent_id=${_enc(agentId)}', {}),
);

/// Applies the mode the owner's tap chose on that card. Only the Mandate card sets Full.
Future<Json> decideMandate(String cardId, String mode) async => asJson(
  await api.post('/owner-actions/${_enc(cardId)}/decision', {
    'decision': 'confirm',
    'trading_mode': mode,
  }),
);

/// The other mode a reopen offers; null when the agent has no mode
/// (apps/mobile/lib/mandate-mode.ts `otherTradingMode`).
String? otherTradingMode(String? mode) => switch (mode) {
  'full' => 'ask',
  'ask' => 'full',
  _ => null,
};

/// The mode a decision response applied: Full only when it says Full
/// (apps/mobile/lib/mandate-mode.ts `appliedTradingMode`).
String appliedTradingMode(Json? result) =>
    result?['trading_mode'] == 'full' ? 'full' : 'ask';

// Delivery rules ----------------------------------------------------------------------------------

/// `AgentDeliveryRules`: in-app messages, agent calls and a daily limit (null = none).
@immutable
class DeliveryRules {
  const DeliveryRules({
    required this.inApp,
    required this.calls,
    this.dailyLimit,
  });

  factory DeliveryRules.fromJson(Json j) => DeliveryRules(
    inApp: asBool(j['in_app'], true),
    calls: asBool(j['calls'], true),
    dailyLimit: asInt(j['daily_limit']),
  );

  final bool inApp;
  final bool calls;
  final int? dailyLimit;

  Json toJson() => {'in_app': inApp, 'calls': calls, 'daily_limit': dailyLimit};

  DeliveryRules copyWith({bool? inApp, bool? calls, Object? dailyLimit = _k}) =>
      DeliveryRules(
        inApp: inApp ?? this.inApp,
        calls: calls ?? this.calls,
        dailyLimit: identical(dailyLimit, _k)
            ? this.dailyLimit
            : dailyLimit as int?,
      );

  @override
  bool operator ==(Object other) =>
      other is DeliveryRules &&
      other.inApp == inApp &&
      other.calls == calls &&
      other.dailyLimit == dailyLimit;

  @override
  int get hashCode => Object.hash(inApp, calls, dailyLimit);
}

const _k = Object();

Future<DeliveryRules> fetchDeliveryRules(String agentId) async =>
    DeliveryRules.fromJson(
      asJson(await api.get('/agents/${_enc(agentId)}/notifications')),
    );

Future<DeliveryRules> saveDeliveryRules(
  String agentId,
  DeliveryRules rules,
) async => DeliveryRules.fromJson(
  asJson(
    await api.put('/agents/${_enc(agentId)}/notifications', rules.toJson()),
  ),
);

// Model ----------------------------------------------------------------------------------------

/// `GET /agents/{id}/model/summary`, kept as JSON for the ported core text helpers.
Future<Json> fetchModelSummary(String agentId) async =>
    asJson(await api.get('/agents/${_enc(agentId)}/model/summary'));

/// `PUT /agents/{id}/model {primary, expected_revision}`; a null [primary] goes back to the
/// owner's default model.
Future<void> chooseAgentModel(
  String agentId, {
  required Json? primary,
  required int revision,
}) => api.put('/agents/${_enc(agentId)}/model', {
  'primary': primary,
  'expected_revision': revision,
});

// Memory -------------------------------------------------------------------------------------

/// `GET /agents/{id}/memory`: one versioned text document.
@immutable
class AgentMemory {
  const AgentMemory({
    required this.content,
    required this.version,
    this.updatedAt,
  });

  factory AgentMemory.fromJson(Json j) => AgentMemory(
    content: asStr(j['content']),
    version: asInt(j['version']) ?? 1,
    updatedAt: asDate(j['updated_at']),
  );

  final String content;
  final int version;
  final DateTime? updatedAt;
}

Future<AgentMemory> fetchMemory(String agentId) async => AgentMemory.fromJson(
  asJson(await api.get('/agents/${_enc(agentId)}/memory')),
);

/// `PUT /agents/{id}/memory {content, version}` (≤ 30000 characters).
Future<AgentMemory> saveMemory(
  String agentId,
  String content,
  int version,
) async => AgentMemory.fromJson(
  asJson(
    await api.put('/agents/${_enc(agentId)}/memory', {
      'content': content,
      'version': version,
    }),
  ),
);

/// One attributed change of a memory document (agent memory, owner profile or preferences).
@immutable
class MemoryRevision {
  const MemoryRevision({
    required this.id,
    required this.document,
    required this.author,
    required this.change,
    required this.changes,
    this.authorAgentId,
    this.authorAgentName,
    this.fromOwnerMessage = false,
    this.createdAt,
    this.truncated = false,
    this.revertedRevisionId,
  });

  factory MemoryRevision.fromJson(Json j) => MemoryRevision(
    id: asStr(j['id']),
    document: asStr(j['document']),
    author: asStr(j['author'], 'system'),
    change: asStr(j['change']),
    changes: asJsonList(j['changes']),
    authorAgentId: asString(j['author_agent_id']),
    authorAgentName: asString(j['author_agent_name']),
    fromOwnerMessage: asBool(j['from_owner_message']),
    createdAt: asDate(j['created_at']),
    truncated: asBool(j['changes_truncated']),
    revertedRevisionId: asString(j['reverted_revision_id']),
  );

  final String id;

  /// `agent_memory`, `owner_profile` or `owner_preferences`.
  final String document;

  /// `owner`, `agent` or `system`.
  final String author;
  final String change;

  /// `{change: added|removed, text}` lines or `{field, before, after}` preference changes.
  final List<Json> changes;
  final String? authorAgentId;
  final String? authorAgentName;
  final bool fromOwnerMessage;
  final DateTime? createdAt;
  final bool truncated;
  final String? revertedRevisionId;
}

Future<List<MemoryRevision>> fetchMemoryRevisions(String agentId) async =>
    asJsonList(
      await api.get(
        '/agents/${_enc(agentId)}/memory/revisions',
        query: {'limit': 50},
      ),
    ).map(MemoryRevision.fromJson).toList();

Future<List<MemoryRevision>> fetchProfileRevisions() async =>
    asJsonList(await api.get('/owner/profile/revisions', query: {'limit': 50}))
        .map(MemoryRevision.fromJson)
        .toList();

/// Undoes one change as a new change by the owner; later changes stay.
Future<void> revertRevision(String id, int? version) =>
    api.post('/memory/revisions/${_enc(id)}/revert', {'version': version});

// Scratchpad and light goals (generic agent-bound resources) ---------------------------------

/// `/scratchpad` (`ScratchpadItem {title ≤ 160, content ≤ 30000}`).
const scratchpadKind = 'scratchpad';

/// `/agent-goals` (`AgentGoal {title ≤ 160, description ≤ 2000, done}`); a light goal
/// schedules nothing and grants no authority.
const goalsKind = 'agent-goals';

/// One versioned row of an agent-bound resource router (`Resource`).
@immutable
class AgentResource {
  const AgentResource({
    required this.id,
    required this.payload,
    required this.version,
    this.updatedAt,
  });

  factory AgentResource.fromJson(Json j) => AgentResource(
    id: asStr(j['id']),
    payload: asJson(j['payload']),
    version: asInt(j['version']) ?? 1,
    updatedAt: asDate(j['updated_at']),
  );

  final String id;
  final Json payload;
  final int version;
  final DateTime? updatedAt;

  String text(String key) => asStr(payload[key]);
}

/// `GET /{kind}?agent_id=`.
Future<List<AgentResource>> fetchAgentResources(
  String kind,
  String agentId,
) async =>
    asJsonList(await api.get('/$kind', query: {'agent_id': agentId}))
        .map(AgentResource.fromJson)
        .toList();

/// `POST /{kind} {agent_id, payload}`.
Future<void> createAgentResource(String kind, String agentId, Json payload) =>
    api.post('/$kind', {'agent_id': agentId, 'payload': payload});

/// `PUT /{kind}/{id} {version, payload}` (a stale version is `version_conflict`).
Future<void> saveAgentResource(String kind, AgentResource row, Json payload) =>
    api.put('/$kind/${_enc(row.id)}', {
      'version': row.version,
      'payload': payload,
    });

/// `DELETE /{kind}/{id}`.
Future<void> deleteAgentResource(String kind, String id) =>
    api.delete('/$kind/${_enc(id)}');

// Semantic memory ----------------------------------------------------------------------------

/// OpenAI's embedding models (apps/web KnowledgeSection.tsx `EMBEDDING_MODELS`).
const embeddingModels = ['text-embedding-3-small', 'text-embedding-3-large'];

/// The owner's semantic retrieval setting (`GET/PUT /memory/semantic/config`), for every agent.
@immutable
class SemanticConfig {
  const SemanticConfig({required this.enabled, this.model});

  factory SemanticConfig.fromJson(Json j) => SemanticConfig(
    enabled: asBool(j['enabled']),
    model: asString(j['model']),
  );

  final bool enabled;
  final String? model;

  Json toJson() => {'enabled': enabled, 'model': model};

  @override
  bool operator ==(Object other) =>
      other is SemanticConfig &&
      other.enabled == enabled &&
      other.model == model;

  @override
  int get hashCode => Object.hash(enabled, model);
}

Future<SemanticConfig> fetchSemanticConfig() async =>
    SemanticConfig.fromJson(asJson(await api.get('/memory/semantic/config')));

/// Refused with `semantic_model_required` when enabled without a model.
Future<SemanticConfig> saveSemanticConfig(SemanticConfig config) async =>
    SemanticConfig.fromJson(
      asJson(await api.put('/memory/semantic/config', config.toJson())),
    );

/// `POST /agents/{id}/memory/semantic {text ≤ 24000}`: indexes one knowledge note.
Future<void> addSemanticNote(String agentId, String text) =>
    api.post('/agents/${_enc(agentId)}/memory/semantic', {'text': text});

// Knowledge (notes and links) --------------------------------------------------------------

/// One item of `GET /agents/{id}/knowledge`: a note or a link.
@immutable
class KnowledgeItem {
  const KnowledgeItem({
    required this.id,
    required this.type,
    required this.title,
    this.content = '',
    this.url,
    this.version,
    this.updatedAt,
  });

  factory KnowledgeItem.fromJson(Json j) => KnowledgeItem(
    id: asStr(j['id']),
    type: asStr(j['type'], 'note'),
    title: asStr(j['title']),
    content: asStr(j['content']),
    url: asString(j['url']),
    version: asInt(j['version']),
    updatedAt: asDate(j['updated_at']),
  );

  final String id;

  /// `note` or `link`.
  final String type;
  final String title;
  final String content;
  final String? url;
  final int? version;
  final DateTime? updatedAt;

  bool get isLink => type == 'link';
}

Future<List<KnowledgeItem>> fetchKnowledge(String agentId) async =>
    asJsonList(await api.get('/agents/${_enc(agentId)}/knowledge'))
        .map(KnowledgeItem.fromJson)
        .toList();

Future<void> addKnowledgeNote(String agentId, String title, String content) =>
    api.post('/agents/${_enc(agentId)}/knowledge/notes', {
      'title': title,
      'content': content,
    });

Future<void> saveKnowledgeNote(
  String agentId,
  String id,
  String title,
  String content,
) => api.put('/agents/${_enc(agentId)}/knowledge/notes/${_enc(id)}', {
  'title': title,
  'content': content,
});

Future<void> deleteKnowledgeNote(String agentId, String id) =>
    api.delete('/agents/${_enc(agentId)}/knowledge/notes/${_enc(id)}');

Future<void> addKnowledgeLink(String agentId, Json link) =>
    api.post('/knowledge-links', {'agent_id': agentId, 'payload': link});

Future<void> saveKnowledgeLink(String id, int version, Json link) => api.put(
  '/knowledge-links/${_enc(id)}',
  {'version': version, 'payload': link},
);

Future<void> deleteKnowledgeLink(String id) =>
    api.delete('/knowledge-links/${_enc(id)}');

/// An http(s) address with a host (the server's `KnowledgeLink.url` rule).
bool isWebUrl(String value) {
  final uri = Uri.tryParse(value.trim());
  return uri != null &&
      (uri.isScheme('http') || uri.isScheme('https')) &&
      uri.host.isNotEmpty;
}
