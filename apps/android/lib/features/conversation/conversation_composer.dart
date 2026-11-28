// The conversation composer: the design kit's Composer pill driving Lonora's send contract
// (apps/mobile/components/thread-composer.tsx, app/thread.tsx `send`): text + `client_nonce`
// through the outbox, reply (`reply_to`), edit and resend (`edited_from`), attachments uploaded one
// by one to `/artifacts/upload` (≤ 10, ≤ 20 MiB each, progress and cancel) from the «+» menu, the
// conversation's web search (a row of that menu), Stop while a run works, and voice notes: a long
// press anywhere on the empty composer records, a tap types, and the mic records hands-free.
// The draft (text, finished files, reply, mentions) is kept on the phone (draft_store.dart);
// «@» lists the agents to mention and «/» at the start lists the commands (composer_assist.dart,
// apps/web/src/conversation/Composer.tsx).
import 'dart:async';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:dio/dio.dart' show CancelToken;
import 'package:file_picker/file_picker.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:image_picker/image_picker.dart';
import 'package:go_router/go_router.dart';
import 'package:path_provider/path_provider.dart';

import '../../app/deep_links.dart' show SharedFile;
import '../../app/routes.dart';
import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../core/storage/local_store.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/thread_actions.dart';
import '../agents/profile/agent_data.dart'
    show agentTemplate, showsTradingControl;
import '../chats/chat_commands.dart' show runChatsAction;
import '../chats/chat_rows.dart' show ChatRow, ChatRowKind;
import '../chats/chats_actions.dart' show ClearRowsAction;
import '../skills/skills_data.dart' show SkillResource, fetchInstalledSkills;
import '../voice/voice_api.dart' show VoiceCalls;
import '../voice/voice_note_button.dart';
import 'assist_list.dart';
import 'composer_assist.dart';
import 'composer_text.dart';
import 'conversation_actions.dart';
import 'conversation_strings.dart';
import 'conversation_timeline.dart';
import 'draft_store.dart';

/// Lonora's per-message attachment limit (apps/mobile/app/thread.tsx `pick`).
const maxAttachments = 10;

/// One picked file and its upload.
class ComposerUpload {
  ComposerUpload({
    required this.name,
    required this.path,
    required this.size,
    this.mime,
    this.temporary = false,
  });

  /// A finished upload kept in a saved draft: [artifact] as `/artifacts/upload` answered it.
  /// It has no local file, so its chip shows the file or image icon.
  ComposerUpload.restored(Json this.artifact)
    : name = asStr(asJson(artifact['payload'])['name']),
      path = '',
      size = asInt(asJson(artifact['payload'])['size']) ?? 0,
      mime = asString(asJson(artifact['payload'])['media_type']),
      temporary = false,
      artifactId = asString(artifact['id']);

  final String name;
  final String path;
  final int size;
  final String? mime;

  /// [path] is this app's own cache copy of a picked file (deleted once it is no longer
  /// needed).
  final bool temporary;
  final CancelToken token = CancelToken();
  double progress = 0;
  String? artifactId;

  /// The upload's artifact once it is done (what a saved draft keeps).
  Json? artifact;
  String? error;

  bool get running => artifactId == null && error == null;
  bool get done => artifactId != null;
  bool get image => mime != null && isImageType(mime!);

  /// Removes the cache copy, if this upload made one.
  void discard() {
    if (!temporary) return;
    try {
      File(path).deleteSync();
    } catch (_) {
      // Already gone.
    }
  }
}

/// What the composer keeps per conversation while the owner looks elsewhere.
class _Draft {
  String text = '';
  Message? reply;
  String? replyAuthor;
  List<ComposerUpload> files = [];
  List<MentionRange> mentions = const [];
}

class ConversationComposer extends StatefulWidget {
  const ConversationComposer({
    super.key,
    required this.threadId,
    this.running = false,
    this.webSearch = false,
    this.enabled = true,
    this.suggestion,
    this.agentName,
    this.onSent,
    this.onStop,
    this.agent,
    this.group,
    this.members = const [],
    this.agents = const [],
    this.collaborationSessionId,
    this.assist = true,
    this.callable = false,
  });

  final String threadId;

  /// The agent of a direct conversation (the hint names it).
  final String? agentName;

  /// The direct conversation's agent (its commands, skills and call), or null.
  final Agent? agent;

  /// The group conversation's group, or null.
  final Group? group;

  /// The group's member agents (whom «@» lists in a group).
  final List<Agent> members;

  /// Every agent of the owner (a direct chat can bring any other one in with «@»).
  final List<Agent> agents;

  /// The direct chat's open collaboration session: «@الكل» addresses it.
  final String? collaborationSessionId;

  /// «اقتراحات @» is on: the @ and / lists show while typing.
  final bool assist;

  /// A voice call can start from «/اتصال» (a direct chat with an agent that is not paused).
  final bool callable;

  /// A run of this conversation is working: an empty field shows Stop.
  final bool running;

  /// The conversation's web search is on (shown as a removable chip).
  final bool webSearch;

  /// False when the conversation can no longer receive messages.
  final bool enabled;

  /// The agent's suggested reply (shown as a chip above the field while it is empty).
  final String? suggestion;

  /// After a message is handed to the outbox (the transcript scrolls to the end).
  final VoidCallback? onSent;
  final VoidCallback? onStop;

  @override
  State<ConversationComposer> createState() => ConversationComposerState();
}

class ConversationComposerState extends State<ConversationComposer>
    with WidgetsBindingObserver {
  static final Map<String, _Draft> _drafts = {};

  /// Conversations whose draft changed in this run: a saved copy on the phone is older.
  static final Set<String> _touched = {};

  /// Forgets every kept draft, in memory at once and on the phone when the returned future
  /// completes (sign-out, expiry, tests): pending writes finish first, then the drafts go.
  static Future<void> clearDrafts() {
    _drafts.clear();
    _touched.clear();
    return DraftStore.clearAll();
  }

  /// An app restart, for tests: the drafts in memory go, the phone's copies stay.
  @visibleForTesting
  static void debugForgetMemory() {
    _drafts.clear();
    _touched.clear();
  }

  final controller = ComposerTextController();
  final focusNode = FocusNode();
  Message? _reply;
  String? _replyAuthor;
  Message? _editing;
  final List<ComposerUpload> _uploads = [];
  bool _recording = false;

  /// The committed @mentions, and the text they were rebased against last.
  List<MentionRange> _mentions = const [];
  String _prevText = '';

  /// The owner's changes since this composer opened (a saved draft never overwrites one).
  int _revision = 0;

  /// The draft store's scope (server and owner) and the sign-out generation at mount.
  String? _scope;
  late int _generation;
  Timer? _saveTimer;
  bool _restoreAsked = false;

  /// A list the owner closed with Back stays closed until its query changes.
  String? _dismissed;
  bool _picking = false;
  bool _clearing = false;

  /// The agent's skills for «/» (loaded the first time «/» starts the message).
  List<SkillResource> _skills = const [];
  String? _skillsAgent;
  bool _slashed = false;

  /// The composer itself: the «+» menu hangs from its top.
  final _pill = GlobalKey(debugLabel: 'composer');

  late final VoiceNoteController _voice = VoiceNoteController(
    threadId: widget.threadId,
    onRecordingChanged: (value) {
      if (!mounted) return;
      // Recording closes the keyboard: the field gives up its focus.
      if (value) focusNode.unfocus();
      setState(() => _recording = value);
    },
  );

  @override
  void initState() {
    super.initState();
    _generation = DraftStore.generation;
    WidgetsBinding.instance.addObserver(this);
    final draft = _drafts[widget.threadId];
    if (draft != null) {
      _prevText = draft.text;
      _mentions = draft.mentions;
      controller.text = draft.text;
      _reply = draft.reply;
      _replyAuthor = draft.replyAuthor;
      _uploads.addAll(draft.files);
    }
    controller.addListener(_changed);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_restoreAsked) return;
    _restoreAsked = true;
    final session = context.read().session;
    final owner = session.owner;
    final server = session.server;
    if (!session.signedIn || owner == null || server == null) return;
    _scope = LocalStore.scope(server, owner.id);
    // The draft kept in memory (this run) is newer than the phone's copy.
    if (!_drafts.containsKey(widget.threadId) &&
        !_touched.contains(widget.threadId)) {
      unawaited(_restore(_scope!));
    }
  }

  /// Brings the phone's saved draft back when nothing was typed since the composer opened
  /// (apps/mobile/lib/draft-store.ts `restoreDraft`). Silent: a missing or broken draft is none.
  Future<void> _restore(String scope) async {
    final generation = _generation;
    final store = await DraftStore.instance();
    final saved = await store?.read(scope, widget.threadId);
    if (saved == null ||
        !mounted ||
        generation != DraftStore.generation ||
        _revision != 0 ||
        _touched.contains(widget.threadId) ||
        controller.text.isNotEmpty ||
        _reply != null ||
        _uploads.isNotEmpty ||
        _editing != null) {
      return;
    }
    setState(() {
      _prevText = saved.text;
      _mentions = _inPool(saved.mentions);
      controller.value = TextEditingValue(
        text: saved.text,
        selection: TextSelection.collapsed(offset: saved.text.length),
      );
      final reply = saved.reply;
      if (reply != null) {
        _reply = Message.fromJson(reply);
        _replyAuthor = saved.replyAuthor;
      }
      _uploads.addAll(saved.files.map(ComposerUpload.restored));
    });
    for (final f in saved.files) {
      context.dispatch(AddThreadArtifactAction(widget.threadId, f));
    }
  }

  void _changed() {
    final text = controller.text;
    if (text != _prevText) {
      _mentions = rebaseMentions(_prevText, text, _mentions);
      _prevText = text;
      _touch();
    }
    // The first «/» that starts the message loads the agent's skills.
    final before = _beforeCaret;
    final slashed = commandQuery(before) != null;
    if (slashed && !_slashed) _loadSkills();
    _slashed = slashed;
    // A list closed with Back opens again for the next «@» or «/».
    if (!slashed && mentionQuery(before) == null) _dismissed = null;
    setState(() {});
  }

  /// The owner changed the draft: it is saved shortly (an empty one is deleted at once).
  void _touch() {
    _revision++;
    _touched.add(widget.threadId);
    _scheduleSave();
  }

  SavedDraft _snapshot() => SavedDraft(
    // An edit's text never stays behind as a draft.
    text: _editing == null ? controller.text : '',
    files: [
      for (final u in _uploads)
        if (u.done && u.artifact != null) u.artifact!,
    ],
    reply: _reply?.raw,
    replyAuthor: _reply == null ? null : _replyAuthor,
    mentions: _editing == null ? _mentions : const [],
  );

  void _scheduleSave() {
    if (_scope == null) return;
    _saveTimer?.cancel();
    _saveTimer = null;
    if (_snapshot().isEmpty) {
      _writeDraft(null);
      return;
    }
    _saveTimer = Timer(const Duration(milliseconds: 400), () {
      _saveTimer = null;
      _writeDraft(_snapshot());
    });
  }

  /// Writes a save still waiting for its pause (closing, the app going to the background).
  void _flushSave() {
    if (_saveTimer?.isActive ?? false) {
      _saveTimer!.cancel();
      _saveTimer = null;
      _writeDraft(_snapshot());
    }
  }

  void _writeDraft(SavedDraft? draft) {
    final scope = _scope;
    if (scope == null) return;
    final generation = _generation;
    final threadId = widget.threadId;
    unawaited(
      DraftStore.instance().then(
        (store) => store?.write(scope, threadId, draft, generation: generation),
      ),
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // The process can be killed in the background before the pause ends.
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      _flushSave();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _flushSave();
    // An edit never stays behind as a draft; finished files and the reply do. Nothing stays
    // once the owner signed out meanwhile.
    if (_generation == DraftStore.generation) {
      final draft = _drafts.putIfAbsent(widget.threadId, _Draft.new)
        ..text = _editing == null ? controller.text : ''
        ..reply = _reply
        ..replyAuthor = _replyAuthor
        ..files = _uploads.where((u) => u.done).toList()
        ..mentions = _editing == null ? _mentions : const [];
      if (draft.text.isEmpty && draft.reply == null && draft.files.isEmpty) {
        _drafts.remove(widget.threadId);
      }
    }
    for (final u in _uploads) {
      if (u.running) u.token.cancel('composer_closed');
      if (!u.done) u.discard();
    }
    _voice.dispose();
    controller.dispose();
    focusNode.dispose();
    super.dispose();
  }

  /// Quotes [message] in the next send.
  void reply(Message message, String author) {
    setState(() {
      _editing = null;
      _reply = message;
      _replyAuthor = author;
    });
    _touch();
    focusNode.requestFocus();
  }

  /// «تعديل وإعادة الإرسال»: the next send replaces [message]. The edit starts without
  /// mentions (Web).
  void edit(Message message) {
    setState(() {
      _reply = null;
      _editing = message;
      _mentions = const [];
      _prevText = message.content;
      controller.text = message.content;
    });
    _touch();
    focusNode.requestFocus();
  }

  /// «مسح»: the text, the finished files, the reply, the mentions and the saved draft go;
  /// uploads still running stay.
  void clearDraft() {
    setState(() {
      _editing = null;
      _reply = null;
      _replyAuthor = null;
      _mentions = const [];
      _prevText = '';
      controller.clear();
      for (final u in _uploads) {
        if (u.done || u.error != null) u.discard();
      }
      _uploads.removeWhere((u) => u.done || u.error != null);
    });
    _drafts.remove(widget.threadId);
    _touch();
  }

  /// Text shared into the app joins the field.
  void addText(String text) {
    final current = controller.text;
    controller.text = current.isEmpty ? text : '$current\n$text';
  }

  /// Files shared into the app (already on disk) upload as attachments.
  void addSharedFiles(List<SharedFile> files) {
    for (final f in files) {
      _add(
        ComposerUpload(
          name: f.name,
          path: f.path,
          size: f.size > 0 ? f.size : _sizeOf(f.path),
          mime: f.mimeType ?? mimeFor(f.name),
        ),
      );
    }
  }

  int _sizeOf(String path) {
    try {
      return File(path).lengthSync();
    } catch (_) {
      return 0;
    }
  }

  bool get _uploading => _uploads.any((u) => u.running);
  List<ComposerUpload> get _ready => _uploads.where((u) => u.done).toList();

  void _toast(String text, {LnToastKind kind = LnToastKind.error}) {
    if (mounted) LnToast.show(context, text, kind: kind);
  }

  /// The owner text of an error code, when still on screen.
  void _toastError(String code) {
    if (mounted) _toast(context.l10n.errorText(code));
  }

  /// Adds one file within Lonora's limits and starts its upload.
  void _add(ComposerUpload upload) {
    final l10n = context.l10n;
    if (_uploads.length >= maxAttachments) {
      _toast(l10n.t('attachLimit'));
      return;
    }
    if (attachmentTooLarge(upload.size)) {
      _toast(l10n.errorText('attachment_too_large'));
      return;
    }
    setState(() => _uploads.add(upload));
    unawaited(_upload(upload));
  }

  Future<void> _upload(ComposerUpload u) async {
    try {
      final data = asJson(
        await api.upload(
          '/artifacts/upload',
          filePath: u.path,
          fileName: u.name,
          mimeType: u.mime,
          fields: {'thread_id': widget.threadId},
          cancelToken: u.token,
          onProgress: (sent, total) {
            if (total <= 0) return;
            u.progress = sent / total;
            if (mounted) setState(() {});
          },
        ),
      );
      u.artifactId = asString(data['id']);
      if (u.artifactId == null) {
        u.error = 'request_failed';
      } else {
        u.artifact = data;
      }
      if (mounted) {
        if (u.artifactId != null) {
          context.dispatch(AddThreadArtifactAction(widget.threadId, data));
          _touch();
        }
        setState(() {});
      }
    } on ApiError catch (e) {
      if (e.code == 'upload_cancelled') return;
      u.error = e.code;
      u.discard();
      if (mounted) {
        setState(() {});
        _toast(context.l10n.errorText(e.code));
      }
    } on SessionRequestCancelled {
      u.error = 'cancelled';
    } catch (_) {
      u.error = 'request_failed';
      u.discard();
      if (mounted) {
        setState(() {});
        _toast(context.l10n.errorText('request_failed'));
      }
    }
  }

  void _remove(ComposerUpload u) {
    if (u.running) u.token.cancel('removed');
    u.discard();
    setState(() => _uploads.remove(u));
    _touch();
  }

  /// The text before the caret (the whole text when the field has no caret).
  String get _beforeCaret {
    final text = controller.text;
    final caret = controller.selection.baseOffset;
    return caret < 0 || caret > text.length ? text : text.substring(0, caret);
  }

  int get _caret {
    final caret = controller.selection.baseOffset;
    return caret < 0 || caret > controller.text.length
        ? controller.text.length
        : caret;
  }

  /// Whom «@» offers: the group's members, or in a direct chat every other agent.
  List<Agent> get _pool => widget.group != null
      ? widget.members
      : [
          for (final a in widget.agents)
            if (a.id != widget.agent?.id) a,
        ];

  /// [ranges] without a mention of an agent that left the conversation's pool (the server
  /// would refuse it). Until the shell has loaded from the server the pool is not known
  /// (a cold start, a cleared cache), and every range is kept.
  List<MentionRange> _inPool(List<MentionRange> ranges) {
    if (!context.read().shell.loaded) return ranges;
    final pool = {for (final a in _pool) a.id};
    return [
      for (final m in ranges)
        if (m.agentId == null || pool.contains(m.agentId)) m,
    ];
  }

  /// The chat's «/» rows: its commands, then (direct chats) the agent's skills.
  List<CommandOption> _commandRows(L10n l10n) {
    final agent = widget.agent;
    final group = widget.group != null;
    return commandRows(
      l10n,
      group: group,
      symbol: agent?.tradingSymbol,
      // No live readiness here: a personal agent shows «/شارت» only with a symbol or an
      // account.
      trading:
          agent != null &&
          (agentTemplate(agent) == 'trading' || showsTradingControl(agent)),
      name: agent?.name ?? widget.group?.name ?? '',
      callable: widget.callable,
      skills: group ? const [] : _skills,
    );
  }

  /// `GET /skills?agent_id=` once per conversation and agent; a failure leaves the built-in
  /// commands and tries again on the next «/».
  void _loadSkills() {
    final agent = widget.agent;
    if (widget.group != null || agent == null || _skillsAgent == agent.id) {
      return;
    }
    final id = agent.id;
    _skillsAgent = id;
    _skills = const [];
    fetchInstalledSkills(id).then(
      (rows) {
        if (mounted && _skillsAgent == id) setState(() => _skills = rows);
      },
      onError: (Object _) {
        if (_skillsAgent == id) _skillsAgent = null;
      },
    );
  }

  /// A second pick in the same frame is ignored.
  bool _once() {
    if (_picking) return false;
    _picking = true;
    WidgetsBinding.instance.addPostFrameCallback((_) => _picking = false);
    return true;
  }

  /// Replaces the «@…» being typed with [agent]'s token (or «@الكل» for null) and commits it.
  void _pickMention(Agent? agent) {
    if (!_once()) return;
    final text = controller.text;
    final caret = _caret;
    final start = text.substring(0, caret).lastIndexOf('@');
    if (start < 0) return;
    final token = '@${agent?.name ?? context.l10n.t('conv_all')}';
    final next = '${text.substring(0, start)}$token ${text.substring(caret)}';
    final mentions = [
      ...rebaseMentions(text, next, _mentions),
      MentionRange(
        agentId: agent?.id,
        sessionId: agent == null ? widget.collaborationSessionId : null,
        token: token,
        start: start,
        end: start + token.length,
      ),
    ];
    // The listener sees the new text as already rebased.
    _mentions = mentions;
    _prevText = next;
    controller.value = TextEditingValue(
      text: next,
      selection: TextSelection.collapsed(offset: start + token.length + 1),
    );
    _touch();
    focusNode.requestFocus();
  }

  /// A command from the «/» list: one that takes text stays in the field as «/name »; the
  /// others run at once (what was typed of the command goes, anything after it stays).
  void _pickCommand(CommandOption row) {
    if (!_once()) return;
    final text = controller.text;
    final rest = text.substring(_caret).replaceFirst(RegExp(r'^\S*[ \t]*'), '');
    final next = row.argument ? '/${row.name} $rest' : rest;
    final caret = row.argument ? row.name.length + 2 : 0;
    controller.value = TextEditingValue(
      text: next,
      selection: TextSelection.collapsed(offset: caret),
    );
    if (row.argument) {
      focusNode.requestFocus();
      return;
    }
    if (row.command == 'summary') {
      _sendSummary(row);
    } else {
      _runCommand(row.command);
    }
  }

  /// «/ملخص»: sent at once with the reply; only the reply bar goes, the rest of the text
  /// stays.
  void _sendSummary(CommandOption row) {
    context.dispatch(
      SendMessageAction(widget.threadId, {
        'content': '/${row.name}',
        'attachment_ids': <String>[],
        'reply_to': ?_reply?.id,
        'mention_agent_ids': <String>[],
        'mention_all': false,
        'command': {'name': 'summary', 'argument': ''},
      }),
    );
    setState(() {
      _reply = null;
      _replyAuthor = null;
    });
    _touch();
    widget.onSent?.call();
  }

  /// The commands that send nothing open what the chat already has.
  void _runCommand(String command) {
    switch (command) {
      case 'chart':
        context.push(
          Routes.charts(threadId: widget.threadId, agentId: widget.agent?.id),
        );
      case 'call':
        final agent = widget.agent;
        if (agent != null && widget.callable) {
          unawaited(
            VoiceCalls.start(
              context,
              agentId: agent.id,
              threadId: widget.threadId,
            ),
          );
        }
      case 'clear':
        unawaited(_clearChat());
    }
  }

  /// «/مسح»: after the confirmation, the chat's messages are hidden for the owner
  /// (`POST /threads/{id}/clear`, the chat list's own action) and the draft goes.
  Future<void> _clearChat() async {
    if (_clearing) return;
    _clearing = true;
    try {
      final l10n = context.l10n;
      final group = widget.group;
      final ok = await showLnConfirm(
        context,
        title: l10n.t('sh_clearMessagesQ'),
        message: l10n.t(group != null ? 'clearChatGroup' : 'clearChatAgent'),
        confirmLabel: l10n.t('sh_clear'),
        cancelLabel: l10n.t('sh_cancel'),
        destructive: true,
      );
      if (!ok || !mounted) return;
      final threadId = widget.threadId;
      final id = group?.id ?? widget.agent?.id ?? '';
      final row = ChatRow(
        key: group != null ? 'group:$id' : 'agent:$id',
        kind: group != null ? ChatRowKind.group : ChatRowKind.agent,
        id: id,
        name: group?.name ?? widget.agent?.name ?? '',
        agent: widget.agent,
        group: group,
        entry: context.read().shell.entryFor(threadId),
        threadId: threadId,
      );
      if (!await runChatsAction(context, ClearRowsAction([row]))) return;
      if (!mounted) return;
      context.dispatch(
        PatchThreadAction(
          threadId,
          (t) => t.copyWith(messages: const [], streams: const {}),
        ),
      );
      context.dispatch(LoadThreadAction(threadId));
      clearDraft();
    } finally {
      _clearing = false;
    }
  }

  void _send(String _) {
    // The mention ranges index the untrimmed text.
    final raw = controller.text;
    final text = raw.trim();
    final editing = _editing != null;
    // An edit carries no files: uploads still running (or done) wait for the next send.
    if (!widget.enabled || (!editing && _uploading)) return;
    final l10n = context.l10n;
    final ready = _ready;
    // An edit or a message with files is never a command: it is sent as the text it is.
    final typed = editing || _uploads.isNotEmpty
        ? null
        : parseCommand(raw, _commandRows(l10n));
    Json? command;
    if (typed != null) {
      final option = typed.option;
      if (option.argument && !option.skill && typed.argument.isEmpty) {
        // An LRM keeps the «/» before the command's name inside Arabic text.
        _toast(
          l10n.t(
            option.command == 'task' ? 'cmdTaskMissing' : 'cmdSearchMissing',
            ['\u200e/${option.name}'],
          ),
          kind: LnToastKind.notice,
        );
        return;
      }
      command = sentCommand(option, typed.argument);
      if (command == null) {
        if (!_once()) return;
        // «/شارت», «/اتصال», «/مسح» typed in full: the text and the reply go, the command runs.
        controller.clear();
        setState(() {
          _reply = null;
          _replyAuthor = null;
          _mentions = const [];
        });
        _touch();
        _runCommand(option.command);
        return;
      }
    }
    final address = mentionAddress(
      raw,
      _inPool(_mentions),
      everyone: widget.group?.memberIds,
    );
    final mentions = {
      'mention_agent_ids': address.agentIds,
      'mention_all': address.all,
      'collaboration_session_id': ?address.sessionId,
    };
    final Json body;
    if (editing) {
      // An edit replaces the message with new text, never with files alone.
      if (text.isEmpty) return;
      body = {
        'content': text,
        'edited_from': _editing!.id,
        'attachment_ids': <String>[],
        ...mentions,
      };
    } else {
      if (text.isEmpty && ready.isEmpty) return;
      body = {
        'content': text.isEmpty ? l10n.t('attach') : text,
        'attachment_ids': [for (final u in ready) u.artifactId!],
        'reply_to': ?_reply?.id,
        ...mentions,
        'command': ?command,
      };
    }
    context.dispatch(SendMessageAction(widget.threadId, body));
    controller.clear();
    setState(() {
      _reply = null;
      _replyAuthor = null;
      _editing = null;
      _mentions = const [];
      if (!editing) {
        for (final u in _uploads) {
          if (u.done || u.error != null) u.discard();
        }
        _uploads.removeWhere((u) => u.done || u.error != null);
      }
    });
    _drafts.remove(widget.threadId);
    // The saved copy goes at once: a restart right after Send never brings it back.
    _touch();
    widget.onSent?.call();
  }

  /// The attach menu's start edge sits this far inside the composer's.
  static const double attachMenuInset = 7;

  /// «+»: Camera · Photos · Files (only what Lonora supports), then the conversation's web
  /// search, checked while it is on; a menu over the composer, without a scrim. The limits are
  /// enforced as files are picked (a toast says the limit when it is reached); turning web search
  /// on says what it does.
  Future<void> _openAttach() async {
    final l10n = context.l10n;
    registerConversationStrings(l10n);
    final box = _pill.currentContext?.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return;
    // Inset on both sides alike: the menu keeps to the composer's start edge.
    final pill = box.localToGlobal(Offset.zero) & box.size;
    final choice = await showLnPopoverMenu<String>(
      context,
      anchorRect: Rect.fromLTRB(
        pill.left + attachMenuInset,
        pill.top,
        pill.right - attachMenuInset,
        pill.bottom,
      ),
      // Over the composer's top edge, as the menu grows from the «+».
      gap: -4,
      semanticLabel: l10n.t('addToConversation'),
      selected: widget.webSearch ? 'web' : null,
      actions: [
        LnMenuAction(
          value: 'camera',
          icon: FIcons.camera,
          label: l10n.t('conv_camera'),
        ),
        LnMenuAction(
          value: 'photos',
          icon: FIcons.image,
          label: l10n.t('pickPhotos'),
        ),
        LnMenuAction(
          value: 'files',
          icon: FIcons.file,
          label: l10n.t('pickFiles'),
        ),
        LnMenuAction(
          value: 'web',
          icon: FIcons.globe,
          label: l10n.t('webSearch'),
        ),
      ],
    );
    if (!mounted) return;
    switch (choice) {
      case 'camera':
        await _pickCamera();
      case 'photos':
        await _pickPhotos();
      case 'files':
        await _pickFiles();
      case 'web':
        await _setWebSearch(!widget.webSearch);
    }
  }

  /// Turns the conversation's web search on or off (`PUT /threads/{id}/options`).
  Future<void> _setWebSearch(bool on) async {
    final action = ToggleWebSearchAction(widget.threadId, on);
    await context.dispatchAndWait(action);
    if (!mounted) return;
    if (action.errorCode != null) {
      _toast(context.l10n.errorText(action.errorCode));
    } else {
      _toast(
        context.l10n.t(on ? 'webSearchOn' : 'webSearchOff'),
        kind: LnToastKind.normal,
      );
    }
  }

  int get _room => maxAttachments - _uploads.length;

  Future<void> _pickCamera() async {
    if (_room <= 0) return _toast(context.l10n.t('attachLimit'));
    try {
      final shot = await ImagePicker().pickImage(
        source: ImageSource.camera,
        imageQuality: 90,
      );
      if (shot == null || !mounted) return;
      final size = await shot.length();
      if (!mounted) return;
      _add(
        ComposerUpload(
          name: shot.name,
          path: shot.path,
          size: size,
          mime: shot.mimeType ?? mimeFor(shot.name) ?? 'image/jpeg',
        ),
      );
    } on PlatformException {
      _toastError('request_failed');
    }
  }

  Future<void> _pickPhotos() async {
    final room = _room;
    if (room <= 0) return _toast(context.l10n.t('attachLimit'));
    try {
      final picked = await ImagePicker().pickMultiImage(
        limit: room >= 2 ? room : null,
      );
      if (!mounted) return;
      if (picked.length > room) _toast(context.l10n.t('attachLimit'));
      for (final x in picked.take(room)) {
        final size = await x.length();
        if (!mounted) return;
        _add(
          ComposerUpload(
            name: x.name,
            path: x.path,
            size: size,
            mime: x.mimeType ?? mimeFor(x.name),
          ),
        );
      }
    } on PlatformException {
      _toastError('request_failed');
    }
  }

  Future<void> _pickFiles() async {
    final room = _room;
    if (room <= 0) return _toast(context.l10n.t('attachLimit'));
    try {
      final picked = await FilePicker.pickFiles();
      if (!mounted) return;
      if (picked.length > room) _toast(context.l10n.t('attachLimit'));
      for (final f in picked.take(room)) {
        final size = f.lengthSync() ?? await f.length() ?? 0;
        if (!mounted) return;
        if (attachmentTooLarge(size)) {
          _toastError('attachment_too_large');
          continue;
        }
        final copy = f.path == null ? await _copyToTemp(f) : null;
        final path = f.path ?? copy;
        if (!mounted) {
          if (copy != null) _deleteQuietly(copy);
          return;
        }
        if (path == null) continue;
        _add(
          ComposerUpload(
            name: f.name,
            path: path,
            size: size,
            mime: mimeFor(f.name),
            temporary: copy != null,
          ),
        );
      }
    } on PlatformException {
      _toastError('request_failed');
    }
  }

  /// A file the picker only exposes as a content URI is copied to the cache to upload it
  /// (under a name of its own: the display name never becomes a path).
  Future<String?> _copyToTemp(PlatformFile f) async {
    try {
      final dir = await getTemporaryDirectory();
      final safe = f.name.replaceAll(RegExp(r'[/\\\x00]|\.\.'), '_');
      final target = File(
        '${dir.path}/lonora_upload_${DateTime.now().microsecondsSinceEpoch}_$safe',
      );
      final sink = target.openWrite();
      await sink.addStream(f.readAsByteStream());
      await sink.close();
      return target.path;
    } catch (_) {
      return null;
    }
  }

  void _deleteQuietly(String path) {
    try {
      File(path).deleteSync();
    } catch (_) {
      // Already gone.
    }
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final text = controller.text.trim();
    final editing = _editing;
    final reply = _reply;
    final ready = _ready;
    final enabled = widget.enabled && !_recording;

    // «/» at the start (never in an edit) or «@» before the caret: the list above the pill,
    // while «اقتراحات @» is on (apps/web Composer.tsx `assistOpen`).
    final rows = _commandRows(l10n);
    final before = _beforeCaret;
    final commandTyped = editing == null ? commandQuery(before) : null;
    final mentionTyped = mentionQuery(before);
    final ranked = widget.assist && commandTyped != null
        ? rankCommands(rows, commandTyped)
        : null;
    final List<Agent?> mentionOptions =
        ranked == null && widget.assist && mentionTyped != null
        ? [
            ...guestCandidates(
              mentionCandidates(_pool, mentionTyped),
              direct: widget.group == null,
              self: widget.agent?.id,
            ).take(6),
            if ((widget.group != null ||
                    widget.collaborationSessionId != null) &&
                matchesEveryone(mentionTyped))
              null,
          ]
        : const [];
    final listKey = ranked != null
        ? 'c:$commandTyped'
        : mentionOptions.isNotEmpty
        ? 'm:$mentionTyped:${before.lastIndexOf('@')}'
        : null;
    final listShown = listKey != null && listKey != _dismissed && enabled;
    // A command typed in full: marked in the field, and its hint while no text follows it.
    final typed = editing != null || _uploads.isNotEmpty
        ? null
        : parseCommand(controller.text, rows);
    final hint = !listShown && typed != null && typed.argument.isEmpty
        ? typed.option.hint
        : null;
    controller
      ..mentions = _mentions
      ..command = typed == null ? null : (typed.start, typed.end)
      ..mentionFill = c.brand.withValues(alpha: 0.24)
      ..commandFill = c.fg.withValues(alpha: 0.13);

    Widget? replyBar;
    if (editing != null) {
      replyBar = ComposerReplyBar(
        icon: FIcons.pencil,
        title: l10n.t('editTheMessage'),
        text: plainLine(editing.content),
        closeLabel: l10n.t('cancelEdit'),
        onClose: () {
          setState(() {
            _editing = null;
            controller.clear();
          });
          _touch();
        },
      );
    } else if (reply != null) {
      // A plain quote: the bar's own quote mark says it is a reply.
      replyBar = ComposerReplyBar(
        text: plainLine(reply.content).isEmpty
            ? l10n.t('attachments')
            : plainLine(reply.content),
        closeLabel: l10n.t('cancelReply'),
        onClose: () {
          setState(() {
            _reply = null;
            _replyAuthor = null;
          });
          _touch();
        },
      );
    }

    final chips = <Widget>[
      if (widget.webSearch)
        _WebSearchChip(
          label: l10n.t('webSearch'),
          removeLabel: l10n.t('webSearchIsOn'),
          onRemove: () => _setWebSearch(false),
        ),
      // An edit carries no files: the attached ones wait (hidden) for the next send.
      if (editing == null)
        for (final u in _uploads)
          ComposerAttachmentChip(
            label: u.name,
            icon: u.image ? FIcons.image : FIcons.file,
            // A file restored from a saved draft has no local copy: its icon stands for it.
            thumbnail: u.image && u.path.isNotEmpty
                ? Image.file(
                    File(u.path),
                    fit: BoxFit.cover,
                    cacheWidth: 96,
                    errorBuilder: (_, _, _) =>
                        Icon(FIcons.image, size: 18, color: c.fgMuted),
                  )
                : null,
            progress: u.running ? u.progress : null,
            failed: u.error != null,
            removeLabel: u.running
                ? l10n.t('cancelUpload')
                : l10n.t('removeAttachment'),
            onRemove: () => _remove(u),
          ),
    ];

    // Files alone are sent from the pill's send disc; the voice-note mic is its mic slot.
    final filesOnly = text.isEmpty && editing == null && ready.isNotEmpty;

    // While recording, the recording bar takes the pill's place: the pill stays mounted
    // underneath, hidden and inert, so the hold that started it keeps reporting.
    _voice.bind(context);
    registerConversationStrings(l10n);
    final composer = Composer(
      key: _pill,
      controller: controller,
      focusNode: focusNode,
      placeholder: widget.agentName == null
          ? l10n.t('message')
          : l10n.t('conv_messageTo', [widget.agentName!]),
      enabled: widget.enabled,
      inputEnabled: !_recording,
      running: widget.running,
      sendEnabled: editing != null || !_uploading,
      onSend: _send,
      onAttach: editing == null ? _openAttach : null,
      // While the agent works, the empty composer names the agent; the hold still records.
      holdToTalk: widget.enabled
          ? _voice.holdToTalk(
              placeholder: widget.running ? null : l10n.t('conv_holdToTalk'),
            )
          : null,
      recordingBar: _recording
          ? VoiceNoteRecordingBar(controller: _voice)
          : null,
      micButton: VoiceNoteButton(controller: _voice, enabled: widget.enabled),
      sendWithoutText: filesOnly,
      onStop: widget.onStop,
      attachLabel: l10n.t('attach'),
      micLabel: l10n.t('voiceNote'),
      sendLabel: l10n.t('send'),
      stopLabel: l10n.t('cancel'),
      replyBar: replyBar,
      attachments: chips.isEmpty
          ? null
          : SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  for (final (i, chip) in chips.indexed) ...[
                    if (i > 0) const SizedBox(width: LnSpace.xs),
                    chip,
                  ],
                ],
              ),
            ),
    );

    final suggestion = widget.suggestion;
    Widget? list;
    if (listShown && ranked != null) {
      list = CommandList(
        rows: ranked,
        query: commandTyped ?? '',
        agentName: widget.agent?.name ?? '',
        onPick: _pickCommand,
      );
    } else if (listShown) {
      list = MentionList(
        options: mentionOptions,
        group: widget.group != null,
        leadId: widget.group?.leadAgentId,
        alerted: widget.members.where((a) => !a.paused).length,
        onPick: _pickMention,
      );
    }
    // Back closes an open list first, not the conversation.
    return PopScope(
      canPop: !listShown,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && listKey != null) setState(() => _dismissed = listKey);
      },
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (list != null)
            Padding(
              padding: const EdgeInsets.only(bottom: LnSpace.xs),
              child: list,
            ),
          if (hint != null)
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(14, 0, 14, 4),
              child: Text(
                hint,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: ln.text.footnote.copyWith(
                  color: c.fgMuted,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ),
          if (list == null &&
              suggestion != null &&
              suggestion.isNotEmpty &&
              text.isEmpty &&
              editing == null &&
              enabled)
            Padding(
              // The chip's 48 dp touch target adds 4 dp below it.
              padding: const EdgeInsets.only(bottom: LnSpace.xs - 4),
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: _SuggestionChip(
                  text: suggestion,
                  semanticLabel: l10n.t('suggestedReply', [suggestion]),
                  onTap: () {
                    controller.text = suggestion;
                    controller.selection = TextSelection.collapsed(
                      offset: suggestion.length,
                    );
                    focusNode.requestFocus();
                  },
                ),
              ),
            ),
          composer,
        ],
      ),
    );
  }
}

/// «البحث في الويب» while it is on; ✕ turns it off (apps/mobile: the globe beside «+»).
class _WebSearchChip extends StatelessWidget {
  const _WebSearchChip({
    required this.label,
    required this.removeLabel,
    required this.onRemove,
  });

  final String label;
  final String removeLabel;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: onRemove,
      semanticLabel: removeLabel,
      excludeChildSemantics: true,
      child: Container(
        height: 48,
        padding: const EdgeInsetsDirectional.fromSTEB(12, 0, 8, 0),
        decoration: BoxDecoration(
          color: c.fill1,
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.field)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(FIcons.globe, size: 18, color: c.selection),
            const SizedBox(width: 6),
            Text(label, style: ln.text.captionStrong.copyWith(color: c.fg)),
            const SizedBox(width: 4),
            Icon(FIcons.x, size: 16, color: c.fgMuted),
          ],
        ),
      ),
    );
  }
}

/// The agent's suggested reply: a stadium chip; a tap puts it in the field.
class _SuggestionChip extends StatelessWidget {
  const _SuggestionChip({
    required this.text,
    required this.semanticLabel,
    required this.onTap,
  });

  final String text;
  final String semanticLabel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: onTap,
      haptic: true,
      semanticLabel: semanticLabel,
      excludeChildSemantics: true,
      child: Padding(
        // A 40 dp chip in a 48 dp touch target.
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Container(
          constraints: const BoxConstraints(minHeight: 40, maxWidth: 320),
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: 14,
            vertical: 9,
          ),
          decoration: ShapeDecoration(
            color: c.surface,
            shape: StadiumBorder(side: BorderSide(color: c.border)),
            shadows: ln.chromeShadow,
          ),
          child: Text(
            text,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: ln.text.caption.copyWith(color: c.fg),
          ),
        ),
      ),
    );
  }
}
