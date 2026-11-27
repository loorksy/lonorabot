// Screen-local reads and writes of the integrations pages (lonora-api-contract §18, §11.4,
// §3.3; apps/web IntegrationsPage.tsx and ConnectionPages.tsx, apps/mobile
// app/(settings)/integrations.tsx). Secret values only ever travel outward, once: nothing here
// reads one back, logs one or keeps one.
import 'package:flutter/foundation.dart';

import '../../../app/services.dart';
import '../../../core/json.dart';
import '../../../l10n/l10n.dart';

/// Display names of the model providers (apps/web ConnectionPages.tsx `PROVIDER_NAMES`).
const Map<String, String> providerNames = {
  'openai': 'OpenAI',
  'openai_chatgpt': 'ChatGPT',
  'anthropic': 'Anthropic',
  'deepseek': 'DeepSeek',
  'zai': 'Z.ai',
  'openrouter': 'OpenRouter',
};

String providerName(String id) => providerNames[id] ?? id;

/// One `GET /providers` row: whether a key is stored (never the key) and, for the ChatGPT
/// plan, its sign-in status.
@immutable
class ProviderStatus {
  const ProviderStatus({
    required this.id,
    required this.configured,
    this.signIn,
  });

  factory ProviderStatus.fromJson(Json j) => ProviderStatus(
    id: asStr(j['id']),
    configured: asBool(j['configured']),
    signIn: j['sign_in'] is Map ? asJson(j['sign_in']) : null,
  );

  final String id;
  final bool configured;
  final Json? signIn;

  /// The ChatGPT plan signs in from its Secret card in chat: it takes no key here.
  bool get takesKey => id != chatgptProvider;
}

Future<List<ProviderStatus>> fetchProviders() async =>
    asJsonList(await api.get('/providers'))
        .map(ProviderStatus.fromJson)
        .toList();

/// `POST /providers/{id}/test`: whether the provider accepts the key; nothing is stored.
Future<void> testProviderKey(String provider, String key) async {
  await api.post('/providers/${Uri.encodeComponent(provider)}/test', {
    'api_key': key,
  });
}

/// `PUT /providers/{id}/credential`: stores the key encrypted; it is never read back.
Future<void> saveProviderKey(String provider, String key) async {
  await api.put('/providers/${Uri.encodeComponent(provider)}/credential', {
    'api_key': key,
  });
}

/// `POST /providers/openai_chatgpt/sign-out` → `{signed_out, revoked}`.
Future<Json> signOutChatGpt() async =>
    asJson(await api.post('/providers/$chatgptProvider/sign-out'));

/// A broker connection (`GET /trading/connections` resource row).
@immutable
class BrokerConnection {
  const BrokerConnection({
    required this.id,
    required this.provider,
    required this.accountId,
    this.region,
    this.enabled = true,
    this.version = 1,
    this.state = const {},
  });

  factory BrokerConnection.fromJson(Json j) {
    final payload = asJson(j['payload']);
    return BrokerConnection(
      id: asStr(j['id']),
      provider: asStr(payload['provider'], 'metaapi'),
      accountId: asStr(payload['account_id']),
      region: asString(payload['region']),
      enabled: asBool(payload['enabled'], true),
      version: asInt(j['version']) ?? 1,
      state: asJson(j['state']),
    );
  }

  final String id;
  final String provider;
  final String accountId;
  final String? region;
  final bool enabled;
  final int version;
  final Json state;

  /// A simulation trades against an imported snapshot: it is never a broker account.
  bool get isSimulation => provider == 'simulation';

  /// What the broker itself reported (broker, login, server), only once observed for this
  /// version of the connection (apps/web lib/broker-identity.ts `brokerIdentity`).
  ({String? broker, String? login, String? server})? get identity {
    final raw = state['broker_identity'];
    if (raw is! Map) return null;
    final values = asJson(raw);
    if (asInt(values['connection_version']) != version) return null;
    String? text(Object? v) => v is String && v.isNotEmpty ? v : null;
    return (
      broker: text(values['broker']),
      login: text(values['login']),
      server: text(values['server']),
    );
  }

  /// The account number the owner knows: the broker's login, or a simulation's own id. A
  /// MetaApi account id is a provisioning UUID and is never shown as a number.
  String? get number => identity?.login ?? (isSimulation ? accountId : null);
}

Future<List<BrokerConnection>> fetchConnections() async =>
    asJsonList(await api.get('/trading/connections'))
        .map(BrokerConnection.fromJson)
        .toList();

/// The fields each trading adapter takes (apps/web ConnectionPages.tsx `brokerProviders`).
typedef BrokerField = ({String name, bool secret, bool required});

const Map<String, List<BrokerField>> brokerFields = {
  'metaapi': [
    (name: 'account_id', secret: false, required: true),
    (name: 'api_key', secret: true, required: true),
    (name: 'region', secret: false, required: false),
  ],
  'simulation': [(name: 'account_id', secret: false, required: true)],
};

/// The body of a link or a dry run: the adapter, `enabled`, and every field (empty → null).
Json brokerBody(String provider, Map<String, String> values) => {
  'provider': provider,
  'enabled': true,
  for (final f in brokerFields[provider] ?? const <BrokerField>[])
    f.name: (values[f.name] ?? '').trim().isEmpty
        ? null
        : values[f.name]!.trim(),
};

/// `POST /trading/connections/test`: a read-only round trip that stores nothing.
Future<Json> testBroker(Json body) async =>
    asJson(await api.post('/trading/connections/test', body));

/// `POST /trading/connections`: the same link endpoint as the Web.
Future<BrokerConnection> linkBroker(Json body) async =>
    BrokerConnection.fromJson(
      asJson(await api.post('/trading/connections', body)),
    );

/// `DELETE /trading/connections/{id}` (refused while an operation is unresolved).
Future<void> unlinkBroker(String id) async {
  await api.delete('/trading/connections/${Uri.encodeComponent(id)}');
}

/// `GET /trading/accounts/{id}` → the account part (balance, currency, broker, login…).
Future<Json> fetchAccount(String id) async => asJson(
  asJson(
    await api.get('/trading/accounts/${Uri.encodeComponent(id)}'),
  )['account'],
);

/// `GET /market/symbols?account_id=` → the account's symbols.
Future<List<String>> fetchSymbols(String id) async =>
    asStringList(await api.get('/market/symbols', query: {'account_id': id}));

/// `POST /trading/connections/{id}/simulation {snapshot}`.
Future<void> importSimulation(String id, Object? snapshot) async {
  await api.post('/trading/connections/${Uri.encodeComponent(id)}/simulation', {
    'snapshot': snapshot,
  });
}

/// `GET /capabilities`: everything agents can use now, as raw server facts.
@immutable
class CapabilityReport {
  const CapabilityReport(this.raw);

  final Json raw;

  List<Json> get trustedSources => asJsonList(raw['trusted_sources']);
  List<Json> get skills => asJsonList(raw['skills']);
  List<Json> get mcpServers => asJsonList(raw['mcp_servers']);
  List<Json> get integrations => asJsonList(raw['integrations']);
  List<Json> get builtIn => asJsonList(raw['built_in']);

  List<Json> get feedDomains => [
    for (final s in trustedSources)
      if (s['kind'] == 'feed_domain' && asBool(s['active'])) s,
  ];

  List<Json> get githubSources => [
    for (final s in trustedSources)
      if (asStr(s['kind']).startsWith('github') && asBool(s['active'])) s,
  ];

  List<Json> get feeds => [
    for (final i in integrations)
      if (i['type'] == 'news_feed') i,
  ];

  Json? get telegram {
    for (final i in integrations) {
      if (i['type'] == 'telegram') return i;
    }
    return null;
  }

  /// Integrations without a page of their own (economic calendar, web search, webhooks).
  List<Json> get otherIntegrations => [
    for (final i in integrations)
      if (i['type'] != 'news_feed' && i['type'] != 'telegram') i,
  ];

  Json? sourceOf(Json server) {
    final id = server['trust_source_id'];
    if (id == null) return null;
    for (final s in trustedSources) {
      if (s['id'] == id) return s;
    }
    return null;
  }
}

Future<CapabilityReport> fetchCapabilities() async =>
    CapabilityReport(asJson(await api.get('/capabilities')));

/// `POST /trusted-sources/{id}/revoke|restore`.
Future<void> setSourceActive(String id, {required bool active}) async {
  await api.post(
    '/trusted-sources/${Uri.encodeComponent(id)}/${active ? 'restore' : 'revoke'}',
  );
}

/// `POST /trusted-sources {kind: feed_domain, identifier}`.
Future<void> addFeedDomain(String domain) async {
  await api.post('/trusted-sources', {
    'kind': 'feed_domain',
    'identifier': domain,
  });
}

/// A domain as typed («https://Example.com/x» → «example.com»), or null when it is not one
/// (apps/web IntegrationsPage.tsx `domainsSheet`).
String? normalizeDomain(String input) {
  final value = input
      .trim()
      .replaceFirst(RegExp(r'^https?://'), '')
      .replaceFirst(RegExp(r'/.*$'), '')
      .toLowerCase();
  return RegExp(r'^[a-z0-9.-]+\.[a-z]{2,}$').hasMatch(value) ? value : null;
}

/// Whether [url] is a feed link the Web accepts (`^https?://\S+\.\S+`).
bool isFeedUrl(String url) =>
    RegExp(r'^https?://\S+\.\S+').hasMatch(url.trim());

/// `POST /integrations` for a news feed (named after its host, as the Web does).
Future<void> addFeed(String url) async {
  final link = url.trim();
  await api.post('/integrations', {
    'payload': {
      'type': 'news_feed',
      'name': link.replaceFirst(RegExp(r'^https?://'), '').split('/').first,
      'url': link,
      'enabled': true,
    },
  });
}

/// `DELETE /integrations/{id}`.
Future<void> removeIntegration(String id) async {
  await api.delete('/integrations/${Uri.encodeComponent(id)}');
}

/// `POST /integrations/secrets {name, value}` → the secret's id. The value goes out once.
Future<String> saveIntegrationSecret(String name, String value) async => asStr(
  asJson(
    await api.post('/integrations/secrets', {'name': name, 'value': value}),
  )['id'],
);

/// Links Telegram: the bot token is stored as a secret first, then the integration points
/// at it and at the agent that receives the owner's messages.
Future<void> linkTelegram(String token, String? agentId) async {
  final secretId = await saveIntegrationSecret('telegram-bot', token);
  await api.post('/integrations', {
    'payload': {
      'type': 'telegram',
      'name': 'Telegram',
      'secret_id': secretId,
      'deliver_to_agent_id': agentId,
      'enabled': true,
    },
  });
}

/// `POST /trusted-sources/mcp/{connection}/preview` → `{id, digest, tools, writes, blocked,
/// titles}`.
Future<Json> previewMcp(String connectionId) async => asJson(
  await api.post(
    '/trusted-sources/mcp/${Uri.encodeComponent(connectionId)}/preview',
  ),
);

/// `POST /trusted-sources/mcp/{connection} {tier, digest}`; tier is read or
/// write_nonfinancial (never money).
Future<void> trustMcp(String connectionId, String tier, String digest) async {
  await api.post('/trusted-sources/mcp/${Uri.encodeComponent(connectionId)}', {
    'tier': tier,
    'digest': digest,
  });
}

/// `POST /mcp/test {url, token}` → `{ok, tools, writes, blocked, unsupported}`.
Future<Json> testMcp(String url, String? token) async => asJson(
  await api.post('/mcp/test', {
    'url': url,
    'token': token == null || token.isEmpty ? null : token,
  }),
);

/// Adds a remote MCP server: its token (if any) is stored as a secret first.
Future<void> addMcp({
  required String name,
  required String url,
  String? token,
}) async {
  final secretId = token == null || token.isEmpty
      ? null
      : await saveIntegrationSecret(
          'mcp-$name'.length > 80 ? 'mcp-$name'.substring(0, 80) : 'mcp-$name',
          token,
        );
  await api.post('/mcp', {
    'payload': {
      'name': name,
      'url': url,
      'secret_id': secretId,
      'enabled': true,
    },
  });
}

/// Undoes a skill version: `GET` the agent's revision, then `POST` the revocation.
Future<void> undoSkillVersion(Json skill) async {
  final agentId = asStr(skill['agent_id']);
  final controls = asJson(
    await api.get('/agents/${Uri.encodeComponent(agentId)}/skills/revocations'),
  );
  await api.post('/agents/${Uri.encodeComponent(agentId)}/skills/revocations', {
    'skill_id': skill['skill_id'],
    'version': skill['version'],
    'expected_revision': controls['revision'],
  });
}

/// `GET /secrets` → `[{id, name, updated_at}]` (names only).
Future<List<Json>> fetchSecrets() async =>
    asJsonList(await api.get('/secrets'));

/// `DELETE /secrets/{id}` (refused while a connection uses it).
Future<void> deleteSecret(String id) async {
  await api.delete('/secrets/${Uri.encodeComponent(id)}');
}

/// The tools of an MCP server by level, each count in the language's own plural
/// (apps/web IntegrationsPage.tsx `levelText`, its ar catalog). Empty when it has none.
String mcpLevelText(L10n l10n, Json server) {
  final writes = asStringList(server['write_tools']).length;
  final reads = asStringList(server['trusted_tools']).length - writes;
  String count(int n, String noun) => plural(
    n,
    one: l10n.t('ix_${noun}1'),
    two: l10n.t('ix_${noun}2'),
    few: l10n.t('ix_${noun}sFew', [n]),
    many: l10n.t('ix_${noun}sMany', [n]),
  );

  return [
    if (reads > 0) count(reads, 'readTool'),
    if (writes > 0) count(writes, 'writeTool'),
  ].join(dotSeparator);
}
