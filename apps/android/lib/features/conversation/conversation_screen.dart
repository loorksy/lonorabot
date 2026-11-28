// The conversation (Lonora apps/mobile/app/thread.tsx): header with the avatar + name capsule, the
// transcript (newest at the bottom, older pages on scroll up, `around` landing with a flash), live
// reply previews from the fenced stream, run rows, questions, cards of the cards feature, the
// outbox, the run banner and the composer above the floating tab bar (on the keyboard while it is
// open).
import 'dart:async';
import 'dart:math' as math;

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';
import 'package:scrollview_observer/scrollview_observer.dart';
import 'package:shimmer/shimmer.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/deep_links.dart';
import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/thread_actions.dart';
import '../../state/app_state.dart';
import '../../state/realtime.dart';
import '../../state/reply_stream.dart';
import '../cards/owner_action_card.dart' show TimelineCardJumpNotification;
import '../cards/thread_cards.dart';
import '../rich/rich_content_view.dart';
import '../rich/rich_parts.dart' show CallPart, validateRichContent;
import '../voice/voice_api.dart';
import 'conversation_actions.dart';
import 'conversation_composer.dart';
import 'conversation_header.dart';
import 'conversation_strings.dart';
import 'conversation_timeline.dart';
import 'message_menu.dart';
import 'message_widgets.dart';
import 'question_card.dart';
import 'run_rows.dart';

/// The jump button's touch target reaches this far beyond its disc.
const double _jumpTouchMargin = (LnSize.minTouch - LnSize.jumpButton) / 2;

/// The transcript's fade into the canvas above the composer.
const double _bottomFade = 18;

class ConversationScreen extends StatefulWidget {
  const ConversationScreen({
    super.key,
    required this.threadId,
    this.around,
    this.home = false,
  });
  final String threadId;

  /// Land on this message seq (search hit, notification) and flash it.
  final int? around;

  /// The Chats tab's last-conversation home: the header's start circle opens the chat drawer.
  final bool home;

  @override
  State<ConversationScreen> createState() => _ConversationScreenState();
}

/// Everything the screen reads from the store, identity-compared. A streamed chunk changes
/// only the stream's text, which the live preview row reads itself ([_LivePreview]): the
/// screen rebuilds when the transcript's shape changes ([_streamShape]), not per chunk.
typedef _View = ({
  Thread? model,
  List<Message> messages,
  Map<String, Run> runs,
  Map<String, Object?> side,
  String streams,
  bool loaded,
  bool loading,
  bool loadingOlder,
  String? error,
  int? focusSeq,
  List<OutgoingMessage> outbox,
  Map<String, Agent> agents,
  Map<String, Group> groups,
  InboxEntry? entry,
  StreamStatus connection,
  ChatPrefs chatPrefs,
  bool shellLoaded,
  bool signedIn,
});

/// What of the live streams decides the transcript's rows: phase, whether there is something
/// to draw, the committed message and the input (never the growing text).
String _streamShape(Map<String, LiveReplyStream> streams) {
  if (streams.isEmpty) return '';
  final b = StringBuffer();
  for (final s in streams.values) {
    b
      ..write(s.runId)
      ..write(':')
      ..write(s.phase)
      ..write(streamHasContent(s) ? '+' : '-')
      ..write(s.messageId ?? '')
      ..write(':')
      ..write(s.inputSeq ?? '')
      ..write(';');
  }
  return b.toString();
}

class _ConversationScreenState extends State<ConversationScreen>
    with WidgetsBindingObserver {
  /// The conversations on screen, oldest first: the open thread (no unread bump, no
  /// notification) is the newest one's.
  static final List<_ConversationScreenState> _shown = [];

  final _scroll = ScrollController();
  late final _observer = ListObserverController(controller: _scroll);
  final _composer = GlobalKey<ConversationComposerState>();

  /// Each message's bubble (the long-press menu lifts it from its place), by timeline key.
  final Map<String, GlobalKey> _bubbleKeys = {};
  GlobalKey _bubbleKey(String key) =>
      _bubbleKeys.putIfAbsent(key, () => GlobalKey(debugLabel: key));
  Store<AppState>? _store;
  StreamSubscription<LonoraEvent>? _sub;

  /// This conversation's recent run and tool events, for the activity line and the avatar.
  final _events = ValueNotifier<List<Map<String, Object?>>>(const []);
  Timer? _sideTimer;
  Timer? _filesTimer;
  Timer? _flashTimer;
  Timer? _backTimer;

  /// The list rests on the latest message (hysteresis 120/64 dp as on mobile).
  late bool _following = widget.around == null;
  int _seenSeq = 0;
  int _markedSeq = 0;
  int? _jumpedAround;
  String? _flashKey;

  /// On screen: not in an offstage tab (indexedStack) nor under an opaque page.
  bool? _visible;

  /// The rows of the last build (jump targets).
  List<TimelineRow> _rows = const [];
  Object? _memoKey;
  List<TimelineItem> _memoItems = const [];
  StreamStatus? _lastConnection;
  bool _backOnline = false;
  bool _foreground = true;

  /// Older page: one request at a time; a failure waits for the owner's Retry (or the
  /// connection's return) instead of repeating on every scroll tick.
  bool _olderPending = false;
  bool _olderFailed = false;

  /// Run controls on their way (their buttons wait), and Retry-After answers.
  final Set<String> _busyRuns = {};
  final Map<String, DateTime> _retryAt = {};
  bool _stopping = false;

  String get _threadId => widget.threadId;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _scroll.addListener(_onScroll);
    try {
      _sub = realtime.events.listen(_onEvent);
    } catch (_) {
      // No live feed (previews, tests): snapshots still load.
    }
    // The drawer home stays open under the share picker: a share addressed to it lands here.
    pendingShare.addListener(_consumeShare);
    WidgetsBinding.instance.addPostFrameCallback((_) => _open());
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // ignore: invalid_use_of_internal_member
    _store ??= StoreProvider.backdoorInheritedWidget<AppState>(context);
    // The home shell keeps other tabs' pages alive offstage with tickers off, and a page
    // pushed over the conversation turns them off once it covers it.
    final visible = TickerMode.valuesOf(context).enabled;
    final before = _visible;
    _visible = visible;
    if (before != null && before != visible) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || _visible != visible) return;
        visible ? _show() : _hide();
      });
    }
  }

  @override
  void didUpdateWidget(ConversationScreen old) {
    super.didUpdateWidget(old);
    if (old.around == widget.around) return;
    _jumpedAround = null;
    final around = widget.around;
    if (around != null) {
      _following = false;
    } else {
      // The same conversation opened without a landing: back to the latest messages.
      _following = true;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (around != null) {
        _load();
      } else {
        if (_store?.state.threads[_threadId]?.focusSeq != null && _signedIn) {
          _dispatch(LoadNewestAction(_threadId));
        }
        if (_scroll.hasClients) _scroll.jumpTo(0);
      }
    });
  }

  @override
  void dispose() {
    pendingShare.removeListener(_consumeShare);
    WidgetsBinding.instance.removeObserver(this);
    _sub?.cancel();
    _sideTimer?.cancel();
    _filesTimer?.cancel();
    _flashTimer?.cancel();
    _backTimer?.cancel();
    _hide();
    _events.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
  }

  bool get _signedIn => _store?.state.session.signedIn ?? false;

  void _dispatch(ReduxAction<AppState> action) => _store?.dispatch(action);

  void _open() {
    if (!mounted) return;
    if (_visible ?? true) _show();
    _dispatch(RestoreThreadCacheAction(_threadId));
    _load();
    _consumeShare();
  }

  /// This conversation is on screen: it is the open thread, and what arrived is read.
  void _show() {
    _shown
      ..remove(this)
      ..add(this);
    _setOpenThread(_threadId);
    if (mounted) setState(() {});
  }

  /// Off screen (another tab, a page over it, closed): the open thread is the conversation
  /// still on screen, if any.
  void _hide() {
    if (!_shown.remove(this)) return;
    _setOpenThread(_shown.isEmpty ? null : _shown.last._threadId);
  }

  void _setOpenThread(String? id) {
    final store = _store;
    if (store != null && store.state.openThreadId != id) {
      store.dispatch(SetOpenThreadAction(id));
    }
  }

  void _load() {
    if (!_signedIn) return;
    _dispatch(LoadThreadAction(_threadId, around: widget.around));
    _dispatch(LoadThreadSideAction(_threadId));
    _dispatch(LoadCollaborationAction(_threadId));
    _dispatch(LoadThreadArtifactsAction(_threadId));
  }

  /// Content shared into Lonora joins the composer of the conversation the share picker
  /// addressed it to: when the conversation opens, or at once when it is already open (the
  /// last-conversation home stays open under the picker). A share not addressed yet goes to the
  /// picker first (deep_links closes a pushed conversation), never to another conversation.
  void _consumeShare() {
    if (!mounted) return;
    final share = pendingShare.value;
    final composer = _composer.currentState;
    if (share == null || composer == null) return;
    if (share.targetThreadId != _threadId) return;
    final text = share.text;
    if (text != null && text.isNotEmpty) composer.addText(text);
    if (share.files.isNotEmpty) composer.addSharedFiles(share.files);
    pendingShare.value = null;
  }

  void _onEvent(LonoraEvent e) {
    if (e.threadId != _threadId || !mounted) return;
    final kind = e.kind;
    if (kind.startsWith('run.') || kind.startsWith('tool.')) {
      if (kind != 'run.delta') {
        final events = [..._events.value, eventJson(e)];
        _events.value = events.length > 250
            ? events.sublist(events.length - 250)
            : events;
      }
    }
    if (e.isStreamChunk ||
        kind == 'run.delta' ||
        kind == 'message.reaction_updated' ||
        kind == 'thread.read' ||
        kind == 'thread.prefs_updated') {
      return;
    }
    // Cards follow their records: owner actions, approvals, receipts, peer exchanges…
    _sideTimer?.cancel();
    _sideTimer = Timer(const Duration(milliseconds: 400), () {
      if (mounted && _signedIn) {
        _dispatch(LoadThreadSideAction(_threadId));
        _dispatch(LoadCollaborationAction(_threadId));
      }
    });
    final files =
        kind == 'artifacts.updated' ||
        (kind == 'message.created' &&
            asStringList(e.payload['attachment_ids']).isNotEmpty);
    if (files) {
      _filesTimer?.cancel();
      _filesTimer = Timer(const Duration(milliseconds: 400), () {
        if (mounted && _signedIn) {
          _dispatch(LoadThreadArtifactsAction(_threadId));
        }
      });
    }
  }

  void _onScroll() {
    if (!_scroll.hasClients) return;
    final p = _scroll.position;
    final near = p.pixels <= (_following ? 120 : 64);
    if (near != _following) setState(() => _following = near);
    if (p.maxScrollExtent > 0 && p.pixels >= p.maxScrollExtent - 600) {
      unawaited(_loadOlder());
    }
  }

  Future<void> _loadOlder() async {
    final store = _store;
    final t = store?.state.threads[_threadId];
    if (store == null ||
        t == null ||
        _olderPending ||
        _olderFailed ||
        !_signedIn ||
        !t.hasOlder ||
        t.loadingOlder ||
        t.messages.isEmpty) {
      return;
    }
    _olderPending = true;
    final action = LoadOlderAction(_threadId);
    await store.dispatchAndWait(action);
    _olderPending = false;
    if (!mounted) return;
    // Only a code means a page failed: null is also «nothing was asked» (the checks above).
    final failed = action.errorCode != null;
    if (failed != _olderFailed) setState(() => _olderFailed = failed);
  }

  void _retryOlder() {
    setState(() => _olderFailed = false);
    unawaited(_loadOlder());
  }

  void _toBottom({bool animate = true}) {
    setState(() => _following = true);
    if (!_scroll.hasClients) return;
    if (animate) {
      _scroll.animateTo(0, duration: LnMotion.slow, curve: LnMotion.standard);
    } else {
      _scroll.jumpTo(0);
    }
  }

  void _jumpToLatest() {
    final t = _store?.state.threads[_threadId];
    if (t?.focusSeq != null && _signedIn) {
      _dispatch(LoadNewestAction(_threadId));
    }
    _toBottom();
  }

  void _flash(String key) {
    _flashTimer?.cancel();
    setState(() => _flashKey = key);
    _flashTimer = Timer(const Duration(milliseconds: 1700), () {
      if (mounted) setState(() => _flashKey = null);
    });
  }

  /// Rests the list on a row (centred) and marks it for a moment.
  void _jumpTo(List<TimelineRow> rows, String key) {
    final index = rows.indexWhere((r) => r.item.key == key);
    if (index < 0) {
      LnToast.show(context, context.t('messageGone'), kind: LnToastKind.notice);
      return;
    }
    setState(() => _following = false);
    _flash(key);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scroll.hasClients) return;
      _observer.jumpTo(index: rows.length - 1 - index, alignment: 0.5);
    });
  }

  void _toast(String? code) {
    if (code == null || !mounted) return;
    LnToast.show(
      context,
      context.l10n.errorText(code),
      kind: LnToastKind.error,
    );
  }

  /// Cancel, Resume or Retry of one run; its buttons wait while the request runs, and a
  /// Retry the provider refuses for now waits for its Retry-After.
  Future<void> _runControl(Run run, String control) async {
    if (_busyRuns.contains(run.id)) return;
    setState(() => _busyRuns.add(run.id));
    final action = ConversationRunControlAction(run.id, control);
    await _store?.dispatchAndWait(action);
    if (!mounted) return;
    setState(() {
      _busyRuns.remove(run.id);
      final wait = action.retryAfter;
      if (action.errorCode == 'run_retry_too_early' && wait != null) {
        _retryAt[run.id] = DateTime.now().add(wait);
      }
    });
    _toast(action.errorCode);
  }

  Future<void> _stop() async {
    final t = _store?.state.threads[_threadId];
    if (t == null || _stopping) return;
    final targets = stopTargets(t.runs.values, _threadId);
    if (targets.isEmpty) return;
    _stopping = true;
    final action = StopConversationRunsAction([for (final r in targets) r.id]);
    await _store?.dispatchAndWait(action);
    _stopping = false;
    _toast(action.errorCode);
  }

  void _answer(InputRequest request, InputChoice choice) {
    _dispatch(
      SendMessageAction(_threadId, {
        'content': choice.label,
        'reply_to': request.messageId,
        'input_answer': {
          'run_id': request.runId,
          'question_id': request.id,
          'choice_id': choice.id,
        },
        'attachment_ids': <String>[],
      }),
    );
    _toBottom();
  }

  Future<void> _react(Message m, String? emoji) async {
    final action = ConversationReactionAction(
      threadId: _threadId,
      messageId: m.id,
      emoji: emoji,
    );
    await _store?.dispatchAndWait(action);
    _toast(action.errorCode);
  }

  String _author(Message m, Map<String, Agent> agents) {
    final l10n = context.l10n;
    if (m.fromOwner) return l10n.t('you');
    return agents[m.agentId]?.name ?? l10n.t('system');
  }

  Future<void> _messageMenu(
    Message m, {
    required Widget target,
    required Map<String, Agent> agents,
    required String? taskAgentId,
  }) async {
    final l10n = context.l10n;
    final text = m.content.trim();
    final at = m.createdAt;
    await showMessageMenu(
      context,
      target: target,
      targetKey: _bubbleKey('m:${m.id}'),
      header: at == null ? null : l10n.timeSeparator(at),
      ownReaction: ownerReaction(m.reactions),
      onReact: (emoji) => _react(m, emoji),
      actions: [
        LnMenuAction(
          icon: LnIcons.reply,
          label: l10n.t('reply'),
          onSelected: () =>
              _composer.currentState?.reply(m, _author(m, agents)),
        ),
        if (text.isNotEmpty)
          LnMenuAction(
            icon: FIcons.copy,
            label: l10n.t('copyText'),
            onSelected: () => _copy(m.content),
          ),
        if (text.isNotEmpty)
          LnMenuAction(
            icon: FIcons.textSelect,
            label: l10n.t('conv_selectText'),
            onSelected: () =>
                showSelectTextSheet(context, message: m, threadId: _threadId),
          ),
        if (canEditAndResend(m))
          LnMenuAction(
            icon: FIcons.pencil,
            label: l10n.t('editAndResend'),
            onSelected: () => _composer.currentState?.edit(m),
          ),
        if (canTurnIntoTask(m) && taskAgentId != null)
          LnMenuAction(
            icon: LnIcons.listTodo,
            label: l10n.t('turnIntoTask'),
            onSelected: () => _task(m, taskAgentId),
          ),
      ],
    );
  }

  Future<void> _copy(String text) async {
    final l10n = context.l10n;
    try {
      await Clipboard.setData(ClipboardData(text: text));
      if (mounted) {
        LnToast.show(context, l10n.t('copied'), kind: LnToastKind.positive);
      }
    } on PlatformException {
      if (mounted) {
        LnToast.show(context, l10n.t('copyFailed'), kind: LnToastKind.error);
      }
    }
  }

  Future<void> _task(Message m, String agentId) async {
    final action = CreateTaskFromMessageAction(
      threadId: _threadId,
      agentId: agentId,
      message: m,
    );
    await _store?.dispatchAndWait(action);
    if (!mounted) return;
    if (action.errorCode != null) {
      _toast(action.errorCode);
    } else {
      LnToast.show(
        context,
        context.t('taskCreated'),
        kind: LnToastKind.positive,
      );
    }
  }

  Future<void> _failedMenu(OutgoingMessage o, Widget target) async {
    final l10n = context.l10n;
    await showMessageMenu(
      context,
      target: target,
      targetKey: _bubbleKey('o:${o.nonce}'),
      header: l10n.t('messageNotSent'),
      actions: [
        LnMenuAction(
          icon: FIcons.rotateCcw,
          label: l10n.t('retry'),
          onSelected: () => _dispatch(RetryOutgoingAction(o.nonce)),
        ),
        LnMenuAction(
          icon: FIcons.trash2,
          label: l10n.t('deleteMessage'),
          destructive: true,
          onSelected: () => _discard(o),
        ),
      ],
    );
  }

  Future<void> _discard(OutgoingMessage o) async {
    final l10n = context.l10n;
    final ok = await showLnConfirm(
      context,
      title: l10n.t('conv_discardUnsentQ'),
      message: l10n.t('conv_discardUnsentBody'),
      confirmLabel: l10n.t('deleteMessage'),
      cancelLabel: l10n.t('sh_cancel'),
      destructive: true,
    );
    if (ok) _dispatch(DiscardOutgoingAction(o.nonce));
  }

  /// The ordered transcript, rebuilt only when its inputs change (not per streamed chunk).
  List<TimelineItem> _timeline(
    BuildContext context,
    ThreadState t,
    _View view,
    List<OutgoingMessage> outbox,
  ) {
    final key = (
      view.messages,
      view.runs,
      view.side,
      view.streams,
      view.outbox,
    );
    if (key != _memoKey) {
      _memoKey = key;
      _memoItems = buildTimeline(
        thread: t,
        outbox: outbox,
        cards: threadCards(context, t),
      );
    }
    return _memoItems;
  }

  @override
  Widget build(BuildContext context) {
    registerConversationStrings(context.l10n);
    final _View view = context.select((AppState s) {
      final t = s.threads[_threadId];
      return (
        model: t?.thread,
        messages: t?.messages ?? const <Message>[],
        runs: t?.runs ?? const <String, Run>{},
        side: t?.side ?? const <String, Object?>{},
        streams: _streamShape(t?.streams ?? const {}),
        loaded: t?.loaded ?? false,
        loading: t?.loading ?? false,
        loadingOlder: t?.loadingOlder ?? false,
        error: t?.error,
        focusSeq: t?.focusSeq,
        outbox: s.outbox,
        agents: s.shell.agents,
        groups: s.shell.groups,
        entry: s.shell.entryFor(_threadId),
        connection: s.connection,
        chatPrefs: s.prefs.chatPrefs,
        shellLoaded: s.shell.loaded,
        signedIn: s.session.signedIn,
      );
    });
    _watchConnection(view.connection);

    final ln = context.ln;
    final l10n = context.l10n;
    // The selection above decides when to rebuild; the rows read the store's current thread.
    final t =
        _store?.state.threads[_threadId] ?? ThreadState(threadId: _threadId);
    final model = view.model;
    final groupId = model?.groupId ?? view.entry?.groupId;
    final agentId = groupId == null
        ? (model?.agentId ?? view.entry?.agentId)
        : null;
    final group = groupId == null ? null : view.groups[groupId];
    final agent = agentId == null ? null : view.agents[agentId];
    final members = [
      for (final id in group?.memberIds ?? const <String>[]) ?view.agents[id],
    ];
    final title =
        agent?.name ??
        group?.name ??
        (model?.title.isNotEmpty == true ? model!.title : l10n.t('inbox'));
    final threadRuns = view.runs.values
        .where((r) => r.threadId.isEmpty || r.threadId == _threadId)
        .toList();
    final running = threadRuns.any((r) => r.isActive);
    final unavailable = view.error == 'thread_not_found';
    final agentGone =
        agentId != null &&
        agent == null &&
        view.shellLoaded &&
        view.agents.isNotEmpty;

    final outbox = [
      for (final o in view.outbox)
        if (o.threadId == _threadId) o,
    ];
    final items = _timeline(context, t, view, outbox);
    final questions = threadQuestions(t.runs.values, _threadId);
    bool startsWithBubble(TimelineItem item) =>
        item is MessageItem && _drawsBubble(context, item.message, questions);
    final rows = presentTimeline(
      items,
      group: groupId != null,
      sameSenderGap: LnSpace.sameSenderGap,
      senderChangeGap: LnSpace.senderChangeGap,
      bubbleRunGap: LnSpace.bubbleRunGap,
      startsWithBubble: startsWithBubble,
      // Files and reactions under a bubble keep the next one at the usual distance.
      endsWithBubble: (item) =>
          startsWithBubble(item) &&
          (item as MessageItem).message.attachmentIds.isEmpty &&
          item.message.reactions.isEmpty,
    );
    _rows = rows;
    final banner = bannerRun(view.runs.values, {
      for (final item in items)
        if (item is PreviewItem)
          item.run.id
        else if (item is RunStatusItem)
          item.run.id,
    });
    final newestSeq = view.messages.isEmpty ? 0 : view.messages.last.seq;
    // Messages count as new (the jump button's badge) only when they arrive after the owner
    // first saw this conversation or while the list rests away from the latest one.
    if (_following || (_seenSeq == 0 && view.loaded)) {
      _seenSeq = math.max(_seenSeq, newestSeq);
    }
    final unread = view.messages
        .where((m) => m.seq > _seenSeq && !m.fromOwner)
        .length;
    // The whole spoken label, joined in the owner's language («، » in Arabic).
    final jumpLabel = unread > 0
        ? [
            l10n.t('jumpLatest'),
            l10n.t('sh_unreadN', const [], {'count': unread}),
          ].join(listSeparator(l10n.lang))
        : l10n.t('jumpLatest');
    _afterBuild(view, newestSeq);

    final keyboard = MediaQuery.viewInsetsOf(context).bottom;
    final bottom = keyboard > 0
        ? keyboard + LnSpace.sm
        : FloatingTabBar.occupiedHeight(context) + LnSpace.composerToBar;
    final strip = _strip(view.connection);

    final body = unavailable
        ? _unavailable(context)
        : !view.loaded && rows.isEmpty
        ? (view.error != null
              ? ErrorState(
                  title: l10n.errorText(view.error),
                  retryLabel: l10n.t('retry'),
                  onRetry: _load,
                )
              : const _ConversationSkeleton())
        : rows.isEmpty
        ? _empty(context, agent, group, members)
        : _list(context, view, t, rows, agent, group, members);

    return ColoredBox(
      color: ln.colors.bg,
      child: Column(
        children: [
          NetworkStrip(
            status: strip,
            label: switch (strip) {
              NetworkStripStatus.offline => l10n.t('sh_netOff'),
              NetworkStripStatus.reconnected => l10n.t('sh_netBack'),
              _ => l10n.t('reconnecting'),
            },
          ),
          Expanded(
            child: MediaQuery.removePadding(
              context: context,
              removeTop: strip != NetworkStripStatus.hidden,
              child: Builder(
                builder: (context) => Stack(
                  children: [
                    Positioned.fill(child: body),
                    Positioned(
                      left: 0,
                      right: 0,
                      top: 0,
                      child: ValueListenableBuilder(
                        valueListenable: _events,
                        builder: (context, events, _) => ConversationHeader(
                          threadId: _threadId,
                          title: title,
                          agent: agent,
                          group: group,
                          members: members,
                          avatarState: _avatarState(
                            agent,
                            threadRuns,
                            t,
                            view.connection,
                            events,
                          ),
                          callable:
                              agent != null && !agent.paused && !unavailable,
                          home: widget.home,
                        ),
                      ),
                    ),
                    // The transcript fades into the canvas over the 18 dp above the composer.
                    if (!unavailable)
                      Positioned(
                        left: 0,
                        right: 0,
                        bottom: 0,
                        height: _bottomFade,
                        child: IgnorePointer(
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: [
                                  ln.colors.bg.withValues(alpha: 0),
                                  ln.colors.bg.withValues(alpha: 0.7),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    // At the end side, 16 dp from the edge and 20 dp above the composer (the
                    // button's 48 dp touch target reaches 6 dp beyond its 36 dp disc).
                    PositionedDirectional(
                      end: LnSpace.pageGutter - _jumpTouchMargin,
                      bottom: 20 - LnSpace.xs - _jumpTouchMargin,
                      child: JumpToLatestButton(
                        visible: !_following && rows.isNotEmpty,
                        unreadCount: unread,
                        semanticLabel: jumpLabel,
                        onTap: _jumpToLatest,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          if (!unavailable)
            Padding(
              padding: EdgeInsetsDirectional.fromSTEB(
                LnSpace.chromeGutter,
                LnSpace.xs,
                LnSpace.chromeGutter,
                bottom,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (banner != null) _runBanner(banner, view),
                  if (agentGone)
                    _Notice(text: l10n.t('conv_agentUnavailable'))
                  else if (agent != null && agent.paused)
                    _Notice(
                      text: l10n.t('agent_paused'),
                      action: RowTextButton(
                        label: l10n.t('agentSettings'),
                        onTap: () =>
                            context.push(Routes.agentSettings(agent.id)),
                      ),
                    ),
                  ConversationComposer(
                    key: _composer,
                    threadId: _threadId,
                    running: running,
                    webSearch: model?.webSearch ?? false,
                    enabled: !agentGone,
                    agentName: group == null ? agent?.name : null,
                    suggestion: view.chatPrefs.assist
                        ? _suggestion(t, items)
                        : null,
                    onSent: () => _toBottom(animate: false),
                    onStop: _stop,
                    agent: agent,
                    group: group,
                    members: members,
                    agents: _store?.state.shell.orderedAgents ?? const [],
                    collaborationSessionId: collaborationSessionOf(t),
                    assist: view.chatPrefs.assist,
                    callable: agent != null && !agent.paused && !unavailable,
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  /// The agent's own suggested reply under its last answer: a conversational answer (no
  /// generated interface, no question) that nothing came after (apps/mobile thread.tsx).
  String? _suggestion(ThreadState t, List<TimelineItem> items) {
    if (items.isEmpty || items.last is! MessageItem) return null;
    final last = (items.last as MessageItem).message;
    final suggested = last.suggestedReply;
    if (!last.fromAgent || suggested == null || suggested.isEmpty) return null;
    if (RichContentView.drawsOwnBubbles(last.richContent)) return null;
    if (threadQuestions(t.runs.values, _threadId).containsKey(last.id)) {
      return null;
    }
    final mine = t.messages.lastWhere((m) => m.fromOwner, orElse: () => last);
    if (mine.fromOwner && mine.content.trim() == suggested) return null;
    return suggested;
  }

  LonoraAvatarState _avatarState(
    Agent? agent,
    List<Run> runs,
    ThreadState t,
    StreamStatus connection,
    List<Map<String, Object?>> events,
  ) {
    final active = runs.where((r) => r.isActive).toList()
      ..sort(
        (a, b) =>
            (b.createdAt ?? DateTime(0)).compareTo(a.createdAt ?? DateTime(0)),
      );
    if (active.isNotEmpty) {
      if (connection != StreamStatus.connected &&
          connection != StreamStatus.idle) {
        return LonoraAvatarState.connecting;
      }
      final run = active.first;
      final phase = turnActivity(
        runJsonFor(run, t.streams[run.id]),
        events,
      ).phase;
      return activityPhaseAvatar[phase] ?? LonoraAvatarState.working;
    }
    if (agent?.paused ?? false) return LonoraAvatarState.sleeping;
    return LonoraAvatarState.idle;
  }

  void _watchConnection(StreamStatus now) {
    final before = _lastConnection;
    _lastConnection = now;
    if (before == null || before == now) return;
    final wasDown =
        before == StreamStatus.offline || before == StreamStatus.reconnecting;
    if (wasDown && now == StreamStatus.connected) {
      _backOnline = true;
      // The network is back: an older page that failed may load again.
      _olderFailed = false;
      _backTimer?.cancel();
      _backTimer = Timer(const Duration(seconds: 2), () {
        if (mounted) setState(() => _backOnline = false);
      });
    } else if (now != StreamStatus.connected) {
      _backOnline = false;
    }
  }

  NetworkStripStatus _strip(StreamStatus s) => switch (s) {
    StreamStatus.offline => NetworkStripStatus.offline,
    StreamStatus.reconnecting => NetworkStripStatus.connecting,
    StreamStatus.connected when _backOnline => NetworkStripStatus.reconnected,
    _ => NetworkStripStatus.hidden,
  };

  /// Read marks (only while the conversation is on screen and the app in front), the
  /// `around` landing: work that needs the laid-out list.
  void _afterBuild(_View view, int newestSeq) {
    final around = widget.around;
    // Land once the page around the target has loaded (LoadThreadAction sets focusSeq).
    final land =
        around != null &&
        _jumpedAround != around &&
        view.focusSeq == around &&
        view.loaded &&
        !view.loading;
    final mark =
        view.signedIn &&
        _following &&
        _foreground &&
        (_visible ?? true) &&
        view.loaded &&
        newestSeq > _markedSeq;
    if (!land && !mark) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final latest = _store?.state.threads[_threadId];
      if (land &&
          _jumpedAround != around &&
          latest != null &&
          !latest.loading &&
          latest.focusSeq == around) {
        _jumpedAround = around;
        final key = _rows
            .map((r) => r.item)
            .whereType<MessageItem>()
            .where((m) => m.message.seq == around)
            .firstOrNull
            ?.key;
        if (key == null) {
          LnToast.show(
            context,
            context.t('messageGone'),
            kind: LnToastKind.notice,
          );
        } else {
          _jumpTo(_rows, key);
        }
      }
      if (mark && (_visible ?? true) && newestSeq > _markedSeq) {
        _markedSeq = newestSeq;
        _dispatch(MarkReadAction(_threadId, newestSeq));
      }
    });
  }

  Widget _list(
    BuildContext context,
    _View view,
    ThreadState t,
    List<TimelineRow> rows,
    Agent? agent,
    Group? group,
    List<Agent> members,
  ) {
    final l10n = context.l10n;
    final byId = {for (final m in t.messages) m.id: m};
    final questions = threadQuestions(t.runs.values, _threadId);
    final artifacts = {
      for (final a in asJsonList(t.side[artifactsSideKey])) asStr(a['id']): a,
    };
    final retry = retryableFailure(
      t.runs.values.where((r) => r.threadId == _threadId),
      DateTime.now(),
    );
    final taskAgentId =
        agent?.id ?? group?.leadAgentId ?? members.firstOrNull?.id;
    final answering = <String, String>{
      for (final o in view.outbox)
        if (o.threadId == _threadId && o.delivery != Delivery.failed)
          if (asJson(o.body['input_answer']) case final a when a.isNotEmpty)
            asStr(a['question_id']): asStr(a['choice_id']),
    };
    final callBack = agent != null && group == null && !agent.paused
        ? () =>
              VoiceCalls.start(context, agentId: agent.id, threadId: _threadId)
        : null;
    final older = view.loadingOlder || _olderFailed;

    Widget build(TimelineRow row) {
      final item = row.item;
      final callLog = item is MessageItem && _isCallLog(item.message);
      // A preview without a sender line spaces itself: its activity line can be tappable.
      final selfSpaced = item is PreviewItem && !row.showSender;
      Widget child = switch (item) {
        MessageItem(:final message) => _messageRow(
          message,
          row: row,
          callLog: callLog,
          byId: byId,
          view: view,
          questions: questions,
          answering: answering,
          artifacts: artifacts,
          taskAgentId: taskAgentId,
          callBack: callBack,
        ),
        OutgoingItem(:final outgoing) => () {
          OutgoingTile tile({VoidCallback? onLongPress}) => OutgoingTile(
            outgoing: outgoing,
            quoted: byId[outgoing.replyTo],
            quotedAuthor: byId[outgoing.replyTo] == null
                ? null
                : _author(byId[outgoing.replyTo]!, view.agents),
            artifacts: artifacts,
            onRetry: () => _dispatch(RetryOutgoingAction(outgoing.nonce)),
            onLongPress: onLongPress,
          );
          return Align(
            alignment: AlignmentDirectional.centerEnd,
            child: KeyedSubtree(
              key: _bubbleKey(item.key),
              child: tile(
                onLongPress: outgoing.delivery == Delivery.failed
                    ? () => _failedMenu(outgoing, tile())
                    : null,
              ),
            ),
          );
        }(),
        PreviewItem(:final run) => _LivePreview(
          threadId: _threadId,
          runId: run.id,
          builder: (context, run, stream) => _preview(
            context,
            item,
            run,
            stream,
            view,
            gap: selfSpaced ? row.gap : 0,
          ),
        ),
        RunStatusItem(:final run) => RunEndRow(
          run: run,
          retryable: retry?.run.id == run.id,
          retryAt: retry?.run.id == run.id
              ? _later(retry?.until, _retryAt[run.id])
              : null,
          busy: _busyRuns.contains(run.id),
          onRetry: () => _runControl(run, 'retry'),
        ),
        CardItem(:final card) => Align(
          alignment: AlignmentDirectional.centerStart,
          child: Builder(builder: card.builder),
        ),
      };
      if (row.showSender) {
        final senderId = senderOf(item).substring('agent:'.length);
        child = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            SenderRow(agent: view.agents[senderId]),
            child,
          ],
        );
      }
      final flash = _flashKey == item.key;
      child = AnimatedContainer(
        duration: LnMotion.slow,
        decoration: BoxDecoration(
          color: flash ? context.ln.colors.jumpFlash : null,
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.card)),
        ),
        child: child,
      );
      // A tappable event row (a tool result, a call log that calls back) stands 48 dp tall around
      // its 38 dp content: the gap above gives those 5 dp back, so the visible gap stays 15.3 dp.
      // Below, no gap is left to trim.
      final tappableEvent = switch (item) {
        MessageItem(:final message) =>
          message.role == 'tool' || (callBack != null && callLog),
        _ => false,
      };
      return KeyedSubtree(
        key: ValueKey(item.key),
        child: Padding(
          padding: EdgeInsets.only(
            top: selfSpaced
                ? 0
                : tappableEvent
                ? math.max(0, row.gap - 5)
                : row.gap,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (row.separator != null)
                DateSeparator(
                  label: l10n.timeSeparator(row.separator!),
                  // The tappable row's own 5 dp band stands for the rest of the gap.
                  bottom: tappableEvent ? LnSpace.md - 5 : LnSpace.md,
                ),
              child,
            ],
          ),
        ),
      );
    }

    final count = rows.length + (older ? 1 : 0);
    // «Show the latest» on a replaced card asks for the card that replaced it.
    return NotificationListener<TimelineCardJumpNotification>(
      onNotification: (n) {
        _jumpTo(_rows, 'c:${n.key}');
        return true;
      },
      child: ListViewObserver(
        controller: _observer,
        child: RawScrollbar(
          controller: _scroll,
          thickness: 3,
          radius: const Radius.circular(1.5),
          thumbColor: context.ln.colors.fg.withValues(alpha: 0.45),
          minThumbLength: 36,
          fadeDuration: LnMotion.medium,
          timeToFade: const Duration(milliseconds: 900),
          padding: EdgeInsets.only(
            top: conversationHeaderExtent(context),
            bottom: LnSpace.md,
          ),
          child: ListView.builder(
            controller: _scroll,
            reverse: true,
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: EdgeInsets.only(
              top: conversationHeaderExtent(context),
              bottom: LnSpace.md,
              left: LnSpace.pageGutter,
              right: LnSpace.pageGutter,
            ),
            itemCount: count,
            findChildIndexCallback: (key) {
              if (key is! ValueKey<String>) return null;
              final i = rows.indexWhere((r) => r.item.key == key.value);
              return i < 0 ? null : rows.length - 1 - i;
            },
            itemBuilder: (context, index) {
              if (index >= rows.length) {
                return _olderFailed && !view.loadingOlder
                    ? _OlderFailedRow(onRetry: _retryOlder)
                    : const Padding(
                        padding: EdgeInsets.symmetric(vertical: LnSpace.md),
                        child: Center(child: LnSpinner(size: 18)),
                      );
              }
              return build(rows[rows.length - 1 - index]);
            },
          ),
        ),
      ),
    );
  }

  static DateTime? _later(DateTime? a, DateTime? b) {
    if (a == null) return b;
    if (b == null) return a;
    return a.isAfter(b) ? a : b;
  }

  static bool _isCallLog(Message m) =>
      m.role == 'system' &&
      (validateRichContent(m.richContent)?.any((p) => p is CallPart) ?? false);

  /// Whether [m] draws as a text bubble at its top (an owner or agent message that is not a
  /// generated interface, a question with choices or files alone): a bubble run joins it.
  static bool _drawsBubble(
    BuildContext context,
    Message m,
    Map<String, InputRequest> questions,
  ) {
    if (m.role != 'user' && m.role != 'assistant') return false;
    if ((questions[m.id]?.choices.isNotEmpty ?? false)) return false;
    if (m.fromOwner) {
      return !(m.attachmentIds.isNotEmpty &&
          m.parts.isEmpty &&
          isAttachPlaceholder(context, m.content));
    }
    return !RichContentView.drawsOwnBubbles(m.richContent);
  }

  Widget _messageRow(
    Message message, {
    required TimelineRow row,
    required bool callLog,
    required Map<String, Message> byId,
    required _View view,
    required Map<String, InputRequest> questions,
    required Map<String, String> answering,
    required Map<String, Json> artifacts,
    required String? taskAgentId,
    VoidCallback? callBack,
  }) {
    if (message.role == 'system') {
      // A voice call's log (server-written): the call row, a tap calls the agent back.
      if (callLog) {
        return RichContentView(
          threadId: _threadId,
          text: message.content,
          richContent: message.richContent,
          message: message,
          onCallBack: callBack,
        );
      }
      return SystemRow(text: message.content);
    }
    if (message.role == 'tool') return ToolResultRow(message: message);
    final question = questions[message.id];
    if (question != null && question.choices.isNotEmpty) {
      return Align(
        alignment: AlignmentDirectional.centerStart,
        child: QuestionCard(
          request: question,
          answering: answering[question.id],
          onAnswer: (choice) => _answer(question, choice),
        ),
      );
    }
    final quoted = byId[message.replyTo];
    final author = quoted == null ? null : _author(quoted, view.agents);
    // The same bubble, redrawn sharp over the blurred transcript while its menu is open.
    MessageTile tile({GlobalKey? bubbleKey, bool bubbleOnly = false}) =>
        MessageTile(
          message: message,
          threadId: _threadId,
          quoted: quoted,
          quotedAuthor: author,
          artifacts: artifacts,
          onCallBack: callBack,
          bubbleKey: bubbleKey,
          bubbleOnly: bubbleOnly,
          joinTop: row.joinTop,
          joinBottom: row.joinBottom,
          onLongPress: bubbleOnly
              ? null
              : () => _messageMenu(
                  message,
                  target: tile(bubbleOnly: true),
                  agents: view.agents,
                  taskAgentId: message.agentId ?? taskAgentId,
                ),
          onSwipeReply: bubbleOnly
              ? null
              : () => _composer.currentState?.reply(
                  message,
                  _author(message, view.agents),
                ),
          onQuoteTap: quoted == null || bubbleOnly
              ? null
              : () => _jumpTo(_rows, 'm:${quoted.id}'),
          onReactionsTap: () => showReactionsSheet(
            context,
            reactions: message.reactions,
            nameOf: (reactor) =>
                view.agents[reactor]?.name ?? context.l10n.t('system'),
            onRemoveOwn: () => _react(message, null),
          ),
        );
    return tile(bubbleKey: _bubbleKey('m:${message.id}'));
  }

  /// A reply being written: the live stream (replaced by the canonical message once it is
  /// committed), the typing bubble before any text, and the run's activity line when there is
  /// something to say beyond "writing" (tool steps, waiting, reconnecting, an end). [run] and
  /// [stream] are the store's current ones ([_LivePreview]). [gap] is the space above it.
  Widget _preview(
    BuildContext context,
    PreviewItem p,
    Run run,
    LiveReplyStream? stream,
    _View view, {
    required double gap,
  }) {
    final l10n = context.l10n;
    final waiting =
        run.status == 'waiting_input' || run.status == 'waiting_takeover';
    final reconnecting =
        run.isActive &&
        view.connection != StreamStatus.connected &&
        view.connection != StreamStatus.idle;
    final busy = _busyRuns.contains(run.id);
    final actions = <Widget>[
      if (run.status == 'waiting_takeover')
        RowTextButton(
          label: l10n.t('resume'),
          enabled: !busy,
          onTap: () => _runControl(run, 'resume'),
        ),
      if (waiting)
        RowTextButton(
          label: l10n.t('cancel'),
          enabled: !busy,
          onTap: () => _runControl(run, 'cancel'),
        ),
    ];
    Widget? reply;
    if (p.visible && stream != null) {
      final content = RichContentView(
        threadId: _threadId,
        text: stream.text,
        richContent: stream.richContent,
        streaming: stream.streaming,
      );
      reply = RichContentView.drawsOwnBubbles(stream.richContent)
          ? content
          : MessageBubble(sender: BubbleSender.agent, child: content);
    }
    return ValueListenableBuilder(
      valueListenable: _events,
      builder: (context, events, _) {
        final activity = turnActivity(runJsonFor(run, stream), events);
        const quiet = {'queued', 'preparing', 'thinking', 'writing'};
        final showLine =
            waiting ||
            reconnecting ||
            !quiet.contains(activity.phase) ||
            (view.chatPrefs.steps && activity.calls.isNotEmpty);
        // No words yet: the agent's avatar at work, saying the phase unless the line above
        // already does.
        final phaseLabel = l10n.t('activity_${activity.phase}');
        final typing = reply == null && run.isActive
            ? WorkingRow(
                agent: view.agents[run.agentId],
                agentId: run.agentId,
                state:
                    activityPhaseAvatar[activity.phase] ??
                    LonoraAvatarState.working,
                label: showLine ? null : phaseLabel,
                semanticLabel: phaseLabel,
              )
            : null;
        // A line with steps to open stands 48 dp around its 38 dp content, like the
        // transcript's tappable event rows: the gap above gives those 5 dp back.
        final tappableLine =
            showLine && view.chatPrefs.steps && activity.calls.isNotEmpty;
        return Padding(
          padding: EdgeInsets.only(
            top: tappableLine ? math.max(0, gap - 5) : gap,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (showLine)
                ActivityLine(
                  run: run,
                  stream: stream,
                  events: events,
                  connection: view.connection,
                  steps: view.chatPrefs.steps,
                  stepsOpen: view.chatPrefs.stepsOpen,
                  actions: actions,
                ),
              ?reply,
              ?typing,
            ],
          ),
        );
      },
    );
  }

  /// Lonora's run banner (apps/mobile thread.tsx) for a run the transcript does not draw: a
  /// background run waiting for the owner or a takeover, or a failure only the owner can act
  /// on. Composed from the inline event row and row buttons.
  Widget _runBanner(Run run, _View view) {
    final l10n = context.l10n;
    final c = context.ln.colors;
    final failed = run.status == 'failed';
    final waiting =
        run.status == 'waiting_input' || run.status == 'waiting_takeover';
    final plan = failed && planLimitReached(run.failure);
    final name = view.agents[run.agentId]?.name;
    final status = runStatusText(run.status, l10n.lang);
    final retry = retryableFailure(
      view.runs.values.where((r) => r.threadId == _threadId),
      DateTime.now(),
    );
    final retryAt = retry?.run.id == run.id
        ? _later(retry?.until, _retryAt[run.id])
        : null;
    final busy = _busyRuns.contains(run.id);
    return Padding(
      padding: const EdgeInsets.only(bottom: LnSpace.xxs),
      child: Semantics(
        liveRegion: true,
        child: Row(
          children: [
            Expanded(
              child: InlineEventRow(
                icon: failed
                    ? Icon(FIcons.circleAlert, color: c.error)
                    : Icon(FIcons.hourglass, color: c.pending),
                label: name == null ? status : '$name · $status',
                detail: plan
                    ? chatgptText(l10n.lang).planLimitTitle
                    : run.errorCode != null
                    ? l10n.errorText(run.errorCode)
                    : null,
                alignment: InlineEventAlignment.start,
                showChevron: false,
                maxLines: 2,
              ),
            ),
            if (plan)
              RowTextButton(
                label: chatgptText(l10n.lang).manageUsage,
                onTap: () => launchUrl(
                  Uri.parse(manageUsageUrl),
                  mode: LaunchMode.externalApplication,
                ),
              ),
            if (waiting)
              RowTextButton(
                label: l10n.t('cancel'),
                enabled: !busy,
                onTap: () => _runControl(run, 'cancel'),
              ),
            if (run.status == 'waiting_takeover')
              RowTextButton(
                label: l10n.t('resume'),
                enabled: !busy,
                onTap: () => _runControl(run, 'resume'),
              ),
            if (retry?.run.id == run.id)
              _RetryButton(
                retryAt: retryAt,
                enabled: !busy,
                onTap: () => _runControl(run, 'retry'),
              ),
          ],
        ),
      ),
    );
  }

  Widget _empty(
    BuildContext context,
    Agent? agent,
    Group? group,
    List<Agent> members,
  ) {
    final l10n = context.l10n;
    final a = agent;
    return Padding(
      padding: EdgeInsets.only(top: conversationHeaderExtent(context)),
      child: EmptyState(
        illustration: a != null
            ? LonoraAvatar(
                agentId: a.id,
                face: a.avatar,
                color: a.color,
                tradesOnItsOwn: a.tradesOnItsOwn,
                size: 72,
              )
            : null,
        icon: FIcons.messageCircle,
        title: a?.name ?? group?.name ?? l10n.t('newMessage'),
        body: l10n.t('waitingMessage'),
      ),
    );
  }

  Widget _unavailable(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: EdgeInsets.only(top: conversationHeaderExtent(context)),
      child: EmptyState(
        icon: FIcons.messageCircleOff,
        title: l10n.t('conv_unavailable'),
        actionLabel: l10n.t('sh_chats'),
        onAction: () => context.go(Routes.chats),
      ),
    );
  }
}

/// A reply being written reads its own run and stream from the store, so a streamed chunk
/// redraws this row only.
class _LivePreview extends StatelessWidget {
  const _LivePreview({
    required this.threadId,
    required this.runId,
    required this.builder,
  });

  final String threadId;
  final String runId;
  final Widget Function(BuildContext context, Run run, LiveReplyStream? stream)
  builder;

  @override
  Widget build(BuildContext context) {
    final live = context.select((AppState s) {
      final t = s.threads[threadId];
      return (run: t?.runs[runId], stream: t?.streams[runId]);
    });
    final run = live.run;
    if (run == null) return const SizedBox.shrink();
    return builder(context, run, live.stream);
  }
}

/// Retry, enabled again once the provider's Retry-After has passed.
class _RetryButton extends StatefulWidget {
  const _RetryButton({
    required this.retryAt,
    required this.enabled,
    required this.onTap,
  });

  final DateTime? retryAt;
  final bool enabled;
  final VoidCallback onTap;

  @override
  State<_RetryButton> createState() => _RetryButtonState();
}

class _RetryButtonState extends State<_RetryButton> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _arm();
  }

  @override
  void didUpdateWidget(_RetryButton old) {
    super.didUpdateWidget(old);
    if (old.retryAt != widget.retryAt) _arm();
  }

  void _arm() {
    _timer?.cancel();
    final wait = widget.retryAt?.difference(DateTime.now());
    if (wait == null || wait.isNegative) return;
    _timer = Timer(wait + const Duration(milliseconds: 50), () {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final at = widget.retryAt;
    final ready = at == null || !DateTime.now().isBefore(at);
    return RowTextButton(
      label: context.t('retry'),
      enabled: widget.enabled && ready,
      onTap: widget.onTap,
    );
  }
}

/// An older page that did not load: the reason and Retry, in place of the spinner.
class _OlderFailedRow extends StatelessWidget {
  const _OlderFailedRow({required this.onRetry});
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final c = context.ln.colors;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: LnSpace.xs),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Flexible(
            child: InlineEventRow(
              icon: Icon(FIcons.circleAlert, color: c.error),
              label: l10n.t('older'),
              detail: l10n.errorText('request_failed'),
              alignment: InlineEventAlignment.center,
              showChevron: false,
              maxLines: 2,
            ),
          ),
          RowTextButton(label: l10n.t('retry'), onTap: onRetry),
        ],
      ),
    );
  }
}

/// A one-line state above the composer (paused or removed agent).
class _Notice extends StatelessWidget {
  const _Notice({required this.text, this.action});
  final String text;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Padding(
      padding: const EdgeInsets.only(bottom: LnSpace.xs),
      child: Semantics(
        liveRegion: true,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(FIcons.circlePause, size: 16, color: c.fgMuted),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                text,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: ln.text.footnote.copyWith(color: c.fgMuted),
              ),
            ),
            ?action,
          ],
        ),
      ),
    );
  }
}

/// Bubble-shaped placeholders while the first snapshot loads (shimmer, as the list skeleton).
class _ConversationSkeleton extends StatelessWidget {
  const _ConversationSkeleton();

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final base = Color.alphaBlend(c.fill3, c.bg);
    final highlight = Color.alphaBlend(c.fill1, c.bg);
    final reduce = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    const shapes = [
      (true, 200.0, 44.0),
      (false, 250.0, 66.0),
      (false, 160.0, 44.0),
      (true, 230.0, 66.0),
      (false, 280.0, 88.0),
      (true, 140.0, 44.0),
    ];
    final column = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final (i, (owner, w, h)) in shapes.indexed)
          Padding(
            padding: EdgeInsets.only(
              top: i == 0
                  ? 0
                  : (owner == shapes[i - 1].$1
                        ? LnSpace.sameSenderGap
                        : LnSpace.senderChangeGap),
            ),
            child: Align(
              alignment: owner
                  ? AlignmentDirectional.centerEnd
                  : AlignmentDirectional.centerStart,
              child: Container(
                width: w,
                height: h,
                decoration: BoxDecoration(
                  color: base,
                  borderRadius: const BorderRadius.all(
                    Radius.circular(LnRadius.bubble),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
    return Semantics(
      label: context.t('sh_loading'),
      child: ExcludeSemantics(
        child: Padding(
          padding: EdgeInsets.only(
            top: conversationHeaderExtent(context),
            left: LnSpace.pageGutter,
            right: LnSpace.pageGutter,
          ),
          child: Align(
            alignment: Alignment.topCenter,
            child: reduce
                ? column
                : Shimmer.fromColors(
                    baseColor: base,
                    highlightColor: highlight,
                    period: const Duration(milliseconds: 1400),
                    child: column,
                  ),
          ),
        ),
      ),
    );
  }
}
