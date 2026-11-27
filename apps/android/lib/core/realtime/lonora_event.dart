import '../json.dart';

/// One envelope of the owner's durable event feed (`/api/ws/events`).
class LonoraEvent {
  const LonoraEvent({
    required this.cursor,
    required this.kind,
    this.threadId,
    this.agentId,
    this.runId,
    this.payload = const {},
    this.createdAt,
  });

  final int cursor;
  final String kind;
  final String? threadId;
  final String? agentId;
  final String? runId;
  final Json payload;
  final DateTime? createdAt;

  static LonoraEvent? fromJson(Json json) {
    final cursor = asInt(json['cursor']);
    final kind = asString(json['kind']);
    if (cursor == null || kind == null) return null;
    return LonoraEvent(
      cursor: cursor,
      kind: kind,
      threadId: asString(json['thread_id']),
      agentId: asString(json['agent_id']),
      runId: asString(json['run_id']),
      payload: asJson(json['payload']),
      createdAt: asDate(json['created_at']),
    );
  }

  /// High-frequency kinds that never need a snapshot refetch (apps/mobile/app/thread.tsx:575-660).
  bool get isStreamChunk =>
      kind == 'run.delta' ||
      kind == 'run.rich_partial' ||
      kind == 'run.reply_started' ||
      kind == 'run.progress' ||
      kind.startsWith('tool.');

  @override
  String toString() =>
      'LonoraEvent($cursor, $kind, thread=$threadId, run=$runId)';
}

enum StreamStatus { idle, connecting, connected, reconnecting, offline }
