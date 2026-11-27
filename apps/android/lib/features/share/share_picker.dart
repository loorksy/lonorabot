// «إرسال إلى…»: content shared into Lonora from another app (`pendingShare`,
// lib/app/deep_links.dart) waits for the owner to choose the conversation it goes to (composed from
// the kit: a search field over list rows). Picking addresses the payload to that conversation and
// opens it — its composer takes it; dismissing the picker drops it.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';

import '../../app/deep_links.dart';
import '../../app/routes.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/app_state.dart';
import '../chats/chat_commands.dart';
import '../chats/chat_rows.dart';
import '../chats/chat_text.dart';
import '../chats/chat_widgets.dart';
import '../chats/chats_actions.dart';
import '../chats/chats_strings.dart';

/// Watches [pendingShare] and, while the owner is signed in, shows the [ShareTargetPicker] once
/// for each new payload. Mount it under the store and the router (for example around the home
/// shell, or in `MaterialApp.router`'s builder); it shows the sheet on [navigatorKey]'s
/// navigator (the app passes its root navigator's key).
class ShareListener extends StatefulWidget {
  const ShareListener({
    super.key,
    required this.child,
    required this.navigatorKey,
  });

  final Widget child;
  final GlobalKey<NavigatorState> navigatorKey;

  @override
  State<ShareListener> createState() => _ShareListenerState();
}

class _ShareListenerState extends State<ShareListener> {
  SharedPayload? _shown;
  bool _scheduled = false;

  GlobalKey<NavigatorState> get _navigator => widget.navigatorKey;

  @override
  void initState() {
    super.initState();
    pendingShare.addListener(_schedule);
  }

  @override
  void dispose() {
    pendingShare.removeListener(_schedule);
    super.dispose();
  }

  void _schedule() {
    if (_scheduled || !mounted) return;
    _scheduled = true;
    WidgetsBinding.instance
      ..addPostFrameCallback((_) {
        _scheduled = false;
        _check();
      })
      // An idle app draws no frame by itself.
      ..ensureVisualUpdate();
  }

  void _check() {
    if (!mounted) return;
    final payload = pendingShare.value;
    if (payload == null) {
      _shown = null;
      return;
    }
    if (identical(payload, _shown) || payload.targetThreadId != null) return;
    if (!context.read().session.signedIn) return;
    final nav = _navigator.currentContext;
    if (nav == null || !nav.mounted) {
      _schedule();
      return;
    }
    _shown = payload;
    _present(nav, payload);
  }

  Future<void> _present(BuildContext nav, SharedPayload payload) async {
    final row = await showShareTargetPicker(nav, payload);
    if (!mounted || !identical(pendingShare.value, payload)) return;
    if (row == null) {
      pendingShare.value = null;
      return;
    }
    final target = _navigator.currentContext ?? nav;
    if (!target.mounted) return;
    var id = row.threadId;
    if (id == null || id.isEmpty) {
      final action = OpenRowAction(row);
      if (!await runChatsAction(target, action)) {
        // The share still waits: offer the picker again.
        _shown = null;
        _schedule();
        return;
      }
      id = action.threadId;
    }
    if (id == null || id.isEmpty || !target.mounted) return;
    // Addressed to the picked conversation only: no other open conversation takes it.
    final addressed = payload.withTarget(id);
    _shown = addressed;
    pendingShare.value = addressed;
    GoRouter.of(target).go(Routes.thread(id));
  }

  @override
  Widget build(BuildContext context) {
    final signedIn = context.select((AppState s) => s.session.signedIn);
    if (signedIn && pendingShare.value != null) _schedule();
    return widget.child;
  }
}

/// Shows the picker as a sheet; completes with the chosen row, or null when dismissed.
Future<ChatRow?> showShareTargetPicker(
  BuildContext context,
  SharedPayload payload,
) {
  registerChatsStrings();
  return showLnSheet<ChatRow>(
    context,
    title: context.t('share_title'),
    builder: (_) => ShareTargetPicker(payload: payload),
  );
}

/// The conversations to send [payload] to, with a search filter. Pops the chosen [ChatRow].
class ShareTargetPicker extends StatefulWidget {
  const ShareTargetPicker({super.key, required this.payload});
  final SharedPayload payload;

  @override
  State<ShareTargetPicker> createState() => _ShareTargetPickerState();
}

class _ShareTargetPickerState extends State<ShareTargetPicker> {
  final _query = TextEditingController();

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  String _summary(String lang) {
    final text = widget.payload.text?.trim() ?? '';
    if (text.isNotEmpty) return plainLine(text, max: 120);
    final names = widget.payload.files.map((f) => f.name).toList();
    final separator = listSeparator(lang);
    return names.length > 3
        ? '${names.take(3).join(separator)}…'
        : names.join(separator);
  }

  @override
  Widget build(BuildContext context) {
    registerChatsStrings();
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final shell = context.select((AppState s) => s.shell);
    final all = chatRows(shell.orderedAgents, shell.groups.values, shell.inbox);
    // The list's order, the archived chats after the others.
    final rows = [...filterRows(all, 'all'), ...archivedRows(all)];
    String sub(ChatRow row) =>
        row.agent != null ? agentRole(l10n, row.agent!) : row.subtitle;
    final q = foldSearch(_query.text);
    final shown = rows
        .where(
          (r) => q.isEmpty || foldSearch('${r.name} ${sub(r)}').contains(q),
        )
        .toList();
    final summary = _summary(l10n.lang);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (summary.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text(
              summary,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: ln.text.caption.copyWith(color: c.fgMuted),
            ),
          ),
        SearchPill(
          controller: _query,
          hint: l10n.t('sh_searchAgentsGroups'),
          height: 40,
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 8),
        Flexible(
          child: !shell.loaded && rows.isEmpty && shell.lastError != null
              ? ErrorState(
                  title: l10n.errorText(shell.lastError),
                  retryLabel: l10n.t('sh_retry'),
                  onRetry: () =>
                      context.dispatch(RefreshShellAction(silent: false)),
                )
              : !shell.loaded && rows.isEmpty
              ? SkeletonRows(
                  count: 4,
                  // The sheet's own padding sets the row edge, as for the loaded rows.
                  inset: 0,
                  animate:
                      !(MediaQuery.maybeDisableAnimationsOf(context) ?? false),
                  semanticLabel: context.t('sh_loading'),
                )
              : shown.isEmpty
              ? Padding(
                  padding: const EdgeInsets.all(20),
                  child: Text(
                    l10n.t('sh_noResults'),
                    textAlign: TextAlign.center,
                    style: ln.text.caption.copyWith(color: c.fgMuted),
                  ),
                )
              : ListView(
                  shrinkWrap: true,
                  padding: EdgeInsets.zero,
                  children: [
                    for (final row in shown)
                      PickRow(
                        key: ValueKey('share-${row.key}'),
                        avatar: ChatRowAvatar(
                          row: row,
                          agents: shell.agents,
                          size: 40,
                        ),
                        title: row.name,
                        subtitle: sub(row),
                        // The sheet pads its content: the rows share its edge.
                        inset: 0,
                        onTap: () => Navigator.of(context).pop(row),
                      ),
                  ],
                ),
        ),
      ],
    );
  }
}
