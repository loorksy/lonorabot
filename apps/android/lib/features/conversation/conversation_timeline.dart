// What the conversation draws, in order: canonical messages, the owner's unsent messages
// (outbox), live reply previews, run status rows and the cards of the cards feature. Pure
// functions (no widgets) ported from Lonora's clients:
// - apps/mobile/lib/conversation-projection.ts (`projectConversation`: where a preview goes),
// - packages/core/src/thread-questions.ts, run-state.ts (`retryableFailure`, `stopTargets`),
// - packages/core/src/genui/submit.ts (`submitMark`), apps/mobile/lib/message-actions.ts,
// - packages/core/src/time-separators.ts (via the l10n port).
import 'dart:math' as math;

import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../l10n/l10n.dart' show needsTimeSeparator;
import '../../state/app_state.dart';
import '../../state/reply_stream.dart';
import '../cards/thread_cards.dart';

/// One row of the transcript, before presentation.
sealed class TimelineItem {
  const TimelineItem(this.key, this.order, [this.tie = 0]);

  /// Stable identity (list keys, jump targets).
  final String key;

  /// Position: the server seq, with fractions for rows placed after a message.
  final double order;

  /// Breaks ties between rows of one kind at the same [order] (a card's index in the cards
  /// list, which already orders cards that share a seq).
  final int tie;

  int get _rank;
}

class MessageItem extends TimelineItem {
  MessageItem(this.message) : super('m:${message.id}', message.seq.toDouble());
  final Message message;
  @override
  int get _rank => 3;
}

/// An owner send the server has not acknowledged (sending, queued for the network, failed).
class OutgoingItem extends TimelineItem {
  OutgoingItem(this.outgoing, double order)
    : super('o:${outgoing.nonce}', order);
  final OutgoingMessage outgoing;
  @override
  int get _rank => 5;
}

/// A reply being written: the live stream when it has text, else the typing bubble.
class PreviewItem extends TimelineItem {
  PreviewItem(
    this.run,
    this.stream, {
    required this.visible,
    required double order,
    this.at,
  }) : super('p:${run.id}', order);
  final Run run;
  final LiveReplyStream? stream;

  /// The stream has text or rich parts to draw.
  final bool visible;
  final DateTime? at;
  @override
  int get _rank => 4;
}

/// A finished run the owner should know about: failed or stopped without a drawn reply.
class RunStatusItem extends TimelineItem {
  RunStatusItem(this.run, double order) : super('r:${run.id}', order);
  final Run run;
  @override
  int get _rank => 4;
}

/// A card of the cards feature (owner action, approval, receipt, peer exchange…).
class CardItem extends TimelineItem {
  CardItem(this.card, double order, int index)
    : super('c:${card.key}', order, index);
  final TimelineCard card;
  @override
  int get _rank => 2;
}

const _activeOrWaiting = {
  'queued',
  'leased',
  'running',
  'waiting_input',
  'waiting_takeover',
};
const _drawnPhases = {'streaming', 'committed', 'cancelled', 'failed'};

bool streamHasContent(LiveReplyStream? s) =>
    s != null &&
    (s.text.isNotEmpty || asJsonList(s.richContent?['parts']).isNotEmpty);

/// Orders everything the conversation shows (oldest first).
List<TimelineItem> buildTimeline({
  required ThreadState thread,
  List<OutgoingMessage> outbox = const [],
  List<TimelineCard> cards = const [],
}) {
  final canonical = thread.messages;
  final items = <TimelineItem>[for (final m in canonical) MessageItem(m)];
  final last = canonical.isEmpty ? 0 : canonical.last.seq;
  final minimum = canonical.isEmpty ? 0 : canonical.first.seq;
  final ids = {for (final m in canonical) m.id};
  final accepted = {
    for (final m in canonical)
      if (m.clientNonce != null) m.clientNonce!,
  };

  final pending =
      outbox
          .where(
            (o) => o.threadId == thread.threadId && !accepted.contains(o.nonce),
          )
          .toList()
        ..sort((a, b) => a.createdAt.compareTo(b.createdAt));
  for (var i = 0; i < pending.length; i++) {
    items.add(OutgoingItem(pending[i], last + 0.6 + i * 0.001));
  }

  for (final run in thread.runs.values) {
    if (run.threadId.isNotEmpty && run.threadId != thread.threadId) continue;
    final stream = thread.streams[run.id];
    if (stream?.messageId != null && ids.contains(stream!.messageId)) continue;
    final active = _activeOrWaiting.contains(run.status);
    if (stream?.phase == 'committed' && canonical.isEmpty) continue;
    final visible =
        stream != null &&
        _drawnPhases.contains(stream.phase) &&
        streamHasContent(stream);
    final inputSeq = stream?.inputSeq ?? run.inputSeq;
    final input = _inputOf(canonical, run, inputSeq);
    final ownersReply =
        (run.trigger == 'user' || run.trigger == 'group') &&
        run.parentRunId == null;
    final anchor =
        inputSeq ??
        input?.seq ??
        _lastOwnerBefore(canonical, run.createdAt) ??
        0;
    if (!active && !visible) {
      if (_reportsEnd(run, ownersReply) && anchor >= minimum && input != null) {
        items.add(RunStatusItem(run, anchor + 0.25));
      }
      continue;
    }
    if (!visible && (input == null || !ownersReply)) continue;
    if (anchor < minimum) continue;
    final at =
        canonical.where((m) => m.seq == anchor).firstOrNull?.createdAt ??
        run.createdAt;
    items.add(
      PreviewItem(run, stream, visible: visible, order: anchor + 0.125, at: at),
    );
    if (visible && (run.status == 'failed' || run.status == 'cancelled')) {
      if (_reportsEnd(run, ownersReply)) {
        items.add(RunStatusItem(run, anchor + 0.25));
      }
    }
  }

  for (final (i, card) in cards.indexed) {
    items.add(CardItem(card, _cardOrder(card, canonical, last), i));
  }

  // Cards that share a seq keep the order of the cards list (List.sort is not stable).
  items.sort((a, b) {
    final byOrder = a.order.compareTo(b.order);
    if (byOrder != 0) return byOrder;
    final byRank = a._rank.compareTo(b._rank);
    if (byRank != 0) return byRank;
    final byTie = a.tie.compareTo(b.tie);
    return byTie != 0 ? byTie : a.key.compareTo(b.key);
  });
  return items;
}

/// A failed reply is reported unless it ran in the background (then only a model access or
/// quota failure is news the owner can act on); a stopped one when it answered the owner.
bool _reportsEnd(Run run, bool ownersReply) {
  if (run.status == 'failed') {
    if (!run.background) return true;
    final family = runFailure(run).family;
    return family == 'model' || family == 'quota';
  }
  return run.status == 'cancelled' && !run.background && ownersReply;
}

Message? _inputOf(List<Message> canonical, Run run, int? inputSeq) {
  Message? found;
  for (final m in canonical) {
    if (!m.fromOwner) continue;
    final matches = inputSeq != null
        ? m.seq == inputSeq
        : (m.createdAt != null &&
              run.createdAt != null &&
              !m.createdAt!.isAfter(run.createdAt!));
    if (matches && (found == null || m.seq > found.seq)) found = m;
  }
  return found;
}

int? _lastOwnerBefore(List<Message> canonical, DateTime? at) {
  int? seq;
  for (final m in canonical) {
    if (m.fromOwner &&
        at != null &&
        m.createdAt != null &&
        !m.createdAt!.isAfter(at)) {
      seq = math.max(seq ?? 0, m.seq);
    }
  }
  return seq;
}

/// A card anchored to a message sits right after it; one anchored in time sits before the
/// first message written at or after that time (else at the end).
double _cardOrder(TimelineCard card, List<Message> canonical, int last) {
  if (card.seq != null) return card.seq! + 0.5;
  for (final m in canonical) {
    final at = m.createdAt;
    if (at != null && !at.isBefore(card.at)) return m.seq - 0.5;
  }
  return last + 0.55;
}

/// Who wrote a row, for the vertical rhythm and group sender rows.
String senderOf(TimelineItem item) => switch (item) {
  MessageItem(:final message) => switch (message.role) {
    'user' => 'owner',
    'assistant' => 'agent:${message.agentId ?? ''}',
    _ => 'event',
  },
  OutgoingItem() => 'owner',
  PreviewItem(:final run) => 'agent:${run.agentId}',
  RunStatusItem() => 'event',
  CardItem() => 'card',
};

DateTime? timeOf(TimelineItem item) => switch (item) {
  MessageItem(:final message) => message.createdAt,
  OutgoingItem(:final outgoing) => outgoing.createdAt,
  PreviewItem(:final at) => at,
  _ => null,
};

/// A transcript row with its presentation: the time separator above it, the gap to the row
/// before it, whether a group conversation names its sender, and whether its bubble joins the
/// bubble of the same sender right above ([joinTop]) or right below ([joinBottom]).
class TimelineRow {
  const TimelineRow({
    required this.item,
    required this.gap,
    this.separator,
    this.showSender = false,
    this.joinTop = false,
    this.joinBottom = false,
  });

  final TimelineItem item;
  final double gap;
  final bool joinTop;
  final bool joinBottom;

  /// Draw a time separator for this time above the row.
  final DateTime? separator;
  final bool showSender;
}

/// Lonora groups one sender's rows written less than 3 minutes apart (apps/mobile thread.tsx
/// `grouped`).
const groupWindow = Duration(minutes: 3);

/// Same-sender rows sit 7 dp apart and a change of sender 16 dp; a card after its agent's bubble
/// belongs to the same sender. Rows of one sender further apart than [groupWindow] start a new
/// group. Event rows carry their own 8 dp padding. Separators follow Lonora's rule: a new day or a
/// 15 minute pause.
///
/// A run of one sender's bubbles sits [bubbleRunGap] apart with joined corners: a row whose top is
/// its bubble ([startsWithBubble]) under a row whose bottom is its bubble ([endsWithBubble]), both
/// of one sender in one group. Without the predicates nothing joins.
List<TimelineRow> presentTimeline(
  List<TimelineItem> items, {
  required bool group,
  required double sameSenderGap,
  required double senderChangeGap,
  double? bubbleRunGap,
  bool Function(TimelineItem item)? startsWithBubble,
  bool Function(TimelineItem item)? endsWithBubble,
}) {
  final rows = <TimelineRow>[];
  DateTime? lastTime;
  DateTime? previousAt;
  String? previousSender;
  for (final item in items) {
    final at = timeOf(item);
    DateTime? separator;
    if (at != null && (item is MessageItem || item is OutgoingItem)) {
      if (needsTimeSeparator(at, lastTime)) separator = at;
      lastTime = at;
    }
    final sender = senderOf(item);
    final close =
        at == null ||
        previousAt == null ||
        at.difference(previousAt).abs() < groupWindow;
    final same =
        separator == null &&
        previousSender != null &&
        close &&
        (sender == previousSender ||
            (sender == 'card' && previousSender.startsWith('agent:')));
    final joined =
        same &&
        sender == previousSender &&
        sender != 'card' &&
        sender != 'event' &&
        rows.isNotEmpty &&
        (startsWithBubble?.call(item) ?? false) &&
        (endsWithBubble?.call(rows.last.item) ?? false);
    final double gap;
    if (rows.isEmpty || separator != null) {
      // The separator's own padding spaces it from the row before.
      gap = 0;
    } else if (sender == 'event' || previousSender == 'event') {
      gap = sender == 'event' ? sameSenderGap : 0;
    } else if (joined) {
      gap = bubbleRunGap ?? sameSenderGap;
    } else {
      gap = same ? sameSenderGap : senderChangeGap;
    }
    if (joined) {
      final above = rows.removeLast();
      rows.add(
        TimelineRow(
          item: above.item,
          gap: above.gap,
          separator: above.separator,
          showSender: above.showSender,
          joinTop: above.joinTop,
          joinBottom: true,
        ),
      );
    }
    final agentRow = sender.startsWith('agent:') && sender != 'agent:';
    rows.add(
      TimelineRow(
        item: item,
        gap: gap,
        separator: separator,
        showSender: group && agentRow && !(same && sender == previousSender),
        joinTop: joined,
      ),
    );
    previousSender = sender;
    previousAt = at;
  }
  return rows;
}

/// The questions this conversation shows, keyed by the message that holds each. A background
/// run's question copied here names this thread; a request without a thread is in its run's.
Map<String, InputRequest> threadQuestions(Iterable<Run> runs, String threadId) {
  final out = <String, InputRequest>{};
  for (final run in runs) {
    final raw = asJsonList(run.raw['input_requests']);
    for (var i = 0; i < run.inputRequests.length; i++) {
      final request = run.inputRequests[i];
      final rawThread = i < raw.length ? asString(raw[i]['thread_id']) : null;
      final messageId = request.messageId;
      if (messageId == null) continue;
      if ((rawThread ?? run.threadId) == threadId) out[messageId] = request;
    }
  }
  return out;
}

/// Why a reply failed: the server's family, else one read from the error code.
({String family, int? retryAfter}) runFailure(Run run) {
  final family = asString(run.failure?['family']);
  if (family != null && family.isNotEmpty) {
    return (
      family: family,
      retryAfter: asInt(run.failure?['retry_after_seconds']),
    );
  }
  final code = run.errorCode ?? '';
  if (RegExp('quota|budget|insufficient|billing').hasMatch(code)) {
    return (family: 'quota', retryAfter: null);
  }
  if (code.contains('rate')) return (family: 'rate', retryAfter: 30);
  if (RegExp('timeout|timed_out|deadline').hasMatch(code)) {
    return (family: 'timeout', retryAfter: null);
  }
  if (RegExp('model|provider').hasMatch(code)) {
    return (family: 'model', retryAfter: null);
  }
  return (family: 'other', retryAfter: null);
}

/// The failed reply a Retry may re-ask: the newest owner-answering run, failed in a provider
/// family and not retried yet. [ready] is false while the provider's Retry-After lasts.
({Run run, bool ready, DateTime? until})? retryableFailure(
  Iterable<Run> runs,
  DateTime now,
) {
  final candidates =
      runs
          .where(
            (r) =>
                (r.trigger == 'user' || r.trigger == 'group') &&
                r.parentRunId == null,
          )
          .toList()
        ..sort(
          (a, b) => (b.createdAt ?? DateTime(0)).compareTo(
            a.createdAt ?? DateTime(0),
          ),
        );
  if (candidates.isEmpty) return null;
  final newest = candidates.first;
  if (newest.status != 'failed') return null;
  final retried = {
    for (final r in runs)
      if (asString(r.modelMetadata['retry_of']) case final String id) id,
  };
  if (retried.contains(newest.id)) return null;
  final failure = runFailure(newest);
  if (failure.family == 'other') return null;
  final until = failure.retryAfter == null || newest.updatedAt == null
      ? null
      : newest.updatedAt!.add(Duration(seconds: failure.retryAfter!));
  return (
    run: newest,
    ready: until == null || !now.isBefore(until),
    until: until,
  );
}

/// The run of Lonora's run banner (apps/mobile thread.tsx): the newest run waiting for the
/// owner's reply or a takeover, or failed with news the owner can act on (a background run only
/// for its model access or quota). Null when there is none, or when the transcript already
/// draws that run with its controls ([drawn]: runs with a preview or an end row).
Run? bannerRun(Iterable<Run> runs, Set<String> drawn) {
  final newest = runs.toList()
    ..sort(
      (a, b) =>
          (b.createdAt ?? DateTime(0)).compareTo(a.createdAt ?? DateTime(0)),
    );
  final run = newest.where(_bannerWorthy).firstOrNull;
  return run == null || drawn.contains(run.id) ? null : run;
}

bool _bannerWorthy(Run r) {
  if (r.status == 'waiting_input' || r.status == 'waiting_takeover') {
    return true;
  }
  if (r.status != 'failed') return false;
  final family = runFailure(r).family;
  return !r.background || family == 'model' || family == 'quota';
}

/// Stop cancels every cancellable run of the thread (a queued card submit included).
List<Run> stopTargets(Iterable<Run> runs, String threadId) => runs
    .where(
      (r) =>
          r.threadId == threadId &&
          (r.isActive ||
              r.status == 'waiting_input' ||
              r.status == 'waiting_takeover'),
    )
    .toList();

bool _drawnPart(Message m) => m.parts.any((p) => p['type'] != 'text');

/// «تعديل وإعادة الإرسال»: the owner's own plain text (no voice note, no files), not yet
/// replaced, never a card's send.
bool canEditAndResend(Message m) =>
    m.fromOwner &&
    m.attachmentIds.isEmpty &&
    !_drawnPart(m) &&
    m.supersededBy == null &&
    m.origin != 'ui_submit';

/// «تحويل إلى مهمة»: a text message, never a drawn answer, a voice note or files.
bool canTurnIntoTask(Message m) =>
    m.content.trim().isNotEmpty && m.attachmentIds.isEmpty && !_drawnPart(m);

/// The owner's own quick reaction on a message.
String? ownerReaction(List<Reaction> reactions) =>
    reactions.where((r) => r.reactor == 'owner').firstOrNull?.emoji;

/// A card's send that never ran says so: superseded (edited) or not carried out.
String? submitMark(Message m) {
  if (m.origin != 'ui_submit' || m.uiSubmit == null) return null;
  if (m.uiSubmit!['started_at'] != null) return null;
  return asString(m.uiSubmit!['mark']) ?? asString(m.raw['ui_mark']);
}

/// One readable line of a message for quotes and previews (Markdown marks stripped).
String plainLine(String text) => text
    .replaceAll(RegExp(r'```[\s\S]*?```'), ' ')
    .replaceAll(RegExp(r'!\[[^\]]*\]\([^)]*\)'), ' ')
    .replaceAllMapped(RegExp(r'\[([^\]]*)\]\([^)]*\)'), (m) => m[1] ?? '')
    .replaceAll(RegExp(r'[*_`>#~|]'), '')
    .replaceAll(RegExp(r'\s+'), ' ')
    .trim();

const _imageTypes = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'};

bool isImageType(String mediaType) =>
    _imageTypes.contains(mediaType.split(';').first.trim().toLowerCase());

/// "PDF", "PNG", "PLAIN"… from a media type.
String mimeBadge(String mediaType) {
  final value = mediaType.split(';').first.split('/').last;
  return (value.isEmpty ? 'file' : value)
      .replaceFirst(RegExp('^x-'), '')
      .replaceFirst(RegExp(r'\+xml$'), '')
      .toUpperCase();
}

const _byExtension = {
  'png': 'image/png',
  'jpg': 'image/jpeg',
  'jpeg': 'image/jpeg',
  'webp': 'image/webp',
  'gif': 'image/gif',
  'heic': 'image/heic',
  'pdf': 'application/pdf',
  'txt': 'text/plain',
  'md': 'text/markdown',
  'csv': 'text/csv',
  'json': 'application/json',
  'html': 'text/html',
  'xml': 'application/xml',
  'yaml': 'application/yaml',
  'yml': 'application/yaml',
  'doc': 'application/msword',
  'docx':
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'xls': 'application/vnd.ms-excel',
  'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'ppt': 'application/vnd.ms-powerpoint',
  'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'zip': 'application/zip',
  'mp3': 'audio/mpeg',
  'm4a': 'audio/mp4',
  'ogg': 'audio/ogg',
  'wav': 'audio/wav',
  'webm': 'audio/webm',
  'mp4': 'video/mp4',
  'mov': 'video/quicktime',
};

/// The media type a file's name suggests (the server stores the multipart part's type).
String? mimeFor(String fileName) {
  final dot = fileName.lastIndexOf('.');
  if (dot < 0 || dot == fileName.length - 1) return null;
  return _byExtension[fileName.substring(dot + 1).toLowerCase()];
}
