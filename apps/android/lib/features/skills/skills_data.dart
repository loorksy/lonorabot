// One agent's skills (lonora-api-contract §9; apps/mobile/app/skills.tsx and components/skills,
// apps/web/src/shell/domain/SkillsPages.tsx): the current catalog (paged by 50), the owner's
// installed skills (`/skills`, versioned resources), exact-version blocks, version history and
// restore.
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../../app/services.dart';
import '../../core/json.dart';

String _enc(String value) => Uri.encodeComponent(value);

/// One catalog entry (`SkillCatalogEntry`); availability is the current catalog's, not a claim
/// about instructions pinned in a running task.
@immutable
class SkillEntry {
  const SkillEntry({
    required this.id,
    required this.title,
    this.version,
    this.description = '',
    this.source,
    this.available = true,
    this.code,
    this.manifest = const {},
    this.resourceId,
    this.content,
  });

  factory SkillEntry.fromJson(Json j) => SkillEntry(
    id: asStr(j['id']),
    title: asStr(j['title'], asStr(j['id'])),
    version: asString(j['version']),
    description: asStr(j['description']),
    source: asString(j['source']),
    available: asBool(j['available'], true),
    code: asString(j['code']),
    manifest: asJson(j['manifest']),
    resourceId: asString(j['resource_id']),
    content: asString(j['content']),
  );

  final String id;
  final String title;
  final String? version;
  final String description;

  /// `builtin`, `owner`, `legacy` or another manifest source.
  final String? source;
  final bool available;

  /// Why it is unavailable (`skill_disabled`, `skill_version_revoked`, …).
  final String? code;
  final Json manifest;
  final String? resourceId;

  /// The instructions (catalog detail only).
  final String? content;

  bool get builtin => source == 'builtin';

  /// Owner skills stored as a resource can be edited, switched and deleted
  /// (apps/mobile skill-details.tsx `editable`).
  bool get editable =>
      resourceId != null && !builtin && !id.endsWith('@installed');
}

/// A catalog page.
@immutable
class SkillCatalogPage {
  const SkillCatalogPage({required this.items, this.nextOffset, this.total});

  factory SkillCatalogPage.fromJson(Json j) => SkillCatalogPage(
    items: asJsonList(j['items']).map(SkillEntry.fromJson).toList(),
    nextOffset: asInt(j['next_offset']),
    total: asInt(j['total']),
  );

  final List<SkillEntry> items;
  final int? nextOffset;
  final int? total;
}

/// One blocked exact version.
@immutable
class SkillRevocation {
  const SkillRevocation({
    required this.skillId,
    required this.version,
    required this.reason,
    this.revokedAt,
  });

  factory SkillRevocation.fromJson(Json j) => SkillRevocation(
    skillId: asStr(j['skill_id']),
    version: asStr(j['version']),
    reason: asStr(j['reason'], 'owner_revoked'),
    revokedAt: asDate(j['revoked_at']),
  );

  final String skillId;
  final String version;
  final String reason;
  final DateTime? revokedAt;
}

/// `SkillVersionControls`: the agent's blocked versions and their revision.
@immutable
class SkillControls {
  const SkillControls({required this.revision, required this.revoked});

  factory SkillControls.fromJson(Json j) => SkillControls(
    revision: asInt(j['revision']) ?? 0,
    revoked: asJsonList(j['revoked']).map(SkillRevocation.fromJson).toList(),
  );

  final int revision;
  final List<SkillRevocation> revoked;

  bool blocks(String id, String? version) =>
      version != null &&
      revoked.any((r) => r.skillId == id && r.version == version);
}

/// An installed skill resource (`Resource<AgentSkill>`).
@immutable
class SkillResource {
  const SkillResource({
    required this.id,
    required this.agentId,
    required this.version,
    required this.payload,
  });

  factory SkillResource.fromJson(Json j) => SkillResource(
    id: asStr(j['id']),
    agentId: asStr(j['agent_id']),
    version: asInt(j['version']) ?? 1,
    payload: asJson(j['payload']),
  );

  final String id;
  final String agentId;
  final int version;
  final Json payload;

  bool get enabled => payload['enabled'] != false;
  String get content => asStr(payload['content']);
  Json? get manifest =>
      payload['manifest'] is Map ? asJson(payload['manifest']) : null;
  String get name => asStr(payload['name']);
}

/// One saved version of an installed skill («سجل الإصدارات»).
@immutable
class SkillVersion {
  const SkillVersion({
    required this.version,
    this.createdAt,
    this.current = false,
  });

  factory SkillVersion.fromJson(Json j) => SkillVersion(
    version: asInt(j['version']) ?? 0,
    createdAt: asDate(j['created_at']),
    current: asBool(j['current']),
  );

  final int version;
  final DateTime? createdAt;
  final bool current;
}

/// The block reasons, in the Expo order (components/skills/shared.ts).
const skillBlockReasons = {
  'owner_revoked': 'skillsReasonOwner',
  'regression': 'skillsReasonRegression',
  'unsafe': 'skillsReasonUnsafe',
  'superseded': 'skillsReasonSuperseded',
};

/// The availability codes with their own label (components/skills/shared.ts).
const skillAvailabilityCodes = {
  'skill_version_revoked',
  'skill_disabled',
  'skill_dependency_unavailable',
  'skill_required_tools_unavailable',
  'skill_required_capability_unavailable',
  'skill_context_budget_exceeded',
  'skill_total_budget_exceeded',
  'skill_manifest_invalid',
  'skill_builtin_override_denied',
  'skill_reference_missing',
  'skill_dependency_cycle',
};

/// `x.y.z` with no leading zeros (components/skills/shared.ts `semanticVersion`).
final semanticVersion = RegExp(
  r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$',
);

/// A skill identifier (components/skills/skill-create.tsx).
final skillIdentifier = RegExp(r'^[a-z0-9][a-z0-9_-]{0,79}$');

/// The payload of a new owner skill (components/skills/skill-create.tsx): read-only
/// instructions loaded on request; it adds no tools or trading authority.
Json newSkillPayload({
  required String id,
  required String title,
  required String purpose,
  required String version,
  required String content,
}) => {
  'name': id,
  'content': content,
  'enabled': true,
  'manifest': {
    'id': id,
    'version': version,
    'title': title.trim(),
    'description': purpose.trim(),
    'source': 'owner',
    'stability': 'stable',
    'activation': {'mode': 'explicit', 'triggers': <String>[]},
    'risk_class': 'read_only',
    'required_tools': <String>[],
    'required_capabilities': <String>[],
    'dependencies': <String>[],
    'conflicts': <String>[],
    'priority': 50,
    'context_budget': 16000,
  },
};

/// «الأداة»: the three real tools a skill may name, and none (apps/web SkillsPages.tsx `TOOLS`).
const skillToolLabels = {
  '': 'sk_toolNone',
  'web_search': 'sk_toolWeb',
  'artifact_read': 'sk_toolRead',
  'artifact_create': 'sk_toolReports',
};

/// The tool list with its first entry set to [tool]; the rest is kept as it was
/// (apps/web SkillsPages.tsx `keepTools`).
List<String> keepTools(List<String> prior, String tool) {
  if ((prior.isEmpty ? '' : prior.first) == tool) return prior;
  return tool.isNotEmpty
      ? [tool, ...prior.skip(1).where((name) => name != tool)]
      : prior.skip(1).toList();
}

/// The largest skill file an import reads (apps/web SkillsPages.tsx `MAX_IMPORT`).
const maxSkillImportBytes = 600000;

/// A skill identity from its title: the Latin form, else a short random id
/// (apps/web SkillsPages.tsx `skillId`).
String skillIdFromTitle(String title) {
  final slug = title
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9]+'), '-')
      .replaceAll(RegExp(r'^-+|-+$'), '');
  final cut = slug.length > 60 ? slug.substring(0, 60) : slug;
  return skillIdentifier.hasMatch(cut)
      ? cut
      : 'skill-${const Uuid().v4().substring(0, 8)}';
}

/// The payload of an imported .md, .txt or .json skill file (apps/web SkillsPages.tsx
/// `importSkill`): a .json file is data — its name, description and instructions or content
/// are read, nothing in it runs. [fallbackDescription] is «مهارة مستوردة» in the owner's
/// language.
Json importedSkillPayload(
  String fileName,
  String text, {
  required String fallbackDescription,
}) {
  Json parsed = const {};
  try {
    final value = jsonDecode(text);
    if (value is Map) parsed = value.cast<String, dynamic>();
  } on FormatException {
    parsed = const {};
  }
  String cut(String v, int n) => String.fromCharCodes(v.runes.take(n)).trim();
  String field(String key) =>
      parsed[key] is String ? (parsed[key] as String).trim() : '';
  final title = cut(
    field('name').isNotEmpty
        ? field('name')
        : fileName.replaceFirst(RegExp(r'\.[^.]+$'), ''),
    160,
  );
  final description = cut(
    field('description').isNotEmpty
        ? field('description')
        : fallbackDescription,
    1000,
  );
  final content = cut(
    field('instructions').isNotEmpty
        ? field('instructions')
        : field('content').isNotEmpty
        ? field('content')
        : text,
    16000,
  );
  final id = skillIdFromTitle(title);
  return {
    'name': id,
    'content': content,
    'enabled': true,
    'manifest': {
      'id': id,
      'version': '1.0.0',
      'title': title,
      'description': description.isEmpty ? title : description,
      'source': 'owner',
      'stability': 'stable',
      'activation': {'mode': 'explicit', 'triggers': <String>[]},
      'risk_class': 'read_only',
      'required_tools': <String>[],
      'required_capabilities': <String>[],
      'dependencies': <String>[],
      'conflicts': <String>[],
      'priority': 50,
      'context_budget': 6000,
    },
  };
}

Future<SkillCatalogPage> fetchSkillCatalog(
  String agentId, {
  int offset = 0,
}) async => SkillCatalogPage.fromJson(
  asJson(
    await api.get(
      '/agents/${_enc(agentId)}/skills/catalog',
      query: {'offset': offset, 'limit': 50},
    ),
  ),
);

Future<SkillEntry> fetchSkillDetail(String agentId, String skillId) async =>
    SkillEntry.fromJson(
      asJson(
        await api.get(
          '/agents/${_enc(agentId)}/skills/catalog/${_enc(skillId)}',
        ),
      ),
    );

Future<SkillControls> fetchSkillControls(String agentId) async =>
    SkillControls.fromJson(
      asJson(await api.get('/agents/${_enc(agentId)}/skills/revocations')),
    );

Future<List<SkillResource>> fetchInstalledSkills(String agentId) async =>
    asJsonList(await api.get('/skills', query: {'agent_id': agentId}))
        .map(SkillResource.fromJson)
        .toList();

Future<SkillResource> fetchSkillResource(String id) async =>
    SkillResource.fromJson(asJson(await api.get('/skills/${_enc(id)}')));

Future<SkillResource> createSkill(String agentId, Json payload) async =>
    SkillResource.fromJson(
      asJson(
        await api.post('/skills', {'agent_id': agentId, 'payload': payload}),
      ),
    );

/// `PUT /skills/{id} {payload, version}` (optimistic version).
Future<SkillResource> saveSkill(SkillResource skill, Json payload) async =>
    SkillResource.fromJson(
      asJson(
        await api.put('/skills/${_enc(skill.id)}', {
          'payload': payload,
          'version': skill.version,
        }),
      ),
    );

Future<void> deleteSkill(String id) => api.delete('/skills/${_enc(id)}');

Future<List<SkillVersion>> fetchSkillVersions(String id) async =>
    asJsonList(await api.get('/skills/${_enc(id)}/versions'))
        .map(SkillVersion.fromJson)
        .toList();

/// «الرجوع إلى الإصدار N»: that version's payload saved as the next version.
Future<SkillResource> restoreSkill(
  String id,
  int version,
  int expectedVersion,
) async => SkillResource.fromJson(
  asJson(
    await api.post('/skills/${_enc(id)}/restore', {
      'version': version,
      'expected_version': expectedVersion,
    }),
  ),
);

/// Blocks one exact version for this agent (`SkillRevokeRequest`); permanent.
Future<void> blockSkillVersion(
  String agentId, {
  required String skillId,
  required String version,
  required int revision,
  required String reason,
}) => api.post('/agents/${_enc(agentId)}/skills/revocations', {
  'skill_id': skillId,
  'version': version,
  'expected_revision': revision,
  'reason': reason,
});
