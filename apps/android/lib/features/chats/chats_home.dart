// The Chats tab's root. With the last-conversation home (HomeMode.lastChat) it is the
// conversation the owner opened last on this device for this server (else Lonora's own chat,
// else the chat list), with the chat list in the start-side drawer (chat_drawer.dart). With the
// list home (HomeMode.list) it is the chat list, as before.
import 'package:flutter/widgets.dart';

import '../../state/actions/base.dart';
import '../../state/actions/prefs_actions.dart' show lastThreadOf;
import '../../state/app_state.dart';
import '../conversation/conversation_screen.dart';
import 'chat_rows.dart';
import 'chats_screen.dart';

/// The conversation the last-conversation home shows: [requested] (a link to a conversation),
/// else the owner's last opened one, else Lonora's own chat (the personal agent's); null when
/// there is none yet (the home shows the chat list).
String? homeThreadId(AppState state, {String? requested}) {
  if (requested != null && requested.isNotEmpty) return requested;
  final last = lastThreadOf(state.session);
  if (last != null && state.threads[last]?.error != 'thread_not_found') {
    return last;
  }
  for (final row in chatRowsOf(state)) {
    if ((row.agent?.isPersonal ?? false) && row.threadId != null) {
      return row.threadId;
    }
  }
  return null;
}

/// Unread messages in every conversation but [threadId] (archived and muted ones do not count,
/// as on the tab's badge): the drawer button's count.
int unreadElsewhere(ShellState shell, String? threadId) => shell.inbox
    .where((e) => !e.archived && !e.muted && e.threadId != threadId)
    .fold(0, (sum, e) => sum + inboxUnread(e));

class ChatsHome extends StatefulWidget {
  const ChatsHome({super.key, this.threadId, this.around});

  /// The conversation a link asked for (`/chats?thread=…`).
  final String? threadId;

  /// Land on this message seq of [threadId].
  final int? around;

  @override
  State<ChatsHome> createState() => _ChatsHomeState();
}

class _ChatsHomeState extends State<ChatsHome> {
  /// The conversation this home shows. A bare `/chats` (cold start, a tab re-tap, a share) keeps
  /// it: a conversation opened over the home becomes the last opened one, and must not replace
  /// the home under it. Only a link (`?thread=`) moves it, or the conversation no longer existing.
  String? _shown;

  String? _resolve(AppState s) {
    final shown = _shown;
    if (widget.threadId == null &&
        shown != null &&
        s.threads[shown]?.error != 'thread_not_found') {
      return shown;
    }
    return homeThreadId(s, requested: widget.threadId);
  }

  @override
  Widget build(BuildContext context) {
    final mode = context.select((AppState s) => s.prefs.homeMode);
    if (mode == HomeMode.list) {
      // Back in the last-conversation home later, it opens on the last opened conversation.
      _shown = null;
      return const ChatsScreen();
    }
    final id = _shown = context.select(_resolve);
    if (id == null) return const ChatsScreen();
    return ConversationScreen(
      key: ValueKey('home:$id'),
      threadId: id,
      around: id == widget.threadId ? widget.around : null,
      // A conversation pushed over another (an older link) keeps its back button.
      home: ModalRoute.of(context)?.isFirst ?? true,
    );
  }
}
