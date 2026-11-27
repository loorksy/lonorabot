// Search (a field in the header slot over list rows): Lonora's unified search
// (apps/mobile/components/shell/unified-search.tsx). One engine, `GET /search`, owner-wide; tabs
// الكل · المحادثات · الرسائل · المهام · الملفات · المعرفة والمهارات; the field is debounced and
// only the latest query lands; an empty query browses what is recent. A message hit opens its own
// conversation at its place (`around=seq`). Search is a root page and a conversation lives in the
// chats tab (go_router cannot push a tab's page over a root page), so a chat or message hit
// replaces the search; the next search opens with that query and tab again, as the Expo app's Back
// returns to its results.
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import 'chat_commands.dart';
import 'chat_rows.dart';
import 'chat_text.dart';
import 'chat_widgets.dart';
import 'chats_strings.dart';
import 'search_feed.dart';

/// `GET /search` through the app's API client.
Future<Json> fetchSearchPage(
  String q,
  String? category,
  int limit,
  int offset,
) async => asJson(
  await api.get('/search', query: searchQuery(q, category, limit, offset)),
);

/// The query and tab a chat or message hit left the search with.
({String q, String tab})? _resume;

@visibleForTesting
void forgetSearchResume() => _resume = null;

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

typedef _Loaded = ({String key, List<SearchSection> sections, String? error});

class _SearchScreenState extends State<SearchScreen> {
  final _query = TextEditingController();
  final _focus = FocusNode();
  String _tab = 'all';
  _Loaded? _loaded;
  Timer? _debounce;
  int _generation = 0;
  bool _more = false;

  String get _q => _query.text.trim();
  String get _key => '$_tab|$_q';

  @override
  void initState() {
    super.initState();
    final resume = _resume;
    _resume = null;
    if (resume != null) {
      _query.text = resume.q;
      _tab = resume.tab;
    }
    _load();
  }

  /// A hit leaves the search for a conversation: the next search resumes here.
  void _leaving() => _resume = (q: _query.text, tab: _tab);

  @override
  void dispose() {
    _debounce?.cancel();
    _query.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _schedule() {
    _debounce?.cancel();
    setState(() {});
    _debounce = Timer(
      _q.isEmpty ? Duration.zero : const Duration(milliseconds: 160),
      _load,
    );
  }

  Future<void> _load() async {
    final q = _q;
    final tab = _tab;
    final key = _key;
    final generation = ++_generation;
    try {
      final sections = await firstSearchPage(q, tab, fetchSearchPage);
      if (!mounted || generation != _generation) return;
      setState(() => _loaded = (key: key, sections: sections, error: null));
    } on SessionRequestCancelled {
      return;
    } catch (error) {
      if (!mounted || generation != _generation) return;
      setState(
        () => _loaded = (
          key: key,
          sections: const [],
          error: error is ApiError ? error.code : 'request_failed',
        ),
      );
    }
  }

  void _setTab(String tab) {
    if (tab == _tab) return;
    HapticFeedback.selectionClick();
    _tab = tab;
    _schedule();
  }

  Future<void> _loadMore(SearchSection section) async {
    final loaded = _loaded;
    if (loaded == null || _more) return;
    setState(() => _more = true);
    try {
      final next = await moreSearchItems(_q, section, fetchSearchPage);
      if (!mounted || _loaded?.key != loaded.key) return;
      setState(
        () => _loaded = (
          key: loaded.key,
          sections: [
            for (final s in loaded.sections) s.tab == section.tab ? next : s,
          ],
          error: null,
        ),
      );
    } catch (_) {
      // The button stays for another try.
    } finally {
      if (mounted) setState(() => _more = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    registerChatsStrings();
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final shell = context.select((AppState s) => s.shell);
    final rows = chatRows(
      shell.orderedAgents,
      shell.groups.values,
      shell.inbox,
    );
    final top = MediaQuery.paddingOf(context).top;
    final header = Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter - 2,
        top + ScreenHeader.topGapDefault - 2,
        LnSpace.pageGutter,
        0,
      ),
      child: SizedBox(
        height: ScreenHeader.rowHeight,
        child: Row(
          children: [
            CircleIconButton(
              // Lucide's chevrons follow the text direction by themselves.
              icon: const Icon(FIcons.chevronLeft),
              semanticLabel: l10n.t('sh_closeSearch'),
              onTap: () => Navigator.of(context).maybePop(),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: SearchPill(
                controller: _query,
                focusNode: _focus,
                autofocus: true,
                hint: l10n.t('sh_searchPh'),
                onChanged: (_) => _schedule(),
                onClear: () {
                  _query.clear();
                  _schedule();
                },
              ),
            ),
          ],
        ),
      ),
    );

    final tabs = Semantics(
      container: true,
      label: l10n.t('sh_filterSearch'),
      child: SizedBox(
        height: 52,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: LnSpace.pageGutter,
            vertical: 2,
          ),
          children: [
            for (final tab in searchTabs)
              Padding(
                padding: const EdgeInsetsDirectional.only(end: 8),
                child: _Chip(
                  label: l10n.t(searchTabLabelKey(tab)),
                  active: _tab == tab,
                  onTap: () => _setTab(tab),
                ),
              ),
          ],
        ),
      ),
    );

    final loaded = _loaded;
    final q = _q;
    final List<Widget> body;
    if (loaded == null || loaded.key != _key) {
      body = [
        SkeletonRows(
          count: 5,
          animate: !(MediaQuery.maybeDisableAnimationsOf(context) ?? false),
          semanticLabel: context.t('sh_loading'),
        ),
      ];
    } else if (loaded.error != null) {
      body = [
        SizedBox(
          height: 320,
          child: ErrorState(
            title: l10n.errorText(loaded.error),
            retryLabel: l10n.t('sh_retry'),
            onRetry: _schedule,
          ),
        ),
      ];
    } else {
      final hasHistory = rows.any((r) => r.entry?.lastMessage != null);
      String title(String tab) => switch (tab) {
        'chats' =>
          q.isNotEmpty || !hasHistory
              ? l10n.t('sh_mAgentsGroups')
              : l10n.t('sh_mRecentChats'),
        'messages' =>
          q.isNotEmpty ? l10n.t('sh_mMatching') : l10n.t('sh_mRecentMessages'),
        _ => l10n.t(searchTabLabelKey(tab)),
      };
      final sections = loaded.sections
          .where((s) => s.items.isNotEmpty)
          .toList();
      body = [
        for (final section in sections)
          ...() {
            final limit = _tab == 'all'
                ? (q.isNotEmpty ? 3 : (section.tab == 'chats' ? 4 : 2))
                : section.items.length;
            final shown = section.items.take(limit).toList();
            final rest = _tab == 'all'
                ? section.count > limit
                : section.count > section.items.length;
            return <Widget>[
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(
                  LnSpace.listInset,
                  14,
                  LnSpace.listInset,
                  6,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Semantics(
                        header: true,
                        child: Text(
                          title(section.tab),
                          style: ln.text.captionStrong.copyWith(
                            color: c.fgMuted,
                          ),
                        ),
                      ),
                    ),
                    if (q.isNotEmpty || _tab != 'all')
                      Text(
                        '${section.count}',
                        style: ln.text.caption.copyWith(color: c.fgMuted),
                      ),
                  ],
                ),
              ),
              for (final hit in shown)
                _HitRow(
                  key: ValueKey('${hit.category}:${hit.id}'),
                  hit: hit,
                  query: q,
                  rows: rows,
                  agents: shell.agents,
                  onLeave: _leaving,
                ),
              if (rest)
                LnTappable(
                  onTap: _more
                      ? null
                      : () => _tab == 'all'
                            ? _setTab(section.tab)
                            : _loadMore(section),
                  child: SizedBox(
                    height: 48,
                    child: Center(
                      child: Text(
                        _tab == 'all'
                            ? (q.isNotEmpty
                                  ? l10n.t('sh_showAllN', [section.count])
                                  : l10n.t('sh_showAll'))
                            : l10n.t('sh_showMore'),
                        style: ln.text.captionStrong.copyWith(color: c.fg),
                      ),
                    ),
                  ),
                ),
            ];
          }(),
        if (sections.isEmpty)
          _EmptyBlock(
            title: q.isNotEmpty
                ? l10n.t(
                    _tab == 'all' ? 'sh_noResultsTitle' : 'sh_noResultsCat',
                  )
                : l10n.t('sh_emptySection'),
            body: q.isNotEmpty
                ? (_tab == 'all'
                      ? l10n.t('sh_noResultsFor', const [], {'q': q})
                      : l10n.t('sh_chooseAll'))
                : l10n.t(switch (_tab) {
                    'chats' => 'sh_noChatsAvail',
                    'messages' => 'sh_noMessagesSaved',
                    'tasks' => 'sh_noTasksSaved',
                    'files' => 'sh_noFilesAvail',
                    'other' => 'sh_noKnowledgeSaved',
                    _ => 'sh_browseEmpty',
                  }),
          ),
        if (q.isEmpty && _tab == 'all')
          Padding(
            padding: const EdgeInsetsDirectional.all(LnSpace.listInset),
            child: Row(
              children: [
                Icon(FIcons.search, size: 18, color: c.fgSubtle),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    l10n.t('sh_typeToSearch'),
                    style: ln.text.caption.copyWith(color: c.fgMuted),
                  ),
                ),
              ],
            ),
          ),
      ];
    }

    return ColoredBox(
      color: c.bg,
      child: Column(
        children: [
          header,
          const SizedBox(height: 4),
          tabs,
          Expanded(
            child: Semantics(
              label: l10n.t(
                q.isNotEmpty ? 'sh_searchResults' : 'sh_browseContent',
              ),
              container: true,
              child: ListView(
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.onDrag,
                // A root page without a Scaffold: the keyboard is not taken off by itself.
                padding: EdgeInsets.only(
                  bottom:
                      math.max(
                        MediaQuery.viewInsetsOf(context).bottom,
                        MediaQuery.viewPaddingOf(context).bottom,
                      ) +
                      24,
                ),
                children: body,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label, required this.active, required this.onTap});
  final String label;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: onTap,
      selected: active,
      semanticLabel: label,
      excludeChildSemantics: true,
      child: SizedBox(
        height: minTouchTarget,
        child: Center(
          child: AnimatedContainer(
            duration: LnMotion.fast,
            height: LnSize.chipHeight,
            padding: const EdgeInsets.symmetric(horizontal: 14),
            alignment: Alignment.center,
            decoration: ShapeDecoration(
              color: active ? c.fgStrong : c.fill2,
              shape: const StadiumBorder(),
            ),
            child: Text(
              label,
              maxLines: 1,
              style: ln.text.captionStrong.copyWith(
                color: active ? c.bg : c.fg,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _EmptyBlock extends StatelessWidget {
  const _EmptyBlock({required this.title, required this.body});
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 32),
    child: EmptyState(icon: FIcons.search, title: title, body: body),
  );
}

/// [text] with the folded [query]'s first match marked. The words read in their own direction
/// (punctuation stays with them) and keep the interface's alignment.
Widget _highlight(
  BuildContext context,
  String text,
  String query,
  TextStyle style,
) {
  final c = context.ln.colors;
  final ui = Directionality.of(context);
  final direction = textDirectionFor(text, ui);
  final align = ui == TextDirection.rtl ? TextAlign.right : TextAlign.left;
  final range = query.isEmpty ? null : highlightRange(text, query);
  if (range == null) {
    return Text(
      text,
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
      textDirection: direction,
      textAlign: align,
      style: style,
    );
  }
  return Text.rich(
    TextSpan(
      children: [
        TextSpan(text: text.substring(0, range.$1)),
        TextSpan(
          text: text.substring(range.$1, range.$2),
          style: TextStyle(
            color: c.fg,
            backgroundColor: c.brand.withValues(alpha: 0.3),
          ),
        ),
        TextSpan(text: text.substring(range.$2)),
      ],
    ),
    maxLines: 2,
    overflow: TextOverflow.ellipsis,
    textDirection: direction,
    textAlign: align,
    style: style,
  );
}

/// One hit and where it leads (unified-search.tsx:52-227).
class _HitRow extends StatelessWidget {
  const _HitRow({
    super.key,
    required this.hit,
    required this.query,
    required this.rows,
    required this.agents,
    required this.onLeave,
  });

  final SearchHit hit;
  final String query;
  final List<ChatRow> rows;
  final Map<String, Agent> agents;

  /// Called before a hit replaces the search with a conversation.
  final VoidCallback onLeave;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    String agentName(String? id) => agents[id]?.name ?? '';
    void gone() => LnToast.show(context, l10n.t('sh_resultGone'));
    Widget disc(IconData icon) => Container(
      width: LnSize.avatarList,
      height: LnSize.avatarList,
      decoration: BoxDecoration(color: c.fill2, shape: BoxShape.circle),
      child: Icon(icon, size: 20, color: c.fgMuted),
    );
    final titleStyle = ln.text.title.copyWith(color: c.fg);
    final subStyle = ln.text.caption.copyWith(color: c.fgMuted);
    final snippet = plainLine(hit.snippet);
    final Widget lead;
    final Widget title;
    Widget? sub;
    String? meta;
    final VoidCallback open;
    String label;
    switch (hit.category) {
      case 'chats':
        final row = rows
            .where(
              (r) =>
                  r.key ==
                  rowKey(
                    hit.kind == 'group' ? ChatRowKind.group : ChatRowKind.agent,
                    hit.id,
                  ),
            )
            .firstOrNull;
        final at = row?.entry?.lastMessage?.createdAt;
        lead = row != null
            ? ChatRowAvatar(row: row, agents: agents)
            : disc(hit.kind == 'group' ? FIcons.users : FIcons.bot);
        title = _highlight(context, hit.title, query, titleStyle);
        final text = snippet.isNotEmpty
            ? snippet
            : row == null
            ? ''
            : (row.agent != null ? agentRole(l10n, row.agent!) : row.subtitle);
        if (text.isNotEmpty) sub = _highlight(context, text, query, subStyle);
        meta = at == null ? null : listTime(at, l10n.lang);
        open = () {
          if (row == null) return gone();
          onLeave();
          openChatRow(context, row, replace: true);
        };
        label = [hit.title, text].join(', ');
      case 'messages':
        final owner = hit.threadAgentId;
        final row =
            rows.where((r) => r.threadId == hit.threadId).firstOrNull ??
            (hit.groupId == null && owner != null
                ? rows
                      .where((r) => r.key == rowKey(ChatRowKind.agent, owner))
                      .firstOrNull
                : null);
        final speaker = hit.role == 'user'
            ? l10n.t('sh_you')
            : (agentName(hit.agentId).isNotEmpty
                  ? agentName(hit.agentId)
                  : row?.name ?? '');
        lead = disc(FIcons.messageCircle);
        final head = '${row?.name ?? ''} · $speaker';
        title = Text(
          head,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: titleStyle,
        );
        sub = _highlight(context, snippet, query, subStyle);
        meta = hit.createdAt == null
            ? null
            : listTime(hit.createdAt!, l10n.lang);
        open = () {
          final thread = hit.threadId;
          final seq = hit.seq;
          if (row == null || seq == null || thread == null) return gone();
          onLeave();
          context.go(Routes.thread(thread, around: seq));
        };
        label = '$head, $snippet';
      case 'tasks':
        lead = disc(LnIcons.listTodo);
        title = _highlight(context, hit.title, query, titleStyle);
        sub = _highlight(context, snippet, query, subStyle);
        meta = agentName(hit.agentId);
        open = () => context.push(Routes.tasks);
        label = '${hit.title}, $snippet';
      case 'files':
        lead = disc(FIcons.file);
        title = _highlight(context, hit.title, query, titleStyle);
        sub = hit.snippet.isNotEmpty && hit.snippet != hit.title
            ? _highlight(context, snippet, query, subStyle)
            : Text(l10n.t('sh_savedFile'), style: subStyle);
        meta = agentName(hit.agentId);
        open = () => context.push(Routes.artifact(hit.id));
        label = hit.title;
      default:
        final skill = hit.category == 'skills';
        final kindLabel = l10n.t(skill ? 'sh_skill' : 'sh_knowledge');
        lead = disc(skill ? FIcons.cpu : FIcons.folder);
        title = Row(
          children: [
            Flexible(child: _highlight(context, hit.title, query, titleStyle)),
            Text(' · $kindLabel', style: subStyle),
          ],
        );
        sub = _highlight(context, snippet, query, subStyle);
        final owner = agentName(hit.agentId);
        meta = owner.isNotEmpty && owner != hit.title ? owner : null;
        open = () {
          if (skill) {
            context.push(Routes.integrations);
          } else if (hit.agentId != null) {
            context.push(Routes.agentSettings(hit.agentId!));
          } else {
            gone();
          }
        };
        label = '${hit.title}, $kindLabel, $snippet';
    }
    return LnTappable(
      onTap: open,
      semanticLabel: [label, ?meta].join(', '),
      excludeChildSemantics: true,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 64),
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: LnSpace.listInset,
            vertical: 10,
          ),
          child: Row(
            children: [
              SizedBox.square(
                dimension: LnSize.avatarList,
                child: Center(child: lead),
              ),
              const SizedBox(width: LnSpace.listTextGap),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [title, ?sub],
                ),
              ),
              if (meta != null && meta.isNotEmpty) ...[
                const SizedBox(width: 8),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 90),
                  child: Text(
                    meta,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: ln.text.caption.copyWith(color: c.fgMuted),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
