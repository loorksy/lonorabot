// Port of packages/core/src/reply-stream.ts (accumulateStream / seedStream): the fenced,
// bounded live preview of an agent's reply. Identity is (run, turn_id, fence, generation);
// `sequence` counts chunks; a sequence jump marks a gap that is healed by rebasing on the
// durable `run.stream` snapshot.
import '../core/json.dart';
import '../core/models/models.dart';
import '../core/realtime/lonora_event.dart';

const maxStreamChars = 60000;
const _maxTailChunks = 150;

class StreamChunk {
  const StreamChunk({
    required this.sequence,
    required this.text,
    required this.truncated,
    this.richContent,
    this.hasRich = false,
  });
  final int sequence;
  final String text;
  final bool truncated;
  final Json? richContent;
  final bool hasRich;

  StreamChunk withoutRich() =>
      StreamChunk(sequence: sequence, text: text, truncated: truncated);
}

class LiveReplyStream {
  const LiveReplyStream({
    required this.runId,
    required this.threadId,
    required this.agentId,
    required this.turnId,
    required this.fence,
    required this.generation,
    required this.sequence,
    required this.text,
    required this.truncated,
    required this.phase,
    required this.cursor,
    required this.gap,
    required this.chunks,
    this.messageId,
    this.inputSeq,
    this.richContent,
  });

  final String runId;
  final String threadId;
  final String agentId;
  final String turnId;
  final int fence;
  final int generation;
  final int sequence;
  final String text;
  final bool truncated;

  /// streaming | committed | discarded | cancelled | failed
  final String phase;
  final String? messageId;
  final int? inputSeq;
  final Json? richContent;
  final int cursor;
  final bool gap;
  final List<StreamChunk> chunks;

  bool get streaming => phase == 'streaming';

  LiveReplyStream copyWith({
    int? sequence,
    String? text,
    bool? truncated,
    String? phase,
    Object? messageId = _keep,
    Object? richContent = _keep,
    int? inputSeq,
    int? cursor,
    bool? gap,
    List<StreamChunk>? chunks,
  }) => LiveReplyStream(
    runId: runId,
    threadId: threadId,
    agentId: agentId,
    turnId: turnId,
    fence: fence,
    generation: generation,
    sequence: sequence ?? this.sequence,
    text: text ?? this.text,
    truncated: truncated ?? this.truncated,
    phase: phase ?? this.phase,
    messageId: identical(messageId, _keep)
        ? this.messageId
        : messageId as String?,
    richContent: identical(richContent, _keep)
        ? this.richContent
        : richContent as Json?,
    inputSeq: inputSeq ?? this.inputSeq,
    cursor: cursor ?? this.cursor,
    gap: gap ?? this.gap,
    chunks: chunks ?? this.chunks,
  );

  static const _keep = Object();
}

int _compare(int af, int ag, int bf, int bg) => af != bf ? af - bf : ag - bg;

String _bounded(String text) {
  final runes = text.runes;
  if (runes.length <= maxStreamChars) return text;
  return String.fromCharCodes(runes.take(maxStreamChars));
}

LiveReplyStream _append(LiveReplyStream current, StreamChunk chunk) {
  if (chunk.sequence <= current.sequence) return current;
  final gap = current.gap || chunk.sequence != current.sequence + 1;
  final text = gap ? current.text : _bounded(current.text + chunk.text);
  final tail = chunk.hasRich
      ? current.chunks.map((c) => c.withoutRich()).toList()
      : current.chunks;
  final chunks = [...tail, chunk];
  return current.copyWith(
    sequence: chunk.sequence,
    text: text,
    gap: gap,
    truncated: current.truncated || chunk.truncated,
    richContent: chunk.hasRich ? chunk.richContent : LiveReplyStream._keep,
    chunks: chunks.length > _maxTailChunks
        ? chunks.sublist(chunks.length - _maxTailChunks)
        : chunks,
  );
}

Json? _validRich(Object? value) {
  final json = asJson(value);
  if (json.isEmpty) return null;
  return json['parts'] is List ? json : null;
}

const streamKinds = {
  'run.reply_started',
  'run.delta',
  'run.rich_partial',
  'run.reply_committed',
};

/// Every delivered stream event updates this bounded accumulator.
LiveReplyStream? accumulateStream(LiveReplyStream? current, LonoraEvent event) {
  final runId = event.runId;
  if (runId == null) return current;
  if (current != null && runId != current.runId) return current;
  if (current != null && event.cursor < current.cursor) return current;
  if (event.kind == 'run.cancelled' || event.kind == 'run.failed') {
    return current?.copyWith(
      phase: event.kind == 'run.failed' ? 'failed' : 'cancelled',
      cursor: event.cursor,
    );
  }
  if (!streamKinds.contains(event.kind)) return current;
  final p = event.payload;
  final turnId = asString(p['turn_id']);
  final fence = asInt(p['fence']);
  final generation = asInt(p['generation']);
  final sequence = asInt(p['sequence']);
  if (turnId == null ||
      fence == null ||
      fence < 0 ||
      generation == null ||
      generation < 0 ||
      sequence == null ||
      sequence < 0) {
    return current;
  }
  if (current != null &&
      _compare(current.fence, current.generation, fence, generation) > 0) {
    return current;
  }
  final same =
      current != null &&
      current.turnId == turnId &&
      current.fence == fence &&
      current.generation == generation;
  var stream = same
      ? current
      : LiveReplyStream(
          runId: runId,
          threadId: event.threadId ?? '',
          agentId: event.agentId ?? '',
          turnId: turnId,
          fence: fence,
          generation: generation,
          sequence: 0,
          text: '',
          truncated: false,
          phase: 'streaming',
          inputSeq: asInt(p['input_seq']),
          cursor: event.cursor,
          gap: false,
          chunks: const [],
        );
  if (event.kind == 'run.reply_started') {
    return same ? stream : stream.copyWith(cursor: event.cursor);
  }
  // Only a newer fence/generation may replace a terminal preview.
  if (!stream.streaming) return stream;
  final inputSeq = asInt(p['input_seq']);
  if (inputSeq != null) stream = stream.copyWith(inputSeq: inputSeq);
  if (event.kind == 'run.delta' || event.kind == 'run.rich_partial') {
    final rich = _validRich(p['rich_content']);
    stream = _append(
      stream,
      StreamChunk(
        sequence: sequence,
        text: event.kind == 'run.delta' ? asStr(p['text']) : '',
        truncated: p['truncated'] == true,
        richContent: rich,
        hasRich: rich != null,
      ),
    );
    return stream.copyWith(
      cursor: stream.cursor > event.cursor ? stream.cursor : event.cursor,
    );
  }
  if (sequence < stream.sequence) return stream;
  final discarded = p['phase'] == 'discarded';
  return stream.copyWith(
    sequence: sequence > stream.sequence ? sequence : stream.sequence,
    phase: discarded ? 'discarded' : 'committed',
    richContent: discarded ? null : _validRich(p['rich_content']),
    messageId: asString(p['message_id']),
    cursor: event.cursor,
  );
}

/// Rebase on the committed DB preview (`run.stream`), then apply only later contiguous chunks.
LiveReplyStream? seedStream(LiveReplyStream? current, Run run) {
  final s = run.stream;
  if (s == null) return current;
  final fence = asInt(s['fence']) ?? 0;
  final generation = asInt(s['generation']) ?? 0;
  final sequence = asInt(s['sequence']) ?? 0;
  final turnId = asStr(s['turn_id']);
  final phase = asStr(s['phase'], 'streaming');
  if (current != null &&
      _compare(current.fence, current.generation, fence, generation) > 0) {
    return current;
  }
  final same =
      current != null &&
      current.turnId == turnId &&
      _compare(current.fence, current.generation, fence, generation) == 0;
  if (same && !current.gap && current.sequence > sequence) return current;
  var rebased = LiveReplyStream(
    runId: run.id,
    threadId: run.threadId,
    agentId: run.agentId,
    turnId: turnId,
    fence: fence,
    generation: generation,
    sequence: sequence,
    text: asStr(s['text']),
    truncated: asBool(s['truncated']),
    phase: phase,
    messageId: asString(s['message_id']),
    inputSeq: asInt(s['input_seq']),
    richContent: phase == 'discarded' ? null : _validRich(s['rich_content']),
    cursor: current?.cursor ?? 0,
    gap: false,
    chunks: const [],
  );
  if (same) {
    if (phase == 'streaming') {
      for (final chunk in current.chunks) {
        rebased = _append(rebased, chunk);
      }
      if (current.sequence > rebased.sequence) {
        rebased = rebased.copyWith(gap: true);
      }
    }
    if (!current.streaming && phase == 'streaming') {
      rebased = rebased.copyWith(
        phase: current.phase,
        messageId: current.messageId,
        richContent: current.richContent,
      );
    }
  }
  return rebased;
}
