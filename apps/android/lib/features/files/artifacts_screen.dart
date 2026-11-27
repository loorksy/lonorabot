// The files library (apps/mobile app/artifacts.tsx, apps/web shell/domain/FilesPages.tsx): every
// file of the owner's conversations and agents, newest first, as a list or a grid with type icons
// (image thumbnails), sizes, agents and dates; search, filters by type, by agent and by the
// conversation it was opened from; share, save, open elsewhere, delete (confirmed), upload and new
// text file. Composed from the kit.
import 'dart:async';
import 'dart:typed_data';

import 'package:async_redux/async_redux.dart' show StoreProvider;
import 'package:flutter/services.dart' show TextInputAction;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/api/api_error.dart';
import '../../core/models/models.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../../state/realtime.dart';
import '../market/market_kit.dart';
import '../settings/settings_common.dart' show LnRefresh, LoadFailure;
import 'file_ops.dart';
import 'files_data.dart';

class ArtifactsScreen extends StatefulWidget {
  const ArtifactsScreen({super.key, this.threadId, this.agentId});
  final String? threadId;

  /// Opened for one agent (its profile's Files row): the agent filter starts on it.
  final String? agentId;

  @override
  State<ArtifactsScreen> createState() => _ArtifactsScreenState();
}

class _ArtifactsScreenState extends State<ArtifactsScreen> {
  List<ArtifactRecord>? _items;
  Object? _error;

  /// The search text lives here: the field is rebuilt when the list and grid swap or its
  /// row scrolls out of the lazily built list.
  final _search = TextEditingController();
  String get _query => _search.text;
  FileFilter _filter = FileFilter.all;
  late String? _agent = widget.agentId;
  late bool _thisChat = widget.threadId != null;
  bool _grid = false;
  StreamSubscription<LonoraEvent>? _events;
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    try {
      _events = realtime.events.listen((e) {
        if (!e.kind.startsWith('artifacts.')) return;
        _debounce?.cancel();
        _debounce = Timer(const Duration(milliseconds: 500), _load);
      });
    } catch (_) {
      // No realtime controller (previews).
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    unawaited(_events?.cancel());
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final items = await fetchArtifacts(
        threadId: widget.threadId ?? _agentThread(),
        agentId: widget.agentId,
      );
      if (mounted) {
        setState(() {
          _items = items;
          _error = null;
        });
      }
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  /// Opened for an agent, its one-to-one conversation (what the profile's Files row opened
  /// before): that conversation's own files are read too, so older ones are never missing,
  /// and files added under the agent's filter go there.
  String? _agentThread() {
    final id = widget.agentId;
    if (id == null) return null;
    return StoreProvider.state<AppState>(context, notify: false).shell.inbox
        .where((e) => e.agentId == id && e.groupId == null)
        .firstOrNull
        ?.threadId;
  }

  /// The agent of each conversation the files belong to (its inbox row, else the loaded
  /// conversation). Selected as plain values, so the library rebuilds only when they change.
  static Map<String, String> _threadAgents(
    AppState s,
    Iterable<String> ids,
  ) => {
    for (final id in ids)
      id: ?(s.shell.entryFor(id)?.agentId ?? s.threads[id]?.thread?.agentId),
  };

  /// The opened conversation's name: its agent's, its group's or its own title.
  static String? _threadTitle(AppState s, String? thread) {
    if (thread == null) return null;
    final e = s.shell.entryFor(thread);
    final agent = e?.agentId == null ? null : s.shell.agents[e!.agentId];
    final group = e?.groupId == null ? null : s.shell.groups[e!.groupId];
    return agent?.name ?? group?.name ?? s.threads[thread]?.thread?.title;
  }

  /// The agent a file belongs to: its own, else its conversation's (apps/mobile artifacts.tsx).
  static String? _agentOf(ArtifactRecord r, Map<String, String> threadAgents) =>
      r.agentId ?? (r.threadId == null ? null : threadAgents[r.threadId]);

  List<ArtifactRecord> _visible(Map<String, String> threadAgents) {
    final needle = _query.trim().toLowerCase();
    return [
      for (final r in _items ?? const <ArtifactRecord>[])
        if ((!_thisChat || r.threadId == widget.threadId) &&
            matchesFilter(r.kind, _filter) &&
            (_agent == null || _agentOf(r, threadAgents) == _agent) &&
            (needle.isEmpty ||
                '${r.name} ${r.mediaType}'.toLowerCase().contains(needle)))
          r,
    ];
  }

  Future<void> _add() async {
    final l10n = context.l10n;
    final choice = await showLnActionMenu<String>(
      context,
      actions: [
        LnMenuAction(
          label: l10n.t('fl_upload'),
          icon: FIcons.upload,
          value: 'upload',
        ),
        LnMenuAction(
          label: l10n.t('fl_newText'),
          icon: FIcons.filePlus,
          value: 'text',
        ),
      ],
    );
    if (!mounted || choice == null) return;
    // Under the page's own agent, a new file is that agent's (also without a conversation), so
    // it stays in view.
    final agent = !_thisChat && _agent != null && _agent == widget.agentId
        ? _agent
        : null;
    final thread = _thisChat
        ? widget.threadId
        : agent != null
        ? _agentThread()
        : null;
    final created = choice == 'upload'
        ? await pickAndUpload(context, threadId: thread, agentId: agent)
        : await showTextEditor(context, threadId: thread, agentId: agent);
    if (created != null && mounted) {
      setState(() => _items = [created, ...?_items]);
    }
  }

  Future<void> _menu(ArtifactRecord r) async {
    final l10n = context.l10n;
    final action = await showLnActionMenu<String>(
      context,
      title: r.name,
      actions: [
        LnMenuAction(label: l10n.t('preview'), icon: FIcons.eye, value: 'open'),
        LnMenuAction(
          label: l10n.t('share'),
          icon: FIcons.share2,
          value: 'share',
        ),
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
        if (r.threadId != null && r.threadId != widget.threadId)
          LnMenuAction(
            label: l10n.t('openConversation'),
            icon: FIcons.messageCircle,
            value: 'thread',
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
      case 'open':
        _open(r);
      case 'share':
        await shareArtifact(context, r);
      case 'save':
        await saveArtifact(context, r);
      case 'elsewhere':
        await openArtifactElsewhere(context, r);
      case 'thread':
        context.go(Routes.thread(r.threadId!));
      case 'delete':
        if (await deleteArtifactConfirmed(context, r) && mounted) {
          setState(
            () => _items = [
              for (final x in _items ?? const <ArtifactRecord>[])
                if (x.id != r.id) x,
            ],
          );
        }
    }
  }

  void _open(ArtifactRecord r) => context.push(Routes.artifact(r.id));

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    final ln = context.ln;
    final c = ln.colors;
    final agents = context.select((AppState s) => s.shell.agents);
    final items = _items;
    final thread = widget.threadId;
    final threadIds = {
      for (final r in items ?? const <ArtifactRecord>[])
        if (r.agentId == null) ?r.threadId,
    };
    final threadAgents = context.select(
      (AppState s) => _threadAgents(s, threadIds),
    );
    final threadTitle = context.select((AppState s) => _threadTitle(s, thread));

    // The chosen agent keeps its chip even without files, so the filter can be cleared.
    final agentIds = <String>{
      for (final r in items ?? const <ArtifactRecord>[])
        ?_agentOf(r, threadAgents),
      ?_agent,
    };

    final header = <Widget>[
      Padding(
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: LnSpace.pageGutter,
        ),
        child: LnTextField(
          controller: _search,
          hint: context.t('artifactSearch'),
          prefix: const Icon(FIcons.search),
          textInputAction: TextInputAction.search,
          onChanged: (_) => setState(() {}),
        ),
      ),
      // The field's 48 dp touch band adds (48 - box) / 2 under its box: 4 dp for the 40 dp box
      // (English at 1.0), so the gap is 8 there; a taller box (Arabic, larger text) leaves 4-7.
      const SizedBox(height: LnSpace.xs - 4),
      LnChipStrip(
        children: [
          if (thread != null)
            LnChoiceChip(
              label: threadTitle == null
                  ? context.t('fl_thisChat')
                  : '${context.t('fl_thisChat')} · ${isolate(threadTitle)}',
              icon: FIcons.messageCircle,
              selected: _thisChat,
              onTap: () => setState(() => _thisChat = !_thisChat),
            ),
          for (final f in FileFilter.values)
            LnChoiceChip(
              label: context.t(switch (f) {
                FileFilter.all => 'sh_fAll',
                FileFilter.images => 'fl_images',
                FileFilter.documents => 'fl_documents',
                FileFilter.text => 'fl_text',
                FileFilter.data => 'fl_data',
                FileFilter.other => 'fl_other',
              }),
              selected: _filter == f,
              onTap: () => setState(() => _filter = f),
            ),
        ],
      ),
      if (agentIds.length > 1 || _agent != null)
        LnChipStrip(
          children: [
            for (final id in agentIds)
              if (agents[id] case final a?)
                LnChoiceChip(
                  label: a.name,
                  leading: LonoraAvatar(
                    agentId: a.id,
                    face: a.avatar,
                    color: a.color,
                    size: 20,
                    animate: false,
                  ),
                  selected: _agent == id,
                  onTap: () =>
                      setState(() => _agent = _agent == id ? null : id),
                ),
          ],
        ),
      const SizedBox(height: LnSpace.xs),
    ];

    Widget body;
    if (items == null && _error != null) {
      body = ListView(
        children: [
          ...header,
          const SizedBox(height: 60),
          LoadFailure(
            error: _error!,
            onRetry: () {
              setState(() => _error = null);
              unawaited(_load());
            },
          ),
        ],
      );
    } else if (items == null) {
      body = ListView(
        physics: const NeverScrollableScrollPhysics(),
        children: [
          ...header,
          SkeletonRows(
            count: 6,
            animate: !(MediaQuery.maybeDisableAnimationsOf(context) ?? false),
            semanticLabel: context.t('sh_loading'),
          ),
        ],
      );
    } else {
      final visible = _visible(threadAgents);
      // The conversation or agent scope the page was opened for is no search: empty, it
      // offers an upload (apps/mobile app/artifacts.tsx ListEmptyComponent).
      final filtered =
          _query.trim().isNotEmpty ||
          _filter != FileFilter.all ||
          (_agent != null && _agent != widget.agentId);
      final bottom = LnSpace.xxl + MediaQuery.paddingOf(context).bottom;
      if (visible.isEmpty) {
        body = ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            ...header,
            const SizedBox(height: 60),
            EmptyState(
              icon: filtered ? FIcons.searchX : FIcons.folderOpen,
              title: context.t(filtered ? 'noResults' : 'emptyArtifacts'),
              actionLabel: filtered ? null : context.t('fl_upload'),
              onAction: filtered ? null : _add,
            ),
          ],
        );
      } else if (_grid) {
        body = CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverList.list(children: header),
            SliverPadding(
              padding: EdgeInsetsDirectional.fromSTEB(
                LnSpace.pageGutter,
                LnSpace.xs,
                LnSpace.pageGutter,
                bottom,
              ),
              sliver: SliverGrid.builder(
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  mainAxisSpacing: LnSpace.tileGap,
                  crossAxisSpacing: LnSpace.tileGap,
                  childAspectRatio: 0.82,
                ),
                itemCount: visible.length,
                itemBuilder: (context, i) => FileTile(
                  record: visible[i],
                  meta: _meta(visible[i], agents, threadAgents),
                  onTap: () => _open(visible[i]),
                  onMenu: () => _menu(visible[i]),
                ),
              ),
            ),
          ],
        );
      } else {
        body = ListView.builder(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(bottom: bottom),
          itemCount: header.length + visible.length,
          itemBuilder: (context, i) => i < header.length
              ? header[i]
              : FileRow(
                  record: visible[i - header.length],
                  meta: _meta(visible[i - header.length], agents, threadAgents),
                  onTap: () => _open(visible[i - header.length]),
                  onMenu: () => _menu(visible[i - header.length]),
                ),
        );
      }
      body = LnRefresh(onRefresh: _load, child: body);
    }

    return PushedPage(
      title: context.t('artifacts'),
      subtitle: thread != null && _thisChat ? threadTitle : null,
      fallback: thread != null
          ? Routes.thread(thread)
          : widget.agentId != null
          ? Routes.agent(widget.agentId!)
          : Routes.me,
      trailing: [
        CircleIconButton(
          icon: Icon(_grid ? LnIcons.list : FIcons.layoutGrid),
          semanticLabel: context.t(_grid ? 'fl_list' : 'fl_grid'),
          onTap: () => setState(() => _grid = !_grid),
        ),
        CircleIconButton(
          icon: const Icon(FIcons.plus),
          semanticLabel: context.t('fl_add'),
          onTap: _add,
        ),
      ],
      body: ColoredBox(color: c.bg, child: body),
    );
  }

  /// «PDF · 2.4 KB · Agent · 27/11».
  String _meta(
    ArtifactRecord r,
    Map<String, Agent> agents,
    Map<String, String> threadAgents,
  ) {
    final lang = context.l10n.lang;
    final agent = agents[_agentOf(r, threadAgents)];
    final at = r.createdAt;
    return [
      mimeBadge(r.mediaType),
      isolate(formatFileSize(r.size, lang)),
      if (agent != null) isolate(agent.name),
      if (at != null) isolate(shortDate(at)),
    ].join(dotSeparator);
  }
}

/// The 40 dp type tile of a file: an image's thumbnail, else its type icon on a tinted fill.
class FileTypeIcon extends StatefulWidget {
  const FileTypeIcon({super.key, required this.record, this.size = 40});

  final ArtifactRecord record;
  final double size;

  @override
  State<FileTypeIcon> createState() => _FileTypeIconState();
}

class _FileTypeIconState extends State<FileTypeIcon> {
  Uint8List? _thumb;

  @override
  void initState() {
    super.initState();
    _maybeLoad();
  }

  @override
  void didUpdateWidget(FileTypeIcon old) {
    super.didUpdateWidget(old);
    if (old.record.id != widget.record.id) {
      _thumb = null;
      _maybeLoad();
    }
  }

  void _maybeLoad() {
    final r = widget.record;
    if (r.kind != FileKind.image || r.size > 8 * 1024 * 1024) return;
    unawaited(
      fetchArtifactBytes(r, preview: true).then((b) {
        if (mounted) setState(() => _thumb = b);
      }, onError: (_) {}),
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final kind = widget.record.kind;
    final tint = switch (kind) {
      FileKind.image => c.brand,
      FileKind.pdf => c.negative,
      FileKind.json || FileKind.csv => c.positive,
      FileKind.code || FileKind.html => c.selection,
      FileKind.markdown || FileKind.text => c.warning,
      FileKind.other => c.fgMuted,
    };
    final radius = BorderRadius.circular(widget.size * 0.25);
    final thumb = _thumb;
    return SizedBox.square(
      dimension: widget.size,
      child: thumb != null
          ? ClipRRect(
              borderRadius: radius,
              child: Image.memory(
                thumb,
                fit: BoxFit.cover,
                gaplessPlayback: true,
                // Decoded near the tile's size, not the photo's: twice its width, so a
                // landscape image still covers the square after its crop.
                cacheWidth:
                    (widget.size * 2 * MediaQuery.devicePixelRatioOf(context))
                        .round(),
                errorBuilder: (_, _, _) => const SizedBox.shrink(),
              ),
            )
          : DecoratedBox(
              decoration: BoxDecoration(
                color: tint.withValues(alpha: 0.14),
                borderRadius: radius,
              ),
              child: Icon(fileIcon(kind), size: widget.size * 0.5, color: tint),
            ),
    );
  }
}

/// A list row: type tile, name, «type · size · agent · date», a more button (long press too).
class FileRow extends StatelessWidget {
  const FileRow({
    super.key,
    required this.record,
    required this.meta,
    required this.onTap,
    required this.onMenu,
  });

  final ArtifactRecord record;
  final String meta;
  final VoidCallback onTap;
  final VoidCallback onMenu;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: onTap,
      onLongPress: onMenu,
      haptic: true,
      semanticLabel: '${record.name}. $meta',
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: LnSize.listRow),
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.listInset,
            8,
            LnSpace.listInset - 12,
            8,
          ),
          child: Row(
            children: [
              FileTypeIcon(record: record),
              const SizedBox(width: LnSpace.listTextGap),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      record.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textDirection: readingDirection(record.name),
                      style: ln.text.title.copyWith(color: c.fg),
                    ),
                    Text(
                      meta,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: ln.text.footnote.copyWith(color: c.fgMuted),
                    ),
                  ],
                ),
              ),
              LnTappable(
                onTap: onMenu,
                semanticLabel: context.t('more'),
                excludeChildSemantics: true,
                child: SizedBox.square(
                  dimension: 48,
                  child: Icon(
                    FIcons.ellipsisVertical,
                    size: 20,
                    color: c.fgMuted,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A grid card: a large preview (thumbnail or icon), the name and the meta line.
class FileTile extends StatelessWidget {
  const FileTile({
    super.key,
    required this.record,
    required this.meta,
    required this.onTap,
    required this.onMenu,
  });

  final ArtifactRecord record;
  final String meta;
  final VoidCallback onTap;
  final VoidCallback onMenu;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: onTap,
      onLongPress: onMenu,
      haptic: true,
      semanticLabel: '${record.name}. $meta',
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: c.fill1,
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.tile)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: LayoutBuilder(
                builder: (context, box) => Center(
                  child: FileTypeIcon(
                    record: record,
                    size: box.biggest.shortestSide,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 10),
            Text(
              record.name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textDirection: readingDirection(record.name),
              style: ln.text.captionStrong.copyWith(color: c.fg),
            ),
            Text(
              meta,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: ln.text.small.copyWith(color: c.fgMuted),
            ),
          ],
        ),
      ),
    );
  }
}
