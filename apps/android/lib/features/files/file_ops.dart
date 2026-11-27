// What the owner does with a file: share it (share_plus), save it where they choose (the
// system's save dialog), open it in another app (open_filex), upload one, write or edit a text
// file, delete one (confirmed). The platform hand-offs sit behind [FileHandoff] so tests can
// replace them.
import 'dart:async';
import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show LengthLimitingTextInputFormatter;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:open_filex/open_filex.dart';
import 'package:share_plus/share_plus.dart';

import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../market/market_kit.dart';
import '../settings/settings_common.dart' show showErrorToast;
import 'files_data.dart';

/// A picked local file.
typedef PickedFile = ({String path, String name, String? mimeType});

/// Platform hand-offs (share sheet, save dialog, other apps, file picker).
abstract final class FileHandoff {
  static Future<void> Function(String path, String mimeType, String name)
  share = _share;
  static Future<Uri?> Function(String name, Uint8List bytes, String mimeType)
  save = _save;
  static Future<bool> Function(String path, String mimeType) open = _open;
  static Future<PickedFile?> Function() pick = _pick;

  @visibleForTesting
  static void reset() {
    share = _share;
    save = _save;
    open = _open;
    pick = _pick;
  }

  static Future<void> _share(String path, String mimeType, String name) async {
    await SharePlus.instance.share(
      ShareParams(
        files: [XFile(path, mimeType: mimeType, name: name)],
      ),
    );
  }

  static Future<Uri?> _save(String name, Uint8List bytes, String mimeType) =>
      FilePicker.saveFile(fileName: name, bytes: bytes, mimeType: mimeType);

  static Future<bool> _open(String path, String mimeType) async {
    final result = await OpenFilex.open(path, type: mimeType);
    return result.type == ResultType.done;
  }

  static Future<PickedFile?> _pick() async {
    final picked = await FilePicker.pickFiles();
    if (picked.isEmpty) return null;
    final f = picked.first;
    final path = f.path;
    if (path == null) return null;
    return (path: path, name: f.name, mimeType: null);
  }
}

Future<String> _cached(ArtifactRecord r) async =>
    cacheArtifact(r, await fetchArtifactBytes(r));

/// Shares the file through the system share sheet.
Future<void> shareArtifact(BuildContext context, ArtifactRecord r) async {
  try {
    final path = await _cached(r);
    await FileHandoff.share(path, r.mediaType, r.name);
  } catch (e) {
    if (context.mounted) showErrorToast(context, e);
  }
}

/// Saves the file where the owner chooses (the system's save dialog).
Future<void> saveArtifact(BuildContext context, ArtifactRecord r) async {
  try {
    final bytes = await fetchArtifactBytes(r);
    final uri = await FileHandoff.save(r.name, bytes, r.mediaType);
    if (uri != null && context.mounted) {
      LnToast.show(context, context.t('fl_saved'), kind: LnToastKind.positive);
    }
  } catch (e) {
    if (context.mounted) showErrorToast(context, e);
  }
}

/// Opens the file in another app (document viewer, spreadsheet…).
Future<void> openArtifactElsewhere(
  BuildContext context,
  ArtifactRecord r,
) async {
  try {
    final path = await _cached(r);
    final opened = await FileHandoff.open(path, r.mediaType);
    if (!opened && context.mounted) {
      LnToast.show(context, context.t('fl_noOpener'), kind: LnToastKind.notice);
    }
  } catch (e) {
    if (context.mounted) showErrorToast(context, e);
  }
}

/// Deletes the file after the owner confirms; true when it is gone.
Future<bool> deleteArtifactConfirmed(
  BuildContext context,
  ArtifactRecord r,
) async {
  final ok = await showLnConfirm(
    context,
    title: context.t('fl_confirmDelete'),
    message: context.t('fl_deleteQ'),
    confirmLabel: context.t('delete'),
    cancelLabel: context.t('sh_cancel'),
    destructive: true,
  );
  if (!ok || !context.mounted) return false;
  try {
    await deleteArtifact(r.id);
    if (context.mounted) {
      LnToast.show(
        context,
        context.t('fl_deleted'),
        kind: LnToastKind.positive,
      );
    }
    return true;
  } catch (e) {
    if (context.mounted) showErrorToast(context, e);
    return false;
  }
}

/// Picks a local file and uploads it (filed under [threadId], stored as [agentId]'s file, when
/// given).
Future<ArtifactRecord?> pickAndUpload(
  BuildContext context, {
  String? threadId,
  String? agentId,
}) async {
  try {
    final picked = await FileHandoff.pick();
    if (picked == null) return null;
    final created = await uploadArtifact(
      path: picked.path,
      name: picked.name,
      mimeType: picked.mimeType,
      threadId: threadId,
      agentId: agentId,
    );
    if (context.mounted) {
      LnToast.show(
        context,
        context.t('fl_uploaded'),
        kind: LnToastKind.positive,
      );
    }
    return created;
  } catch (e) {
    if (context.mounted) showErrorToast(context, e);
    return null;
  }
}

/// Writes a new text file, or edits [record] whose text is [content]. Completes with the saved
/// record (null when dismissed).
Future<ArtifactRecord?> showTextEditor(
  BuildContext context, {
  ArtifactRecord? record,
  String content = '',
  String? threadId,
  String? agentId,
}) => showLnSheet<ArtifactRecord>(
  context,
  title: context.t(record == null ? 'fl_newText' : 'fl_editText'),
  maxHeightFraction: 0.94,
  builder: (_) => TextFileEditor(
    record: record,
    content: content,
    threadId: threadId,
    agentId: agentId,
  ),
);

class TextFileEditor extends StatefulWidget {
  const TextFileEditor({
    super.key,
    this.record,
    this.content = '',
    this.threadId,
    this.agentId,
  });

  final ArtifactRecord? record;
  final String content;
  final String? threadId;
  final String? agentId;

  @override
  State<TextFileEditor> createState() => _TextFileEditorState();
}

class _TextFileEditorState extends State<TextFileEditor> {
  late final _name = TextEditingController(text: widget.record?.name);
  late final _content = TextEditingController(text: widget.content);
  bool _busy = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_name.text.isEmpty) _name.text = context.t('fl_defaultName');
  }

  @override
  void dispose() {
    _name.dispose();
    _content.dispose();
    super.dispose();
  }

  /// A name the server takes: 1–160 characters (apps/web FilesPages.tsx `maxLength`).
  bool get _nameValid {
    final name = _name.text.trim();
    return name.isNotEmpty && name.length <= 160;
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    final content = _content.text;
    if (!_nameValid || _busy) return;
    if (utf8.encode(content).length > maxTextBytes) {
      LnToast.show(context, context.t('fl_tooLarge'), kind: LnToastKind.notice);
      return;
    }
    setState(() => _busy = true);
    try {
      final record = widget.record;
      final saved = record == null
          ? await createTextArtifact(
              name: name,
              content: content,
              threadId: widget.threadId,
              agentId: widget.agentId,
            )
          : await saveArtifactText(record, name: name, content: content);
      if (mounted) Navigator.of(context).pop(saved);
    } catch (e) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, e);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Flexible(
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                LnTextField(
                  controller: _name,
                  label: context.t('fl_fileName'),
                  prefix: const Icon(FIcons.fileText),
                  inputFormatters: [LengthLimitingTextInputFormatter(160)],
                  onChanged: (_) => setState(() {}),
                ),
                const SizedBox(height: 12),
                LnTextField(
                  controller: _content,
                  label: context.t('fl_content'),
                  minLines: 8,
                  maxLines: 16,
                  keyboardType: TextInputType.multiline,
                ),
                const SizedBox(height: 16),
              ],
            ),
          ),
        ),
        BlockButton(
          label: context.t('fl_saveFile'),
          loading: _busy,
          onPressed: _nameValid ? _save : null,
        ),
      ],
    );
  }
}
