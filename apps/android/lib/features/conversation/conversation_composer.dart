// The conversation composer: the design kit's Composer pill driving Lonora's send contract
// (apps/mobile/components/thread-composer.tsx, app/thread.tsx `send`): text + `client_nonce`
// through the outbox, reply (`reply_to`), edit and resend (`edited_from`), attachments uploaded one
// by one to `/artifacts/upload` (≤ 10, ≤ 20 MiB each, progress and cancel) from the «+» menu, the
// conversation's web search (a row of that menu), Stop while a run works, and voice notes: a long
// press anywhere on the empty composer records, a tap types, and the mic records hands-free.
import 'dart:async';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:dio/dio.dart' show CancelToken;
import 'package:file_picker/file_picker.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';

import '../../app/deep_links.dart' show SharedFile;
import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/thread_actions.dart';
import '../voice/voice_note_button.dart';
import 'conversation_actions.dart';
import 'conversation_strings.dart';
import 'conversation_timeline.dart';

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
  });

  final String threadId;

  /// The agent of a direct conversation (the hint names it).
  final String? agentName;

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

class ConversationComposerState extends State<ConversationComposer> {
  static final Map<String, _Draft> _drafts = {};

  /// Forgets every kept draft (sign-out, tests).
  static void clearDrafts() => _drafts.clear();

  final controller = TextEditingController();
  final focusNode = FocusNode();
  Message? _reply;
  String? _replyAuthor;
  Message? _editing;
  final List<ComposerUpload> _uploads = [];
  bool _recording = false;

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
    final draft = _drafts[widget.threadId];
    if (draft != null) {
      controller.text = draft.text;
      _reply = draft.reply;
      _replyAuthor = draft.replyAuthor;
      _uploads.addAll(draft.files);
    }
    controller.addListener(_changed);
  }

  void _changed() => setState(() {});

  @override
  void dispose() {
    // An edit never stays behind as a draft; finished files and the reply do.
    final draft = _drafts.putIfAbsent(widget.threadId, _Draft.new)
      ..text = _editing == null ? controller.text : ''
      ..reply = _reply
      ..replyAuthor = _replyAuthor
      ..files = _uploads.where((u) => u.done).toList();
    if (draft.text.isEmpty && draft.reply == null && draft.files.isEmpty) {
      _drafts.remove(widget.threadId);
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
    focusNode.requestFocus();
  }

  /// «تعديل وإعادة الإرسال»: the next send replaces [message].
  void edit(Message message) {
    setState(() {
      _reply = null;
      _editing = message;
      controller.text = message.content;
    });
    focusNode.requestFocus();
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
      if (u.artifactId == null) u.error = 'request_failed';
      if (mounted) {
        if (u.artifactId != null) {
          context.dispatch(AddThreadArtifactAction(widget.threadId, data));
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
  }

  void _send(String text) {
    final editing = _editing != null;
    // An edit carries no files: uploads still running (or done) wait for the next send.
    if (!widget.enabled || (!editing && _uploading)) return;
    final l10n = context.l10n;
    final ready = _ready;
    final Json body;
    if (editing) {
      // An edit replaces the message with new text, never with files alone.
      if (text.isEmpty) return;
      body = {
        'content': text,
        'edited_from': _editing!.id,
        'attachment_ids': <String>[],
      };
    } else {
      if (text.isEmpty && ready.isEmpty) return;
      body = {
        'content': text.isEmpty ? l10n.t('attach') : text,
        'attachment_ids': [for (final u in ready) u.artifactId!],
        'reply_to': ?_reply?.id,
      };
    }
    context.dispatch(SendMessageAction(widget.threadId, body));
    controller.clear();
    setState(() {
      _reply = null;
      _replyAuthor = null;
      _editing = null;
      if (!editing) {
        for (final u in _uploads) {
          if (u.done || u.error != null) u.discard();
        }
        _uploads.removeWhere((u) => u.done || u.error != null);
      }
    });
    _drafts.remove(widget.threadId);
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

    Widget? replyBar;
    if (editing != null) {
      replyBar = ComposerReplyBar(
        icon: FIcons.pencil,
        title: l10n.t('editTheMessage'),
        text: plainLine(editing.content),
        closeLabel: l10n.t('cancelEdit'),
        onClose: () => setState(() {
          _editing = null;
          controller.clear();
        }),
      );
    } else if (reply != null) {
      // A plain quote: the bar's own quote mark says it is a reply.
      replyBar = ComposerReplyBar(
        text: plainLine(reply.content).isEmpty
            ? l10n.t('attachments')
            : plainLine(reply.content),
        closeLabel: l10n.t('cancelReply'),
        onClose: () => setState(() {
          _reply = null;
          _replyAuthor = null;
        }),
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
            thumbnail: u.image
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
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (suggestion != null &&
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
