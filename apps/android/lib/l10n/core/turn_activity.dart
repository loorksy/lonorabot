/// Port of packages/core/src/turn-activity.ts (`turnActivity`, `activityCallLabel`): the
/// phase a run's observable events put the agent in, its tool calls, and the owner's line for
/// each call. Actual run/tool observations only: nothing here invents reasoning steps.
/// The phase's label is the app catalog's `activity_<phase>`, a call's state
/// `activity_call_<status>` (apps/mobile/components/turn-activity.tsx:45,160).
library;

import 'core_tables.g.dart';
import 'values.dart';

/// One tool call of a run, as the TS `ActivityCall`.
class ActivityCall {
  const ActivityCall({
    required this.id,
    required this.name,
    required this.status,
    this.toolset,
    this.effect,
    this.startedAt,
    this.completedAt,
  });

  final String id;

  /// The tool's registry id: for Technical details and tests, never the normal view.
  final String name;

  /// The tool's capability family (toolset), as the server reported it.
  final String? toolset;

  /// read, change or financial (registry metadata, never guessed from the name).
  final String? effect;

  /// running, completed, failed, cancelled or interrupted.
  final String status;
  final String? startedAt;
  final String? completedAt;

  ActivityCall copyWith({String? status, String? completedAt}) => ActivityCall(
    id: id,
    name: name,
    status: status ?? this.status,
    toolset: toolset,
    effect: effect,
    startedAt: startedAt,
    completedAt: completedAt ?? this.completedAt,
  );

  /// The TS object (absent fields left out).
  Map<String, Object?> toJson() => {
    'id': id,
    'name': name,
    'toolset': ?toolset,
    'effect': ?effect,
    'status': status,
    'started_at': ?startedAt,
    'completed_at': ?completedAt,
  };
}

/// What [turnActivity] returns: the phase (queued, preparing, thinking, searching, reading,
/// analyzing, executing, learning, sending, writing, waiting_input, waiting_external,
/// completed, failed, cancelled), the avatar state it shows, the last 24 calls and when the
/// phase was observed.
typedef TurnActivity = ({
  String phase,
  String avatar,
  List<ActivityCall> calls,
  String observedAt,
});

String? _effectOf(Object? value) =>
    value == 'read' || value == 'change' || value == 'financial'
    ? value as String
    : null;

const List<String> _phaseOrder = [
  'executing',
  'learning',
  'sending',
  'writing',
  'searching',
  'analyzing',
  'reading',
];

String _callPhase(Object? toolset, Object? effect) {
  final change = effect == 'change';
  if (effect == 'financial') return 'executing';
  if (toolset == 'memory' && change) return 'learning';
  if (toolset == 'collaboration' && change) return 'sending';
  if (toolset == 'charts' && change) return 'writing';
  if (toolset == 'files' && change) return 'executing';
  if (toolset == 'research') return 'searching';
  if (const [
    'market',
    'charts',
    'intelligence',
    'account',
  ].contains(jsString(toolset))) {
    return 'analyzing';
  }
  return 'reading';
}

/// The strongest phase among concurrent calls: acting outranks reading.
String _toolPhase(Iterable<(Object?, Object?)> calls) {
  final phases = calls.map((call) => _callPhase(call.$1, call.$2)).toSet();
  return _phaseOrder.firstWhere(phases.contains, orElse: () => 'reading');
}

String? _observedPhase(Object? kind, Map<String, Object?> tool) {
  if (kind == 'run.context_started') return 'preparing';
  if (kind == 'run.reply_started') return 'thinking';
  if (kind == 'run.delta' || kind == 'run.rich_partial') return 'writing';
  if (kind == 'tool.started' && tool['name'] is String) {
    return _toolPhase([(tool['toolset'], tool['effect'])]);
  }
  if (const [
    'tool.completed',
    'tool.failed',
    'tool.cancelled',
  ].contains(jsString(kind))) {
    return 'thinking';
  }
  return null;
}

const Map<String, String> _stable = {
  'queued': 'queued',
  'waiting_input': 'waiting_input',
  'waiting_takeover': 'waiting_external',
  'completed': 'completed',
  'failed': 'failed',
  'cancelled': 'cancelled',
};

/// The run's current phase from its saved activity snapshot and its events; [run] is a Run
/// JSON and [events] the Event JSONs (turn-activity.ts:151-226).
TurnActivity turnActivity(
  Map<String, Object?> run,
  List<Map<String, Object?>> events,
) {
  final calls = <String, ActivityCall>{};
  final stream = obj(run['stream']);
  var phase =
      stream['phase'] == 'streaming' &&
          (truthy(stream['text']) ||
              truthy(list(obj(stream['rich_content'])['parts']).length))
      ? 'writing'
      : 'preparing';
  final saved = obj(run['model_metadata'])['activity'];
  final snapshot = saved is Map ? obj(saved) : null;
  final snapshotPhase = snapshot == null
      ? null
      : _observedPhase(snapshot['kind'], snapshot);
  var phaseAt = snapshotPhase != null && snapshot!['observed_at'] is String
      ? parseTime(snapshot['observed_at'])
      : 0.0;
  if (snapshotPhase != null && phaseAt.isFinite) {
    phase = snapshotPhase;
  } else {
    phaseAt = 0;
  }
  var observedAt = phaseAt != 0
      ? jsString(snapshot?['observed_at'])
      : jsString(run['updated_at']);
  // A stable sort by cursor, as JavaScript's.
  final ordered = [for (var i = 0; i < events.length; i++) (i, events[i])]
    ..sort((a, b) {
      final byCursor = (number(a.$2['cursor']) ?? 0).compareTo(
        number(b.$2['cursor']) ?? 0,
      );
      return byCursor != 0 ? byCursor : a.$1.compareTo(b.$1);
    });
  for (final (_, event) in ordered) {
    if (event['run_id'] != run['id']) continue;
    final payload = obj(event['payload']);
    final kind = jsString(event['kind']);
    final nextPhase = _observedPhase(event['kind'], payload);
    final eventTime = parseTime(event['created_at']);
    if (nextPhase != null &&
        (eventTime >= phaseAt || (phaseAt == 0 && !eventTime.isFinite))) {
      phase = nextPhase;
      phaseAt = eventTime.isFinite ? eventTime : phaseAt;
      observedAt = jsString(event['created_at']);
    }
    final id = payload['call_id'];
    if (id is! String || id.isEmpty || !kind.startsWith('tool.')) continue;
    final previous = calls[id];
    final rawName = payload['name'];
    final trimmed = rawName is String ? rawName.trim() : '';
    final name = trimmed.isNotEmpty ? trimmed : previous?.name;
    if (name == null || name.isEmpty) continue;
    final toolset = payload['toolset'] is String
        ? payload['toolset'] as String
        : previous?.toolset;
    final effect = _effectOf(payload['effect']) ?? previous?.effect;
    final createdAt = jsString(event['created_at']);
    if (kind == 'tool.started') {
      calls[id] = ActivityCall(
        id: id,
        name: name,
        toolset: (toolset?.isNotEmpty ?? false) ? toolset : null,
        effect: effect,
        status: 'running',
        startedAt: createdAt,
      );
    }
    if (kind == 'tool.completed' ||
        kind == 'tool.failed' ||
        kind == 'tool.cancelled') {
      final status = kind == 'tool.cancelled'
          ? 'cancelled'
          : kind == 'tool.failed' || payload['ok'] == false
          ? 'failed'
          : 'completed';
      calls[id] = ActivityCall(
        id: id,
        name: name,
        toolset: previous?.toolset,
        effect: previous?.effect,
        startedAt: previous?.startedAt,
        status: status,
        completedAt: createdAt,
      );
    }
  }
  final active = calls.values
      .where((call) => call.status == 'running')
      .toList();
  if (active.isNotEmpty) {
    phase = _toolPhase(active.map((call) => (call.toolset, call.effect)));
  }
  final status = jsString(run['status']);
  phase = _stable[status] ?? phase;
  if (status == 'completed' || status == 'failed' || status == 'cancelled') {
    for (final call in active) {
      calls[call.id] = call.copyWith(status: 'interrupted');
    }
  }
  final all = calls.values.toList();
  return (
    phase: phase,
    avatar: activityAvatar[phase]!,
    calls: all.length > 24 ? all.sublist(all.length - 24) : all,
    observedAt: observedAt,
  );
}

/// The owner-facing line for one tool call, from its toolset and effect; a short override
/// names the few tools whose family label would be wrong (turn-activity.ts:315-331).
String activityCallLabel({
  String? toolset,
  String? effect,
  String? name,
  required String locale,
}) {
  final family = toolset != null && toolset.isNotEmpty
      ? activityCallLabels[toolset]
      : null;
  final override = name != null && name.isNotEmpty
      ? activityToolLabels[name]
      : null;
  final label =
      override ??
      (family == null
          ? null
          : family[effect ?? 'read'] ?? family['change'] ?? family['read']);
  return (label ?? activityGenericCall).pick(
    locale.toLowerCase().startsWith('ar') ? 'ar' : 'en',
  );
}
