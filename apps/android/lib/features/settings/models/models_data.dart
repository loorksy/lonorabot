// Global model routing and Lonora's model lists (lonora-api-contract §18; apps/web
// ModelsPage.tsx, lib/model_routing.ts, lib/model_catalog.ts; packages/contracts models.ts).
// The routing applies to every agent and routine; an agent's own model is chosen in its
// settings (`/agents/{id}/model`).
import 'package:flutter/foundation.dart';

import '../../../app/services.dart';
import '../../../core/api/api_error.dart';
import '../../../core/json.dart';
import '../integrations/integrations_data.dart';

/// The routes in the Web's order (apps/web lib/model_routing.ts `capabilities`).
const List<String> routeCapabilities = [
  'conversation',
  'reasoning',
  'research',
  'vision',
  'realtime_voice',
  'stt',
  'tts',
  'background',
];

/// The voice routes: they take OpenAI's speech models, not Lonora's chat models.
const List<String> voiceCapabilities = ['realtime_voice', 'stt', 'tts'];

/// The live, transcription and synthesis models lonora_voice serves (apps/web ModelsPage.tsx
/// `SPEECH`).
const Map<String, List<String>> speechModelIds = {
  'realtime_voice': ['gpt-live-1', 'gpt-live-1-mini'],
  'stt': ['gpt-4o-mini-transcribe', 'whisper-1'],
  'tts': ['gpt-4o-mini-tts', 'tts-1'],
};

/// The providers with a model list of their own (apps/web lib/model_catalog.ts), then the
/// ChatGPT plan's models as its signed-in account offers them.
const List<String> catalogProviders = [
  'openai',
  'anthropic',
  'deepseek',
  'zai',
  'openrouter',
  'openai_chatgpt',
];

/// One provider and model (`ModelSelection`).
@immutable
class ModelSelection {
  const ModelSelection(this.provider, this.model);

  static ModelSelection? fromJson(Object? value) {
    final j = asJson(value);
    final provider = asString(j['provider']);
    final model = asString(j['model']);
    if (provider == null || model == null) return null;
    return ModelSelection(provider, model);
  }

  final String provider;
  final String model;

  String get key => '$provider:$model';

  Json toJson() => {'provider': provider, 'model': model};

  @override
  bool operator ==(Object other) =>
      other is ModelSelection &&
      other.provider == provider &&
      other.model == model;

  @override
  int get hashCode => Object.hash(provider, model);
}

/// `RoutingPolicy`: one model for text work (`unified`) or a model per capability (`custom`).
@immutable
class RoutingPolicy {
  const RoutingPolicy({
    required this.mode,
    this.unified,
    this.routes = const {},
  });

  factory RoutingPolicy.fromJson(Json j) => RoutingPolicy(
    mode: j['mode'] == 'custom' ? 'custom' : 'unified',
    unified: ModelSelection.fromJson(j['unified']),
    routes: {
      for (final MapEntry(:key, :value) in asJson(j['routes']).entries)
        if (ModelSelection.fromJson(value) case final ModelSelection s) key: s,
    },
  );

  final String mode;
  final ModelSelection? unified;
  final Map<String, ModelSelection> routes;

  bool get isUnified => mode == 'unified';

  Json toJson() => {
    'mode': mode,
    'unified': unified?.toJson(),
    'routes': {
      for (final MapEntry(:key, :value) in routes.entries) key: value.toJson(),
    },
  };

  /// The routes a mode keeps: one model for text work keeps only the voice routes
  /// (apps/web ModelsPage.tsx, the mode select).
  RoutingPolicy withMode(String next) => RoutingPolicy(
    mode: next,
    unified: unified,
    routes: next == 'unified'
        ? {
            for (final MapEntry(:key, :value) in routes.entries)
              if (voiceCapabilities.contains(key)) key: value,
          }
        : routes,
  );

  RoutingPolicy withUnified(ModelSelection? value) =>
      RoutingPolicy(mode: mode, unified: value, routes: routes);

  /// Sets or clears one capability's route.
  RoutingPolicy withRoute(String capability, ModelSelection? selection) =>
      RoutingPolicy(
        mode: mode,
        unified: unified,
        routes: {
          for (final e in routes.entries)
            if (e.key != capability) e.key: e.value,
          capability: ?selection,
        },
      );

  @override
  bool operator ==(Object other) =>
      other is RoutingPolicy &&
      other.mode == mode &&
      other.unified == unified &&
      mapEquals(other.routes, routes);

  @override
  int get hashCode => Object.hash(
    mode,
    unified,
    Object.hashAllUnordered(
      routes.entries.map((e) => Object.hash(e.key, e.value)),
    ),
  );
}

/// One model of Lonora's list (`ModelDescriptor`).
@immutable
class ModelDescriptor {
  const ModelDescriptor({
    required this.id,
    required this.provider,
    required this.name,
    this.capabilities = const [],
    this.verified = false,
  });

  factory ModelDescriptor.fromJson(Json j) => ModelDescriptor(
    id: asStr(j['id']),
    provider: asStr(j['provider']),
    name: asString(j['name']) ?? asStr(j['id']),
    capabilities: asStringList(j['capabilities']),
    verified: asBool(j['verified']),
  );

  final String id;
  final String provider;
  final String name;
  final List<String> capabilities;
  final bool verified;

  ModelSelection get selection => ModelSelection(provider, id);

  /// «OpenAI · GPT-5».
  String get label => '${providerName(provider)} · $name';
}

/// What a route asks of a model whose capabilities are known (apps/web ModelsPage.tsx
/// `needed`).
String neededCapability(String capability) =>
    capability == 'vision' ||
        capability == 'reasoning' ||
        voiceCapabilities.contains(capability)
    ? capability
    : 'text';

/// The models a route offers: the speech models for a voice route (when OpenAI is
/// connected), otherwise the listed models that can do what it needs (a model with unknown or
/// unverified capabilities is always offered). [capability] null is the unified model.
List<ModelDescriptor> modelsFor(
  String? capability,
  List<ModelDescriptor> models, {
  required bool speech,
}) {
  if (capability != null && voiceCapabilities.contains(capability)) {
    if (!speech) return const [];
    return [
      for (final id in speechModelIds[capability] ?? const <String>[])
        ModelDescriptor(
          id: id,
          provider: 'openai',
          name: id,
          capabilities: [capability],
          verified: true,
        ),
    ];
  }
  if (capability == null) return models;
  final need = neededCapability(capability);
  return [
    for (final m in models)
      if (!m.verified ||
          m.capabilities.isEmpty ||
          m.capabilities.contains(need))
        m,
  ];
}

/// A selection as the owner recognizes it: the listed name, else «provider · model».
String selectionLabel(ModelSelection s, List<ModelDescriptor> models) {
  for (final m in models) {
    if (m.provider == s.provider && m.id == s.model) return m.label;
  }
  return '${providerName(s.provider)} · ${s.model}';
}

Future<RoutingPolicy> fetchRouting() async =>
    RoutingPolicy.fromJson(asJson(await api.get('/settings/models')));

/// `PUT /settings/models` (it also re-queues replies that failed for lack of a model).
Future<RoutingPolicy> saveRouting(RoutingPolicy policy) async =>
    RoutingPolicy.fromJson(
      asJson(await api.put('/settings/models', policy.toJson())),
    );

/// `GET /providers/{p}/models`: Lonora's list for a provider (never read from it).
Future<List<ModelDescriptor>> fetchModels(String provider) async => asJsonList(
  await api.get('/providers/${Uri.encodeComponent(provider)}/models'),
).map(ModelDescriptor.fromJson).toList();

/// The lists of every connected provider, in [catalogProviders] order; a provider whose list
/// cannot be read is left out.
Future<List<ModelDescriptor>> fetchConnectedModels(
  List<ProviderStatus> providers,
) async {
  final connected = [
    for (final p in catalogProviders)
      if (providers.any((s) => s.id == p && s.configured)) p,
  ];
  final lists = await Future.wait([
    for (final p in connected)
      fetchModels(p).catchError((Object e) {
        if (e is SessionRequestCancelled) throw e;
        return const <ModelDescriptor>[];
      }),
  ]);
  return [for (final l in lists) ...l];
}

/// `GET /agents/{id}/model/summary`: the agent's current model and who chose it.
Future<Json> fetchAgentModelSummary(String agentId) async => asJson(
  await api.get('/agents/${Uri.encodeComponent(agentId)}/model/summary'),
);
