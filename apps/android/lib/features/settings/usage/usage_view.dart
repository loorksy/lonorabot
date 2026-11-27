// The usage pages' body: overall (UsageScreen) or one agent (UsageDetailPage), built from
// the kit and the usage cards. Reads `GET /usage/series`, `/usage/rank` (and the share of the
// total for an agent), `/usage/summary` for the all-time totals, and exports
// `/usage/export.csv` through the share sheet. A view only: there is no cap.
import 'dart:async';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../../avatar/avatar.dart';
import '../../../core/api/api_error.dart';
import '../../../core/models/models.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../../state/actions/base.dart';
import '../../../state/app_state.dart';
import '../integrations/ext_common.dart';
import '../settings_common.dart';
import 'usage_data.dart';
import 'usage_widgets.dart';

/// Overall usage when [agentId] is null; one agent's usage (with its share) otherwise.
class UsageView extends StatefulWidget {
  const UsageView({super.key, this.agentId, this.agentName, this.onOpenAgent});

  final String? agentId;

  /// The ranked name of [agentId], for an agent the shell no longer lists (deleted or
  /// archived but still ranked).
  final String? agentName;

  /// Opens an agent's detail page from the «By agent» ranking, with its ranked name.
  final void Function(String agentId, String? agentName)? onOpenAgent;

  @override
  State<UsageView> createState() => _UsageViewState();
}

class _UsageViewState extends State<UsageView> {
  UsagePeriod _period = UsagePeriod.month;
  UsageSeries? _series;
  UsageRank? _rank;
  UsageSeries? _all;
  ({int input, int output, int cached})? _summary;
  Object? _error;
  bool _exporting = false;
  int _serial = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final mine = ++_serial;
    final period = _period;
    final agentId = widget.agentId;
    try {
      final results = await Future.wait<Object?>([
        fetchSeries(period, agentId: agentId),
        fetchRank(period, agentId: agentId),
        if (agentId != null) fetchSeries(period),
      ]);
      if (!mounted || mine != _serial) return;
      setState(() {
        _series = results[0]! as UsageSeries;
        _rank = results[1]! as UsageRank;
        _all = agentId == null ? null : results[2] as UsageSeries?;
        _error = null;
      });
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (!mounted || mine != _serial) return;
      // A failed refresh keeps the figures on screen and says so; a first read shows the
      // error state.
      if (_series != null && _rank != null) {
        showErrorToast(context, e);
      } else {
        setState(() => _error = e);
      }
      return;
    }
    if (agentId == null) unawaited(_loadSummary());
  }

  Future<void> _loadSummary() async {
    try {
      final summary = await fetchUsageSummary();
      if (mounted) setState(() => _summary = summary);
    } catch (_) {
      // The all-time totals are an extra; the dashboard stands without them.
    }
  }

  void _setPeriod(UsagePeriod period) {
    setState(() {
      _period = period;
      _series = null;
      _rank = null;
      _error = null;
    });
    unawaited(_load());
  }

  Future<void> _export() async {
    if (_exporting) return;
    setState(() => _exporting = true);
    try {
      final dir = await getTemporaryDirectory();
      final name = ['lonora-usage', _period.name, ?widget.agentId].join('-');
      final path = '${dir.path}${Platform.pathSeparator}$name.csv';
      await downloadUsageCsv(path, _period, agentId: widget.agentId);
      await SharePlus.instance.share(
        ShareParams(files: [XFile(path, mimeType: 'text/csv')]),
      );
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final agents = context.select((AppState s) => s.shell.agents);
    final series = _series;
    final rank = _rank;
    final children = <Widget>[
      Gutter(
        bottom: LnSpace.md,
        child: UsagePeriodSelector(period: _period, onChanged: _setPeriod),
      ),
    ];
    if (series == null || rank == null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.only(top: LnSpace.xs),
        children: [
          ...children,
          if (_error != null)
            ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 360),
              child: LoadFailure(error: _error!, onRetry: _load),
            )
          else
            const SettingsSkeleton(groups: [2, 3, 2]),
        ],
      );
    }
    final agentId = widget.agentId;
    final agent = agentId == null ? null : agents[agentId];
    if (agentId != null) {
      final name = agent?.name ?? widget.agentName;
      children.add(
        UsageHero(
          series: series,
          // An agent known by no name gets no lead (the Web's rule).
          lead: name == null
              ? null
              : _AgentLead(agent: agent, name: name, share: _share),
        ),
      );
    } else {
      children
        ..add(UsageHero(series: series))
        ..add(UsageMonthCard(series: series));
    }
    children
      ..add(UsageChartCard(key: ValueKey(_period), series: series))
      ..add(UsageKpis(totals: series.totals));
    final total = rank.totals.cost;
    final models = [
      for (final m in rank.models)
        (
          key: '${m.provider}/${m.model}',
          name: ltr(m.model ?? ''),
          value: m.figures.cost,
          agent: null,
          onTap: null,
        ),
    ];
    if (agentId == null) {
      children
        ..add(
          UsageRankCard(
            title: context.t('us_byAgent'),
            note: context.t('us_ofTotal'),
            total: total,
            rows: [
              for (final a in rank.agents)
                (
                  key: a.agentId ?? 'none',
                  name: isolate(a.agentName ?? 'Lonora'),
                  value: a.figures.cost,
                  agent: a.agentId == null ? null : agents[a.agentId],
                  onTap: a.agentId == null || widget.onOpenAgent == null
                      ? null
                      : () => widget.onOpenAgent!(a.agentId!, a.agentName),
                ),
            ],
          ),
        )
        ..add(
          UsageRankCard(
            title: context.t('us_byModel'),
            total: total,
            rows: models,
          ),
        );
    } else {
      children.add(
        UsageRankCard(
          title: context.t('us_breakdown'),
          total: total,
          rows: models,
        ),
      );
    }
    final summary = _summary;
    if (agentId == null && summary != null) {
      children.add(
        LnSection(
          title: context.t('us_allTime'),
          children: [
            LnListTile(
              icon: FIcons.arrowDownToLine,
              title: context.t('inputTokens'),
              value: isolate(usageCount(summary.input)),
            ),
            LnListTile(
              icon: FIcons.arrowUpFromLine,
              title: context.t('outputTokens'),
              value: isolate(usageCount(summary.output)),
            ),
            LnListTile(
              icon: FIcons.databaseZap,
              title: context.t('cachedTokens'),
              value: isolate(usageCount(summary.cached)),
            ),
          ],
        ),
      );
      children.add(const SectionGap());
    }
    children.add(
      Gutter(
        bottom: LnSpace.lg,
        child: BlockButton(
          label: context.t('us_exportCsv'),
          icon: FIcons.download,
          variant: BlockButtonVariant.secondary,
          loading: _exporting,
          onPressed: _exporting ? null : _export,
        ),
      ),
    );
    return LnRefresh(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.only(
          top: LnSpace.xs,
          bottom: LnSpace.xxl + MediaQuery.paddingOf(context).bottom,
        ),
        children: children,
      ),
    );
  }

  /// This agent's share of everyone's cost in the period, as a whole percent.
  int get _share {
    final mine = _series?.totals.cost ?? 0;
    final all = _all?.totals.cost ?? 0;
    return all > 0 ? (mine / all * 100).round() : 0;
  }
}

class _AgentLead extends StatelessWidget {
  const _AgentLead({
    required this.agent,
    required this.name,
    required this.share,
  });

  /// Null for an agent the shell no longer lists: its ranked [name] only.
  final Agent? agent;
  final String name;
  final int share;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final a = agent;
    return Row(
      children: [
        if (a != null) ...[
          LonoraAvatar(
            agentId: a.id,
            face: a.avatar,
            color: a.color,
            tradesOnItsOwn: a.tradesOnItsOwn,
            size: 40,
            animate: false,
          ),
          const SizedBox(width: LnSpace.sm),
        ],
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(isolate(name), style: ln.text.title.copyWith(color: c.fg)),
              if (a != null && a.title.isNotEmpty)
                Text(
                  a.title,
                  style: ln.text.footnote.copyWith(color: c.fgMuted),
                ),
            ],
          ),
        ),
        StatusChip(
          label: context.t('us_shareOfTotal', [ltr('$share%')]),
          kind: StatusChipKind.brand,
        ),
      ],
    );
  }
}
