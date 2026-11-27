// «يحتاج انتباهك» — the Attention circle's destination (apps/web shell/domain/UpdatesPages.tsx,
// apps/mobile components/attention-view.tsx): everything that needs the owner, across all agents,
// from the server's one projection (`GET /attention/view`). Rows are grouped by urgency (a
// decision waiting · service health · agent alerts) or by agent; an unseen row carries a dot.
// A tap marks the item seen (`POST /attention/seen`, as the Web does; a question waiting for an
// answer is read with its conversation instead) and opens its conversation, where the fixed card
// or the question stands. Opening decides nothing: no approval is made here.
//
// Composed from the kit: tab-root title, the kit's segmented control, chat-row geometry without
// dividers.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../../state/realtime.dart';
import '../chats/chat_text.dart' show listTime;
import '../market/market_kit.dart';
import '../settings/settings_common.dart'
    show LnRefresh, LoadFailure, showErrorToast;
import 'attention_actions.dart';

/// How rows are grouped.
enum AttentionGrouping { urgency, agent }

/// The urgency group of a view row kind (contracts attention.ts `AttentionViewKind`).
enum AttentionUrgency { decision, health, alert }

AttentionUrgency urgencyOf(String kind) => switch (kind) {
  'trade_approval' ||
  'settle_operation' ||
  'secret_request' ||
  'mandate_card' ||
  'owner_question' ||
  'task_review' => AttentionUrgency.decision,
  'broker_health' ||
  'background_health' ||
  'system_alert' => AttentionUrgency.health,
  _ => AttentionUrgency.alert,
};

/// Unseen first, then newest first.
int compareRows(Json a, Json b) {
  final seenA = a['seen'] == true, seenB = b['seen'] == true;
  if (seenA != seenB) return seenA ? 1 : -1;
  return asStr(b['created_at']).compareTo(asStr(a['created_at']));
}

/// Groups [rows] by [grouping], each group sorted by [compareRows]; urgency groups keep their
/// fixed order, agent groups go most recent first.
List<(String key, List<Json> rows)> groupRows(
  List<Json> rows,
  AttentionGrouping grouping,
) {
  final groups = <String, List<Json>>{};
  for (final r in rows) {
    final key = grouping == AttentionGrouping.urgency
        ? urgencyOf(asStr(r['kind'])).name
        : asStr(r['agent_id']);
    groups.putIfAbsent(key, () => []).add(r);
  }
  for (final g in groups.values) {
    g.sort(compareRows);
  }
  final keys = groups.keys.toList();
  if (grouping == AttentionGrouping.urgency) {
    keys.sort(
      (a, b) => AttentionUrgency.values
          .byName(a)
          .index
          .compareTo(AttentionUrgency.values.byName(b).index),
    );
  } else {
    String latest(String k) => groups[k]!
        .map((r) => asStr(r['created_at']))
        .reduce((x, y) => x.compareTo(y) > 0 ? x : y);
    keys.sort((a, b) => latest(b).compareTo(latest(a)));
  }
  return [for (final k in keys) (k, groups[k]!)];
}

class AttentionScreen extends StatefulWidget {
  const AttentionScreen({super.key});

  @override
  State<AttentionScreen> createState() => _AttentionScreenState();
}

class _AttentionScreenState extends State<AttentionScreen> {
  AttentionGrouping _grouping = AttentionGrouping.urgency;
  Object? _error;
  bool _loading = false;
  StreamSubscription<LonoraEvent>? _events;
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
    try {
      // Attention, owner-action and approval events already refresh the shell snapshot this
      // screen draws (RealtimeController); run events do not, and a run that starts waiting
      // for the owner's answer adds a question row.
      _events = realtime.events.listen((e) {
        if (e.kind != 'run.waiting_input') return;
        _debounce?.cancel();
        _debounce = Timer(const Duration(milliseconds: 400), _load);
      });
    } catch (_) {
      // No realtime controller (previews): the shell snapshot and pull-to-refresh keep it.
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    unawaited(_events?.cancel());
    super.dispose();
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() => _loading = true);
    final action = LoadAttentionAction();
    await context.dispatchAndWait(action);
    if (!mounted) return;
    setState(() {
      _loading = false;
      _error = action.error;
    });
  }

  Future<void> _open(Json row) async {
    final id = asStr(row['id']);
    final thread = asStr(row['thread_id']);
    if (row['kind'] != 'owner_question' && row['seen'] != true) {
      final mark = MarkAttentionSeenAction(id);
      unawaited(
        context.dispatchAndWait(mark).then((_) {
          final e = mark.error;
          if (e != null && mounted) showErrorToast(context, e);
        }),
      );
    }
    if (thread.isNotEmpty) context.go(Routes.thread(thread));
  }

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    final ln = context.ln;
    final c = ln.colors;
    final rows = context.select((AppState s) => s.shell.attentionView);
    final loaded = context.select((AppState s) => s.shell.loaded);
    final agents = context.select((AppState s) => s.shell.agents);
    final bottom = FloatingTabBar.occupiedHeight(context) + LnSpace.xl;

    final children = <Widget>[
      LargeTitleHeader(title: context.t('android_attention')),
      const SizedBox(height: LnSpace.xs),
    ];
    if (rows.isEmpty && _error != null) {
      children.addAll([
        const SizedBox(height: 80),
        LoadFailure(error: _error!, onRetry: _load),
      ]);
    } else if (rows.isEmpty && (!loaded || (_loading && _error == null))) {
      children.add(
        SkeletonRows(
          count: 5,
          animate: !(MediaQuery.maybeDisableAnimationsOf(context) ?? false),
          semanticLabel: context.t('sh_loading'),
        ),
      );
    } else if (rows.isEmpty) {
      children.addAll([
        const SizedBox(height: 120),
        EmptyState(
          icon: FIcons.circleCheck,
          title: context.t('attentionNothing'),
        ),
      ]);
    } else {
      children.add(
        Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: LnSpace.pageGutter,
          ),
          child: LnSegmented<AttentionGrouping>(
            segments: [
              LnSegment(
                value: AttentionGrouping.urgency,
                label: context.t('at_byUrgency'),
              ),
              LnSegment(
                value: AttentionGrouping.agent,
                label: context.t('at_byAgent'),
              ),
            ],
            selected: _grouping,
            onChanged: (g) {
              HapticFeedback.selectionClick();
              setState(() => _grouping = g);
            },
          ),
        ),
      );
      for (final (key, group) in groupRows(rows, _grouping)) {
        final title = _grouping == AttentionGrouping.urgency
            ? context.t(switch (AttentionUrgency.values.byName(key)) {
                AttentionUrgency.decision => 'at_decisions',
                AttentionUrgency.health => 'at_health',
                AttentionUrgency.alert => 'at_alerts',
              })
            : (agents[key]?.name ?? context.t('agentMissing'));
        children
          ..add(
            Padding(
              padding: const EdgeInsets.only(top: 24, bottom: 4),
              // At the rows' inset, over the avatars (the explore inset is for tiles).
              child: SectionHeader(
                title: title,
                padding: const EdgeInsetsDirectional.symmetric(
                  horizontal: LnSpace.listInset,
                ),
              ),
            ),
          )
          ..addAll([
            for (final r in group)
              AttentionRow(
                row: r,
                agent: agents[asStr(r['agent_id'])],
                showAgent: _grouping == AttentionGrouping.urgency,
                onTap: () => _open(r),
              ),
          ]);
      }
      children.add(const SizedBox(height: LnSpace.md));
      children.add(Footnote(context.t('at_openHint'), icon: FIcons.info));
    }

    return ColoredBox(
      color: c.bg,
      child: LnRefresh(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(bottom: bottom),
          children: children,
        ),
      ),
    );
  }
}

/// One attention item: the agent's avatar, what it is (Lonora's attention label, or the
/// waiting question), the agent's own summary, who and which market, when; a dot while unseen.
class AttentionRow extends StatelessWidget {
  const AttentionRow({
    super.key,
    required this.row,
    required this.agent,
    required this.onTap,
    this.showAgent = true,
  });

  final Json row;
  final Agent? agent;
  final VoidCallback onTap;
  final bool showAgent;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final code = asString(row['code']);
    final kind = asStr(row['kind']);
    final title = kind == 'owner_question' || code == null || code.isEmpty
        ? l10n.t('attentionOwnerQuestion')
        : attentionTitle(
            l10n,
            code,
            reason: asString(row['reason']),
            providerName: asString(row['provider_name']),
          );
    final summary = asString(row['summary'])?.trim();
    final seen = row['seen'] == true;
    final created = asDate(row['created_at']);
    final who = [
      if (showAgent && agent != null) isolate(agent!.name),
      if (asString(row['symbol']) case final s? when s.isNotEmpty) isolate(s),
      if (created != null) isolate(listTime(created, l10n.lang)),
    ].join(dotSeparator);
    final urgency = urgencyOf(kind);
    final a = agent;
    final avatar = a == null
        ? Container(
            width: LnSize.avatarList,
            height: LnSize.avatarList,
            decoration: BoxDecoration(color: c.fill2, shape: BoxShape.circle),
            child: Icon(FIcons.bell, size: 22, color: c.fgMuted),
          )
        : LonoraAvatar(
            agentId: a.id,
            face: a.avatar,
            color: a.color,
            tradesOnItsOwn: a.tradesOnItsOwn,
            state: urgency == AttentionUrgency.decision
                ? LonoraAvatarState.waiting
                : LonoraAvatarState.idle,
            size: LnSize.avatarList,
            animate: false,
          );
    return LnTappable(
      onTap: onTap,
      semanticLabel: [title, ?summary, who].join('. '),
      semanticHint: l10n.t('openConversation'),
      excludeChildSemantics: true,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: LnSize.listRow),
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.listInset,
            10,
            LnSpace.listInset,
            10,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox.square(dimension: LnSize.avatarList, child: avatar),
              const SizedBox(width: LnSpace.listTextGap),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: (seen ? ln.text.body : ln.text.title).copyWith(
                        color: c.fg,
                      ),
                    ),
                    if (summary != null && summary.isNotEmpty)
                      Text(
                        summary,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        textDirection: readingDirection(summary),
                        style: ln.text.caption.copyWith(color: c.fg),
                      ),
                    if (who.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          who,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: ln.text.footnote.copyWith(color: c.fgMuted),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: LnSpace.xs),
              SizedBox(
                width: 12,
                height: 24,
                child: seen
                    ? null
                    : Center(
                        child: DotBadge(
                          size: 9,
                          ring: false,
                          color: urgency == AttentionUrgency.decision
                              ? c.attention
                              : c.selection,
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
