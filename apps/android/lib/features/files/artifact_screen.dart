// One file (apps/mobile app/artifact.tsx, lib/artifacts.ts; apps/web FilesPages.tsx): its type,
// size, agent and date, then a preview by kind — an image (tap for the zoomable viewer),
// Markdown (the rich renderer), JSON (indented, highlighted), CSV (a table), code (highlighted),
// HTML (as safe source, never rendered), plain text (selectable, first MiB) — or, for PDF and
// other types, open it in another app. Share, save, edit (text files), delete (confirmed) and
// open its conversation. Composed from the kit.
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart' show SelectableText;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../../state/realtime.dart';
import '../market/market_kit.dart';
import '../rich/code_block.dart' show CodeBlockView, codeTextStyle;
import '../rich/markdown_view.dart';
import '../settings/settings_common.dart' show LoadFailure;
import 'file_name_title.dart';
import 'file_ops.dart';
import 'files_data.dart';

class ArtifactScreen extends StatefulWidget {
  const ArtifactScreen({super.key, required this.artifactId});
  final String artifactId;

  @override
  State<ArtifactScreen> createState() => _ArtifactScreenState();
}

class _ArtifactScreenState extends State<ArtifactScreen> {
  ArtifactRecord? _record;
  Uint8List? _bytes;
  Object? _error;
  bool _loadingBytes = false;
  StreamSubscription<LonoraEvent>? _events;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    try {
      _events = realtime.events.listen((e) {
        if (e.kind == 'artifacts.updated' &&
            e.payload['id'] == widget.artifactId) {
          unawaited(_load());
        }
      });
    } catch (_) {
      // No realtime controller (previews).
    }
  }

  @override
  void dispose() {
    unawaited(_events?.cancel());
    super.dispose();
  }

  bool _previewable(ArtifactRecord r) =>
      r.kind != FileKind.pdf &&
      r.kind != FileKind.other &&
      r.size <= previewLimitBytes;

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final record = await fetchArtifact(widget.artifactId);
      if (!mounted) return;
      setState(() {
        _record = record;
        _loadingBytes = _previewable(record);
        if (!_loadingBytes) _bytes = null;
      });
      if (_loadingBytes) {
        final bytes = await fetchArtifactBytes(
          record,
          preview: record.kind == FileKind.image,
        );
        if (mounted) {
          setState(() {
            _bytes = bytes;
            _loadingBytes = false;
          });
        }
      }
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e;
          _loadingBytes = false;
        });
      }
    }
  }

  Future<void> _menu(ArtifactRecord r) async {
    final l10n = context.l10n;
    final text = isTextKind(r.kind) && _bytes != null;
    final action = await showLnActionMenu<String>(
      context,
      title: r.name,
      actions: [
        LnMenuAction(
          label: l10n.t('download'),
          icon: FIcons.download,
          value: 'save',
        ),
        LnMenuAction(
          label: l10n.t('fl_openWith'),
          icon: FIcons.externalLink,
          value: 'elsewhere',
        ),
        if (text)
          LnMenuAction(
            label: l10n.t('edit'),
            icon: FIcons.pencil,
            value: 'edit',
          ),
        LnMenuAction(
          label: l10n.t('delete'),
          icon: FIcons.trash2,
          value: 'delete',
          destructive: true,
        ),
      ],
    );
    if (!mounted || action == null) return;
    switch (action) {
      case 'save':
        await saveArtifact(context, r);
      case 'elsewhere':
        await openArtifactElsewhere(context, r);
      case 'edit':
        final edited = await showTextEditor(
          context,
          record: r,
          content: previewText(_bytes!).text,
        );
        if (edited != null && mounted) unawaited(_load());
      case 'delete':
        if (await deleteArtifactConfirmed(context, r) && mounted) {
          leaveTo(context, Routes.artifacts());
        }
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    final r = _record;
    final agents = context.select((AppState s) => s.shell.agents);
    final Widget body;
    if (r == null && _error != null) {
      body = Center(
        child: LoadFailure(error: _error!, onRetry: _load),
      );
    } else if (r == null) {
      body = const Center(child: LnSpinner(size: 28));
    } else {
      body = _content(r, agents[r.agentId]?.name);
    }
    final ln = context.ln;
    return PushedPage(
      title: r?.name ?? context.t('artifacts'),
      // One circle at the start and two at the end, each in a 48 dp button box: the name keeps
      // its extension and the same 16 dp from them at both ends (as in the image viewer).
      titleWidget: r == null
          ? null
          : FileNameTitle(
              name: r.name,
              start: LnSize.minTouch + LnSpace.md,
              end: 2 * LnSize.minTouch + LnSpace.md,
              style: ln.text.headline.copyWith(color: ln.colors.fg),
            ),
      fallback: Routes.artifacts(),
      trailing: [
        if (r != null) ...[
          CircleIconButton(
            icon: const Icon(FIcons.share2),
            semanticLabel: context.t('share'),
            onTap: () => shareArtifact(context, r),
          ),
          CircleIconButton(
            icon: const Icon(FIcons.ellipsisVertical),
            semanticLabel: context.t('more'),
            onTap: () => _menu(r),
          ),
        ],
      ],
      body: body,
    );
  }

  Widget _content(ArtifactRecord r, String? agentName) {
    final ln = context.ln;
    final c = ln.colors;
    final lang = context.l10n.lang;
    final at = r.createdAt;
    final meta = [
      r.mediaType,
      isolate(formatFileSize(r.size, lang)),
      if (agentName != null) isolate(agentName),
      if (at != null) isolate(shortDate(at, lang: context.l10n.lang)),
    ].join(dotSeparator);
    const gutter = EdgeInsetsDirectional.symmetric(
      horizontal: LnSpace.pageGutter,
    );
    final children = <Widget>[
      Padding(
        padding: gutter,
        child: Row(
          children: [
            FileTypeIconLite(kind: r.kind),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                meta,
                maxLines: 2,
                style: ln.text.footnote.copyWith(color: c.fgMuted),
              ),
            ),
          ],
        ),
      ),
      const SizedBox(height: LnSpace.md),
    ];

    final bytes = _bytes;
    if (_error != null && bytes == null && _previewable(r)) {
      children.add(LoadFailure(error: _error!, onRetry: _load));
    } else if (_loadingBytes) {
      children.add(
        const Padding(
          padding: EdgeInsets.all(48),
          child: Center(child: LnSpinner(size: 24)),
        ),
      );
    } else if (bytes != null && r.kind == FileKind.image) {
      children.add(
        Padding(
          padding: gutter,
          child: LnTappable(
            onTap: () => context.push(Routes.image(r.id)),
            semanticLabel: '${context.t('image')}: ${r.name}',
            excludeChildSemantics: true,
            pressOpacity: 0.8,
            child: Container(
              constraints: const BoxConstraints(maxHeight: 520),
              decoration: BoxDecoration(
                color: c.fill1,
                borderRadius: const BorderRadius.all(
                  Radius.circular(LnRadius.image),
                ),
              ),
              clipBehavior: Clip.antiAlias,
              child: Image.memory(
                bytes,
                fit: BoxFit.contain,
                errorBuilder: (_, _, _) => Padding(
                  padding: const EdgeInsets.all(32),
                  child: EmptyState(
                    icon: FIcons.imageOff,
                    title: context.t('noImage'),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    } else if (bytes != null) {
      final preview = previewText(bytes);
      children.addAll(_textPreview(r, preview.text));
      if (preview.truncated) {
        children.add(
          Footnote(context.t('previewTruncated'), icon: FIcons.info),
        );
      }
    } else {
      children.add(
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 8),
          child: EmptyState(
            icon: fileIcon(r.kind),
            title: r.name,
            body: context.t('unsupportedPreview'),
          ),
        ),
      );
      children.add(
        Padding(
          padding: gutter,
          child: BlockButton(
            label: context.t('fl_openWith'),
            icon: FIcons.externalLink,
            onPressed: () => openArtifactElsewhere(context, r),
          ),
        ),
      );
      children.add(const SizedBox(height: LnSpace.xs));
      children.add(
        Padding(
          padding: gutter,
          child: BlockButton(
            label: context.t('download'),
            icon: FIcons.download,
            variant: BlockButtonVariant.secondary,
            onPressed: () => saveArtifact(context, r),
          ),
        ),
      );
    }

    if (r.threadId != null) {
      children
        ..add(const SizedBox(height: LnSpace.lg))
        ..add(
          Padding(
            padding: gutter,
            child: BlockButton(
              label: context.t('openConversation'),
              icon: FIcons.messageCircle,
              variant: BlockButtonVariant.secondary,
              onPressed: () => context.go(Routes.thread(r.threadId!)),
            ),
          ),
        );
    }
    return ListView(
      padding: EdgeInsets.only(
        bottom: LnSpace.xxl + MediaQuery.paddingOf(context).bottom,
      ),
      children: children,
    );
  }

  List<Widget> _textPreview(ArtifactRecord r, String text) {
    final ln = context.ln;
    final c = ln.colors;
    const gutter = EdgeInsetsDirectional.symmetric(
      horizontal: LnSpace.pageGutter,
    );
    switch (r.kind) {
      case FileKind.markdown:
        return [Padding(padding: gutter, child: MarkdownView(text))];
      case FileKind.json:
        return [
          Padding(
            padding: gutter,
            child: CodeBlockView(code: prettyJson(text), language: 'json'),
          ),
        ];
      case FileKind.csv:
        return [CsvTable(rows: parseCsv(text))];
      case FileKind.code:
        return [
          Padding(
            padding: gutter,
            child: CodeBlockView(
              code: text,
              language: codeLanguage(r.name) ?? '',
            ),
          ),
        ];
      case FileKind.html:
        return [
          Footnote(context.t('nativeHtmlPreview'), icon: FIcons.shieldCheck),
          const SizedBox(height: LnSpace.xs),
          Padding(
            padding: gutter,
            child: CodeBlockView(code: text, language: 'xml'),
          ),
        ];
      default:
        return [
          Padding(
            padding: gutter,
            child: Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: c.fill1,
                borderRadius: const BorderRadius.all(
                  Radius.circular(LnRadius.card),
                ),
              ),
              child: SelectableText(
                text,
                textDirection: readingDirection(text),
                style: codeTextStyle(
                  ln.text.body,
                  size: 14,
                  height: 22,
                ).copyWith(color: c.fg),
              ),
            ),
          ),
        ];
    }
  }
}

/// The small type mark beside the meta line.
class FileTypeIconLite extends StatelessWidget {
  const FileTypeIconLite({super.key, required this.kind});
  final FileKind kind;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    return Container(
      width: 28,
      height: 28,
      decoration: BoxDecoration(
        color: c.fill2,
        borderRadius: const BorderRadius.all(
          Radius.circular(LnRadius.iconTile),
        ),
      ),
      child: Icon(fileIcon(kind), size: 16, color: c.fgMuted),
    );
  }
}

/// A CSV file as a table: the first row as the header, horizontal scroll, numbers left to
/// right, at most the rows [parseCsv] returned.
class CsvTable extends StatelessWidget {
  const CsvTable({super.key, required this.rows});

  final List<List<String>> rows;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    if (rows.isEmpty) {
      return Footnote(context.t('sh_listUnitEmpty'));
    }
    final width = rows.fold<int>(0, (m, r) => r.length > m ? r.length : m);
    Widget cell(String text, {bool head = false}) => Container(
      constraints: const BoxConstraints(minWidth: 72, maxWidth: 220),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Text(
        text,
        maxLines: 3,
        overflow: TextOverflow.ellipsis,
        textDirection: readingDirection(text),
        style: (head ? ln.text.footnoteStrong : ln.text.footnote).copyWith(
          color: c.fg,
        ),
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: LnSpace.pageGutter,
          ),
          child: Container(
            decoration: BoxDecoration(
              border: Border.all(color: c.border),
              borderRadius: const BorderRadius.all(Radius.circular(16)),
            ),
            clipBehavior: Clip.antiAlias,
            child: Table(
              defaultColumnWidth: const IntrinsicColumnWidth(),
              border: TableBorder.symmetric(
                inside: BorderSide(color: c.border),
              ),
              children: [
                for (final (i, row) in rows.indexed)
                  TableRow(
                    decoration: BoxDecoration(color: i == 0 ? c.fill2 : null),
                    children: [
                      for (var j = 0; j < width; j++)
                        cell(j < row.length ? row[j] : '', head: i == 0),
                    ],
                  ),
              ],
            ),
          ),
        ),
        if (rows.length >= 500)
          Footnote(context.t('fl_firstRows', ['${rows.length}'])),
      ],
    );
  }
}
