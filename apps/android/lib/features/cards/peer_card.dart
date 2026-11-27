// A persisted exchange between two agents (packages/core/src/peer-outcome.ts `peerCard`,
// apps/mobile/components/peer-card.tsx): drawn on the message it belongs to, in both
// conversations: who asked whom (the other agent's name opens its conversation), the request
// or the returned result without its machine wrapper, and the status.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/core/values.dart' show jsString;
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../rich/markdown_view.dart';

final RegExp _wrapper = RegExp(
  r'''^<peer_outcome\b[^>]*status=['"]([^'"]+)['"][^>]*>\n([\s\S]*)\n</peer_outcome>$''',
);

/// A colleague's result without its machine wrapper (`peerOutcome`).
({String body, String? status}) peerOutcome(String content) {
  final m = _wrapper.firstMatch(content);
  return m == null
      ? (body: content, status: null)
      : (body: m[2]!, status: m[1]);
}

/// The message ids a peer exchange is shown on (`peersByMessage`).
Map<String, Json> peersByMessage(List<Json> peers) {
  final out = <String, Json>{};
  for (final peer in peers) {
    final p = asJson(peer['payload']);
    for (final id in [
      p['source_message_id'],
      p['target_message_id'],
      p['source_outcome_message_id'],
      p['target_outcome_message_id'],
      ...asStringList(p['source_outcome_message_ids']),
    ]) {
      if (id is String) out[id] = peer;
    }
  }
  return out;
}

class PeerParty {
  const PeerParty({required this.id, required this.name, required this.thread});
  final String id;
  final String name;
  final String thread;
}

class PeerCardData {
  const PeerCardData({
    required this.kind,
    required this.from,
    required this.to,
    required this.status,
    required this.body,
  });

  /// request or outcome.
  final String kind;
  final PeerParty from;
  final PeerParty to;

  /// cancelled, failed, completed, limited, working or queued.
  final String status;

  /// Null for a bare cancellation.
  final String? body;
}

PeerCardData peerCardData(Message message, Json peer, [String? runStatus]) {
  final p = asJson(peer['payload']);
  final request =
      p['source_message_id'] == message.id ||
      p['target_message_id'] == message.id;
  final wrapped = peerOutcome(message.content);
  String side(Object? a, Object? b) => jsString(request ? a : b);
  final from = PeerParty(
    id: side(p['source_agent_id'], p['target_agent_id']),
    name: side(p['source_agent_name'], p['target_agent_name']),
    thread: side(p['source_thread_id'], p['target_thread_id']),
  );
  final to = PeerParty(
    id: side(p['target_agent_id'], p['source_agent_id']),
    name: side(p['target_agent_name'], p['source_agent_name']),
    thread: side(p['target_thread_id'], p['source_thread_id']),
  );
  final raw = wrapped.status ?? runStatus ?? jsString(p['status'] ?? 'queued');
  final status =
      const ['cancelled', 'failed', 'completed', 'limited'].contains(raw)
      ? raw
      : const ['running', 'leased'].contains(raw)
      ? 'working'
      : 'queued';
  return PeerCardData(
    kind: request ? 'request' : 'outcome',
    from: from,
    to: to,
    status: status,
    body: raw == 'cancelled' && wrapped.body == 'cancelled'
        ? null
        : wrapped.body,
  );
}

const Map<String, String> _statusKeys = {
  'cancelled': 'peerCancelled',
  'failed': 'peerFailed',
  'completed': 'peerCompleted',
  'limited': 'peerLimited',
  'working': 'peerWorking',
  'queued': 'peerQueued',
};

/// The peer exchange drawn as the message's body (inside its bubble).
class PeerExchangeView extends StatelessWidget {
  const PeerExchangeView({
    super.key,
    required this.message,
    required this.peer,
    this.runStatus,
  });

  final Message message;
  final Json peer;
  final String? runStatus;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final card = peerCardData(message, peer, runStatus);
    Widget who(PeerParty party) {
      final name = party.name.isEmpty ? context.t('peerAgent') : party.name;
      final link = party.thread.isNotEmpty && party.thread != message.threadId;
      final text = Text(
        name,
        style: ln.text.captionStrong.copyWith(color: link ? c.selection : c.fg),
      );
      if (!link) return text;
      // This conversation is already open: only the other one is a link. The last-conversation
      // home keeps one conversation at the Chats tab's root: the other one takes its place.
      return LnTappable(
        onTap: () {
          final router = GoRouter.maybeOf(context);
          final link = Routes.thread(party.thread);
          if (context.read().prefs.homeMode == HomeMode.lastChat) {
            router?.go(link);
          } else {
            router?.push(link);
          }
        },
        semanticLabel: name,
        excludeChildSemantics: true,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 48),
          child: Center(widthFactor: 1, child: text),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(FIcons.users, size: 16, color: c.fgMuted),
            const SizedBox(width: 6),
            Text(
              context.t('peerCollaboration'),
              style: ln.text.smallStrong.copyWith(color: c.fgMuted),
            ),
          ],
        ),
        Wrap(
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 6,
          children: [
            who(card.from),
            // Lucide's chevron mirrors itself in RTL: it points from asker to receiver.
            Icon(FIcons.chevronRight, size: 14, color: c.fgMuted),
            who(card.to),
          ],
        ),
        if (card.body != null) ...[
          const SizedBox(height: 4),
          MarkdownView(card.body!, selectable: false),
        ],
        const SizedBox(height: 4),
        Semantics(
          liveRegion: true,
          child: Text(
            context.t(_statusKeys[card.status]!),
            style: ln.text.small.copyWith(color: c.fgMuted),
          ),
        ),
      ],
    );
  }
}
