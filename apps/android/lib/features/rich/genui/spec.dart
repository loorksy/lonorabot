// Ports of packages/core/src/genui/{spec,input,markdown,submit}.ts and
// packages/contracts/src/genui-catalog.ts: fail-closed validation of compiled lonora-ui v2
// cards, the card's typed numbers, card Markdown, and the shared lock / mark / send rules.
import 'dart:convert';

import '../../../core/json.dart';
import '../../../core/models/models.dart';
import 'expr.dart';

/// The catalog's node set plus the server's delivery row (mandate 10.1.5).
const Set<String> uiNodes = {
  'Segmented',
  'Select',
  'Number',
  'Slider',
  'Text',
  'Title',
  'Markdown',
  'Note',
  'Badge',
  'KeyValue',
  'Stat',
  'Button',
  'Divider',
  'Row',
  'Col',
  'Grid',
  'Card',
  'More',
  'Slot',
  'Delivery',
};
const Set<String> uiActions = {
  'set',
  'toggle',
  'reset',
  'copy',
  'open',
  'go',
  'send',
};
const Set<String> uiRoutes = {'market', 'tasks', 'usage', 'files', 'agents'};
const Set<String> uiSlotCards = {
  'trade_approval',
  'settle',
  'mandate',
  'secret',
};
const Set<String> _kinds = {
  'calculator',
  'form',
  'picker',
  'chart',
  'choice',
  'checklist',
  'quiz',
  'timer',
  'diagram',
  'summary',
};
final RegExp _recordId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$');
const _blockedKeys = {'__proto__', 'prototype', 'constructor'};
const int _maxBytes = 64000;

bool _plain(Object? value) =>
    value is Map &&
    value.keys.every((k) => k is String && !_blockedKeys.contains(k));

bool _json(Object? value, [int depth = 0]) {
  if (depth > 12) return false;
  if (value == null || value is String || value is bool) return true;
  if (value is num) return value.isFinite;
  if (value is List) {
    return value.length <= 200 && value.every((item) => _json(item, depth + 1));
  }
  return _plain(value) &&
      (value as Map).values.every((item) => _json(item, depth + 1));
}

bool _block(Object? value, [int depth = 0]) {
  if (!_plain(value)) return false;
  final b = value as Map;
  final type = b['type'];
  if (type is! String || !uiNodes.contains(type)) return false;
  if (depth > 4 || !isExpression(b['when'])) return false;
  if (type == 'Slot') {
    // A trusted slot (mandate 10.2): top level only, its card and record and nothing else.
    return depth == 0 &&
        b.keys.every((k) => k == 'type' || k == 'card' || k == 'record') &&
        uiSlotCards.contains('${b['card']}') &&
        b['record'] is String &&
        _recordId.hasMatch(b['record'] as String);
  }
  if (type == 'Delivery') {
    final channels = b['channels'];
    return channels is List &&
        channels.every((c) => c == 'app' || c == 'push' || c == 'call');
  }
  if (b.containsKey('children')) {
    final children = b['children'];
    if (children is! List || children.length > 8) return false;
    if (!children.every((child) => _block(child, depth + 1))) return false;
  }
  if (b.containsKey('action') && b['action'] != null) {
    final action = b['action'];
    if (!_plain(action) || !uiActions.contains('${(action as Map)['do']}')) {
      return false;
    }
    if (action['do'] == 'open' &&
        !(action['url'] is String &&
            (action['url'] as String).startsWith('https://'))) {
      return false;
    }
  }
  return true;
}

/// A compiled lonora-ui v2 card, or null when anything is malformed (fail closed).
Json? validateUiDocument(Object? value) {
  try {
    if (!_plain(value)) return null;
    final doc = value as Map;
    if (doc['v'] != 2 || !_json(doc)) return null;
    if (!_kinds.contains('${doc['kind']}') || doc['title'] is! String) {
      return null;
    }
    final fallback = doc['fallback'];
    if (fallback is! String || fallback.length > 1500) return null;
    if (!_plain(doc['facts']) ||
        !_plain(doc['state']) ||
        !_plain(doc['calc'])) {
      return null;
    }
    final calcOk = (doc['calc'] as Map).values.every(
      (source) =>
          source == null ||
          source is bool ||
          (source is num && source.isFinite) ||
          (source is String && isExpression(source)),
    );
    if (!calcOk) return null;
    final blocks = doc['blocks'];
    if (blocks is! List || blocks.length > 14) return null;
    if (!blocks.every(_block)) return null;
    if (utf8.encode(jsonEncode(doc)).length > _maxBytes) return null;
    return asJson(doc);
  } catch (_) {
    return null;
  }
}

/// A lonora-ui v2 part (`{type: ui, document, building?, cut?}`).
class UiPart {
  const UiPart({required this.document, this.building = false, this.cut});
  final Json document;
  final bool building;
  final int? cut;

  List<Json> get blocks => asJsonList(document['blocks']);
}

UiPart? validateUiPart(Json value) {
  const allowed = {'type', 'document', 'building', 'cut'};
  if (!value.keys.every(allowed.contains)) return null;
  final building = value['building'];
  if (building != null && building is! bool) return null;
  final cut = value['cut'];
  if (cut != null && !(cut is int && cut >= 0)) return null;
  final document = validateUiDocument(value['document']);
  if (document == null) return null;
  return UiPart(
    document: document,
    building: building == true,
    cut: cut as int?,
  );
}

bool isUiV2Part(Json part) =>
    part['type'] == 'ui' &&
    _plain(part['document']) &&
    asJson(part['document'])['v'] == 2;

// --- typed numbers (input.ts) ------------------------------------------------------------

final RegExp _arabicDigits = RegExp('[٠-٩۰-۹]');
final RegExp _group = RegExp('[,،٬\\s\u00a0\u202f]');
final RegExp _plainNumber = RegExp(r'^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$');
final RegExp _groupedNumber = RegExp(
  '^[+-]?\\d{1,3}(?:[,،٬\\s\u00a0\u202f]\\d{3})+(?:\\.\\d+)?\$',
);

/// A card's typed number: a number, null for an empty draft, [unreadable] when it cannot be
/// read (review M7). Arabic-Indic / Persian digits and «٬» «٫» are accepted.
const Object unreadable = _Unreadable();

class _Unreadable {
  const _Unreadable();
}

Object? parseCardNumber(String text) {
  final normalized = text
      .trim()
      .replaceAllMapped(_arabicDigits, (m) {
        final d = m[0]!;
        const ar = '٠١٢٣٤٥٦٧٨٩';
        const fa = '۰۱۲۳۴۵۶۷۸۹';
        return '${ar.contains(d) ? ar.indexOf(d) : fa.indexOf(d)}';
      })
      .replaceAll('٫', '.');
  if (normalized.isEmpty) return null;
  if (normalized.length > 64) return unreadable;
  if (!_plainNumber.hasMatch(normalized) &&
      !_groupedNumber.hasMatch(normalized)) {
    return unreadable;
  }
  final parsed = double.tryParse(normalized.split(_group).join());
  return parsed != null && parsed.isFinite ? parsed : unreadable;
}

// --- card Markdown (markdown.ts) ---------------------------------------------------------

class CardInline {
  const CardInline(this.text, {this.bold = false});
  final String text;
  final bool bold;
}

class CardMarkdownBlock {
  CardMarkdownBlock(this.kind);

  /// p, ul or ol.
  final String kind;
  final List<List<CardInline>> lines = [];
}

/// `**bold**` only; a `[label](url)` shows its label and a bare URL stays text.
List<CardInline> cardInline(String text) {
  final labelled = text.replaceAllMapped(
    RegExp(r'\[([^\]\n]+)\]\([^)\s]*\)'),
    (m) => m[1]!,
  );
  final out = <CardInline>[];
  var last = 0;
  for (final m in RegExp(r'\*\*[^*]+\*\*').allMatches(labelled)) {
    if (m.start > last) out.add(CardInline(labelled.substring(last, m.start)));
    final piece = m[0]!;
    out.add(
      piece.length > 4
          ? CardInline(piece.substring(2, piece.length - 2), bold: true)
          : CardInline(piece),
    );
    last = m.end;
  }
  if (last < labelled.length) out.add(CardInline(labelled.substring(last)));
  return out;
}

final RegExp _bullet = RegExp(r'^\s*[-*•]\s+(.*)$');
final RegExp _numbered = RegExp(r'^\s*\d{1,3}[.)]\s+(.*)$');

List<CardMarkdownBlock> cardMarkdown(String text) {
  final blocks = <CardMarkdownBlock>[];
  CardMarkdownBlock? current;
  for (final raw in text.split('\n')) {
    final line = raw.replaceFirst(RegExp(r'^\s*#{1,6}\s+'), '').trimRight();
    if (line.trim().isEmpty) {
      current = null;
      continue;
    }
    final bullet = _bullet.firstMatch(line);
    final number = bullet == null ? _numbered.firstMatch(line) : null;
    final kind = bullet != null
        ? 'ul'
        : number != null
        ? 'ol'
        : 'p';
    final body = bullet?[1] ?? number?[1] ?? line.trim();
    if (current == null || current.kind != kind) {
      current = CardMarkdownBlock(kind);
      blocks.add(current);
    }
    current.lines.add(cardInline(body));
  }
  return blocks;
}

// --- submit rules (submit.ts) ------------------------------------------------------------

const _terminal = {'completed', 'failed', 'cancelled'};
const _waiting = {'waiting_input', 'waiting_takeover'};

/// «مُعدّلة» (superseded) or «لم يُنفَّذ» (not_run): only the server's record counts.
String? submitMark(Message message) {
  final submit = message.uiSubmit;
  if (message.origin != 'ui_submit' || submit == null) return null;
  if (submit['started_at'] != null) return null;
  return asString(submit['mark']) ?? asString(message.raw['ui_mark']);
}

/// The locking submission of one card part, or null.
({String id, int seq})? cardLock(
  Message card,
  int part,
  List<Message> messages,
) {
  final states = asJson(asJson(card.uiState?['parts'])['$part']);
  final unlocked = asInt(states['unlocked_seq']) ?? 0;
  ({String id, int seq})? lock;
  for (final message in messages) {
    final submit = message.uiSubmit;
    if (message.origin != 'ui_submit' ||
        message.replyTo != card.id ||
        submit == null ||
        submit['lock'] != true ||
        asInt(submit['part']) != part ||
        message.seq <= unlocked ||
        submitMark(message) != null) {
      continue;
    }
    if (lock == null || message.seq > lock.seq) {
      lock = (id: message.id, seq: message.seq);
    }
  }
  final derived = asJson(asJson(card.raw['ui_lock'])['$part']);
  final derivedId = asString(derived['message_id']);
  if (lock == null &&
      derivedId != null &&
      !messages.any((m) => m.id == derivedId)) {
    // The page that carried the submission is not loaded: the server's lock holds.
    return (id: derivedId, seq: asInt(derived['seq']) ?? 0);
  }
  return lock;
}

/// Why a send button is disabled right now, or null when it may send.
String? sendBlocked(
  String? agentId,
  String threadId,
  List<Message> messages,
  Iterable<Run> runs, {
  required bool paused,
}) {
  if (paused) return 'paused';
  if (agentId == null) return null;
  final mine = runs
      .where((r) => r.threadId == threadId && r.agentId == agentId)
      .toList();
  if (mine.any((r) => _waiting.contains(r.status))) return 'waiting';
  final queued = messages.any((message) {
    final submit = message.uiSubmit;
    return message.origin == 'ui_submit' &&
        submit != null &&
        submit['started_at'] == null &&
        mine.any(
          (r) => r.id == submit['run_id'] && !_terminal.contains(r.status),
        );
  });
  return queued ? 'queued' : null;
}

/// The `card:record` keys of the trusted slots these messages draw (conversation-timeline.ts
/// `embeddedSlots`): an assistant message whose whole rich content validates, each card up to
/// its cut.
Set<String> embeddedSlots(
  Iterable<Message> messages,
  List<Object?>? Function(Message) validParts,
) {
  final found = <String>{};
  for (final message in messages) {
    if (message.role != 'assistant') continue;
    for (final part in validParts(message) ?? const []) {
      if (part is! UiPart) continue;
      final blocks = part.blocks;
      for (var i = 0; i < blocks.length; i++) {
        if (blocks[i]['type'] != 'Slot') continue;
        if (part.cut != null && i >= part.cut!) continue;
        found.add('${blocks[i]['card']}:${blocks[i]['record']}');
      }
    }
  }
  return found;
}
