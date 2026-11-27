// Port of `validateRichContent` (packages/core/src/visual-response.ts) and message-parts.ts:
// a message's `rich_content {version: 1, parts[]}` validated fail closed. One malformed part
// rejects the whole rich content, and the message then reads as its plain `content`.
import 'dart:convert';

import '../../core/json.dart';
import '../../core/models/models.dart';
import 'genui/spec.dart';
import 'visual/visual_document.dart';

sealed class RichPart {
  const RichPart();
}

class TextPart extends RichPart {
  const TextPart(this.text);
  final String text;
}

/// A lonora-ui v2 card part.
class CardPart extends RichPart {
  const CardPart(this.card);
  final UiPart card;
}

/// A legacy v1 visual document (rendered only).
class VisualPart extends RichPart {
  const VisualPart(this.document);
  final Json document;
}

/// An owner voice note (server-written): the transcript is the message's content.
class VoicePart extends RichPart {
  const VoicePart({
    required this.artifactId,
    required this.duration,
    required this.peaks,
    required this.transcriptStatus,
  });
  final String artifactId;

  /// Seconds, 0 < duration <= 120.
  final double duration;

  /// Exactly 44 bars, each 0..100.
  final List<int> peaks;

  /// pending, done or failed.
  final String transcriptStatus;
}

/// A call log bubble (server-written system message).
class CallPart extends RichPart {
  const CallPart({
    required this.direction,
    required this.durationSeconds,
    required this.missed,
  });
  final String direction;
  final int durationSeconds;
  final bool missed;
}

/// The / command an owner message is (server-written).
class CommandPart extends RichPart {
  const CommandPart({
    required this.name,
    required this.argument,
    this.skillId,
    this.skillName,
  });

  /// task, search, summary or skill.
  final String name;
  final String argument;
  final String? skillId;
  final String? skillName;
}

bool _fieldsOnly(Map value, Set<String> fields) =>
    value.keys.every(fields.contains);

final Expando<List<RichPart>> _cache = Expando('rich-parts');
final Expando<bool> _invalid = Expando('rich-invalid');

/// The validated parts of [value] in stored order (a v2 submission names its part by its
/// index), or null when the rich content is missing or anything in it is malformed.
List<RichPart>? validateRichContent(Object? value) {
  if (value is! Map) return null;
  final cached = _cache[value];
  if (cached != null) return cached;
  if (_invalid[value] == true) return null;
  final parts = _validate(value);
  if (parts == null) {
    _invalid[value] = true;
  } else {
    _cache[value] = parts;
  }
  return parts;
}

List<RichPart>? _validate(Map value) {
  try {
    if (!_fieldsOnly(value, const {'version', 'parts'}) ||
        value['version'] != 1) {
      return null;
    }
    final raw = value['parts'];
    if (raw is! List || raw.isEmpty || raw.length > 24) return null;
    final parts = <RichPart>[];
    for (final item in raw) {
      if (item is! Map) return null;
      final part = asJson(item);
      final type = part['type'];
      if (type == 'text') {
        final text = part['text'];
        if (!_fieldsOnly(part, const {'type', 'text'}) ||
            text is! String ||
            text.length > 32000) {
          return null;
        }
        parts.add(TextPart(text));
      } else if (type == 'ui' && isUiV2Part(part)) {
        final card = validateUiPart(part);
        if (card == null) return null;
        parts.add(CardPart(card));
      } else if (type == 'voice') {
        final id = part['artifact_id'];
        final duration = part['duration'];
        final peaks = part['peaks'];
        if (!_fieldsOnly(part, const {
              'type',
              'artifact_id',
              'duration',
              'peaks',
              'transcript_status',
            }) ||
            id is! String ||
            !resourcePattern.hasMatch(id) ||
            duration is! num ||
            !duration.isFinite ||
            duration <= 0 ||
            duration > 120 ||
            peaks is! List ||
            peaks.length != 44 ||
            !peaks.every(
              (p) =>
                  p is num && p == p.truncateToDouble() && p >= 0 && p <= 100,
            ) ||
            !const [
              'pending',
              'done',
              'failed',
            ].contains(part['transcript_status'])) {
          return null;
        }
        parts.add(
          VoicePart(
            artifactId: id,
            duration: duration.toDouble(),
            peaks: [for (final p in peaks) (p as num).toInt()],
            transcriptStatus: part['transcript_status'] as String,
          ),
        );
      } else if (type == 'call') {
        final seconds = part['duration_seconds'];
        if (!_fieldsOnly(part, const {
              'type',
              'direction',
              'duration_seconds',
              'missed',
            }) ||
            !const ['outgoing', 'incoming'].contains(part['direction']) ||
            seconds is! num ||
            seconds != seconds.truncateToDouble() ||
            seconds < 0 ||
            part['missed'] is! bool) {
          return null;
        }
        parts.add(
          CallPart(
            direction: part['direction'] as String,
            durationSeconds: seconds.toInt(),
            missed: part['missed'] as bool,
          ),
        );
      } else if (type == 'command') {
        final argument = part['argument'];
        bool text(Object? v) => v == null || v is String;
        if (!_fieldsOnly(part, const {
              'type',
              'name',
              'argument',
              'skill_id',
              'skill_name',
            }) ||
            !const [
              'task',
              'search',
              'summary',
              'skill',
            ].contains(part['name']) ||
            argument is! String ||
            argument.runes.length > 30000 ||
            !text(part['skill_id']) ||
            !text(part['skill_name'])) {
          return null;
        }
        parts.add(
          CommandPart(
            name: part['name'] as String,
            argument: argument,
            skillId: part['skill_id'] as String?,
            skillName: part['skill_name'] as String?,
          ),
        );
      } else {
        if (type != 'ui' || !_fieldsOnly(part, const {'type', 'document'})) {
          return null;
        }
        final document = validateVisualDocument(part['document']);
        if (document == null) return null;
        parts.add(VisualPart(document));
      }
    }
    if (utf8.encode(jsonEncode(value)).length > 128000) return null;
    return parts;
  } catch (_) {
    return null;
  }
}

/// The voice note part of [message], else null.
VoicePart? voicePartOf(Message message) =>
    validateRichContent(message.richContent)
        ?.whereType<VoicePart>()
        .firstOrNull;

/// The call log part of [message], else null.
CallPart? callPartOf(Message message) =>
    validateRichContent(message.richContent)?.whereType<CallPart>().firstOrNull;

/// The / command part of an owner message, else null.
CommandPart? commandPartOf(Message message) =>
    validateRichContent(message.richContent)
        ?.whereType<CommandPart>()
        .firstOrNull;

/// The artifact ids a message's v1 documents already show as images, so its attachment
/// cards can skip them (native-rich-response.tsx `nativeRichImageIds`).
Set<String> richImageIds(Message message) {
  final ids = <String>{};
  for (final part
      in validateRichContent(message.richContent) ?? const <RichPart>[]) {
    if (part is VisualPart) ids.addAll(visualImageIds(part.document));
  }
  return ids;
}

/// The parts the renderer draws for an agent message (assistant rich content only).
List<RichPart>? drawnParts(Message message) =>
    message.fromAgent ? validateRichContent(message.richContent) : null;

/// The `card:record` keys of the trusted slots loaded messages draw.
Set<String> drawnSlots(Iterable<Message> messages) => embeddedSlots(
  messages,
  (m) => [
    for (final part in drawnParts(m) ?? const <RichPart>[])
      if (part is CardPart) part.card,
  ],
);

/// Whether rich content [json] has the given part type anywhere (cheap check).
bool hasPartType(Json? json, String type) =>
    asJsonList(json?['parts']).any((p) => p['type'] == type);
