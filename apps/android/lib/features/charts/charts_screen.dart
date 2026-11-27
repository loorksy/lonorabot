// Lonora's persistent market charts (apps/mobile app/charts.tsx, components/candlestick-chart.tsx):
// the charts of a conversation or an agent as chips «SYMBOL · TF», the stored scene drawn natively
// (candles, indicator overlays and panes, every drawing kind, notes), its quote, a refresh request,
// live updates (`cloud_charts.scene_updated`) and chart creation (account, exact broker symbol —
// never auto-picked — and one of the 21 MT5 intervals). Interactions: a crosshair that reads one
// candle and a range selector. Composed from the kit.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../core/broker_identity.dart';
import '../../core/models/models.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/app_state.dart';
import '../../state/realtime.dart';
import '../market/market_data.dart';
import '../market/market_kit.dart';
import '../market/market_widgets.dart' show FactRow, FactsCard;
import '../settings/settings_common.dart'
    show ChoiceTile, LnRefresh, LoadFailure, errorMessage, showErrorToast;
import 'candle_chart.dart';
import 'charts_data.dart';

class ChartsScreen extends StatefulWidget {
  const ChartsScreen({super.key, this.threadId, this.agentId, this.chartId});
  final String? threadId;
  final String? agentId;
  final String? chartId;

  /// How often the open scene and the list are read again while in front (the Expo app polls
  /// every 5 s; events make most reads immediate).
  static const sceneEvery = Duration(seconds: 5);

  @override
  State<ChartsScreen> createState() => _ChartsScreenState();
}

const _ranges = [30, 60, 120, 0];

class _ChartsScreenState extends State<ChartsScreen>
    with WidgetsBindingObserver {
  List<ChartRow>? _charts;
  Object? _listError;
  String? _selected;
  ChartScene? _scene;
  Object? _sceneError;
  bool _requesting = false;
  int _range = 60;
  int? _cursor;
  bool _foreground = true;
  bool _sceneBusy = false;
  bool _sceneDirty = false;
  Timer? _timer;
  int _ticks = 0;
  StreamSubscription<LonoraEvent>? _events;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_loadList());
    _timer = Timer.periodic(ChartsScreen.sceneEvery, (_) {
      if (!_foreground || !mounted) return;
      if (!TickerMode.getValuesNotifier(context).value.enabled) return;
      _ticks++;
      unawaited(_loadScene());
      if (_ticks % 3 == 0) unawaited(_loadList());
    });
    try {
      _events = realtime.events.listen(_onEvent);
    } catch (_) {
      // No realtime controller (previews): the timer keeps the scene fresh.
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    unawaited(_events?.cancel());
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final front = state == AppLifecycleState.resumed;
    if (front && !_foreground) unawaited(_loadScene());
    _foreground = front;
  }

  void _onEvent(LonoraEvent e) {
    if (e.kind == 'cloud_charts.scene_updated') {
      if (e.payload['id'] == _selected) unawaited(_loadScene());
    } else if (e.kind.startsWith('cloud_charts.')) {
      unawaited(_loadList());
    }
  }

  Agent? get _agent {
    final id = widget.agentId;
    if (id == null) return null;
    return StoreProvider.state<AppState>(context).shell.agents[id];
  }

  /// The agent's own market only, when it is bound to one (apps/mobile app/charts.tsx load).
  List<ChartRow> _filter(List<ChartRow> all) {
    final agent = _agent;
    final account = agent?.tradingAccountId;
    if (agent == null || account == null || account.isEmpty) return all;
    return [
      for (final r in all)
        if (r.accountId == account &&
            r.symbol == agent.tradingSymbol &&
            (r.agentId == null || r.agentId == agent.id))
          r,
    ];
  }

  Future<void> _loadList() async {
    try {
      final rows = _filter(await fetchCharts(threadId: widget.threadId));
      if (!mounted) return;
      final keep = rows.any((r) => r.id == _selected);
      final next = keep
          ? _selected
          : (rows.where((r) => r.id == widget.chartId).firstOrNull ??
                    rows.firstOrNull)
                ?.id;
      setState(() {
        _charts = rows;
        _listError = null;
      });
      if (next != _selected) _select(next);
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted) setState(() => _listError = e);
    }
  }

  void _select(String? id) {
    setState(() {
      _selected = id;
      _scene = null;
      _sceneError = null;
      _cursor = null;
    });
    unawaited(_loadScene());
  }

  /// Reads the selected scene; a read asked while one runs is done right after it.
  Future<void> _loadScene() async {
    final id = _selected;
    if (id == null) return;
    if (_sceneBusy) {
      _sceneDirty = true;
      return;
    }
    _sceneBusy = true;
    _sceneDirty = false;
    try {
      final scene = await fetchScene(id);
      if (!mounted || id != _selected) return;
      setState(() {
        final old = _scene;
        if (old == null || old.acceptsUpdate(scene)) _scene = scene;
        _sceneError = null;
        if (_scene!.candles.length <= 30 && _range != 0) _range = 0;
      });
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted && id == _selected) setState(() => _sceneError = e);
    } finally {
      _sceneBusy = false;
      if (_sceneDirty && mounted) unawaited(_loadScene());
    }
  }

  Future<void> _refreshAll() async {
    await _loadList();
    await _loadScene();
  }

  Future<void> _requestRefresh() async {
    final id = _selected;
    if (id == null || _requesting) return;
    setState(() => _requesting = true);
    try {
      await requestChartRefresh(id);
      if (mounted) {
        LnToast.show(context, context.t('ch_refreshRequested'));
      }
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _requesting = false);
    }
  }

  Future<void> _create() async {
    final agent = _agent;
    final created = await showLnSheet<ChartRow>(
      context,
      title: context.t('createChart'),
      maxHeightFraction: 0.94,
      builder: (_) => CreateChartSheet(
        agentId: widget.agentId,
        threadId: widget.threadId,
        lockedAccount: agent?.tradingAccountId,
        lockedSymbol: agent?.tradingSymbol,
      ),
    );
    if (created == null || !mounted) return;
    await _loadList();
    if (mounted) _select(created.id);
  }

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    final charts = _charts;
    final Widget body;
    if (charts == null && _listError != null) {
      body = LoadFailure(
        error: _listError!,
        onRetry: () {
          setState(() => _listError = null);
          unawaited(_loadList());
        },
      );
    } else if (charts == null) {
      body = const Center(child: LnSpinner(size: 28));
    } else if (charts.isEmpty) {
      body = LnRefresh(
        onRefresh: _refreshAll,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            const SizedBox(height: 120),
            EmptyState(
              icon: FIcons.chartCandlestick,
              title: context.t('chartEmpty'),
              actionLabel: context.t('createChart'),
              onAction: _create,
            ),
          ],
        ),
      );
    } else {
      body = LnRefresh(onRefresh: _refreshAll, child: _content(charts));
    }
    return PushedPage(
      title: context.t('charts'),
      fallback: Routes.market,
      trailing: [
        CircleIconButton(
          icon: const Icon(FIcons.plus),
          semanticLabel: context.t('createChart'),
          onTap: _create,
        ),
      ],
      body: body,
    );
  }

  Widget _content(List<ChartRow> charts) {
    final ln = context.ln;
    final c = ln.colors;
    final current = charts.where((r) => r.id == _selected).firstOrNull;
    final scene = _scene;
    final children = <Widget>[
      LnChipStrip(
        children: [
          for (final r in charts)
            LnChoiceChip(
              label: '${r.symbol} · ${r.timeframe}',
              textDirection: TextDirection.ltr,
              selected: r.id == _selected,
              onTap: () {
                if (r.id != _selected) _select(r.id);
              },
            ),
        ],
      ),
      const SizedBox(height: LnSpace.sm),
    ];
    if (current != null) {
      children.add(
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.pageGutter,
            0,
            LnSpace.pageGutter - 2,
            0,
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      current.symbol,
                      textDirection: TextDirection.ltr,
                      style: ln.text.largeTitle.copyWith(color: c.fg),
                    ),
                    Text(
                      current.timeframe,
                      textDirection: TextDirection.ltr,
                      style: ln.text.footnote.copyWith(color: c.fgMuted),
                    ),
                  ],
                ),
              ),
              if (scene?.quote != null)
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      marketNumber(scene!.quote!.bid),
                      textDirection: TextDirection.ltr,
                      style: ln.text.headline.copyWith(color: c.fg),
                    ),
                    Text(
                      '${context.t('ask')} ${ltr(marketNumber(scene.quote!.ask))}',
                      style: ln.text.footnote.copyWith(color: c.fgMuted),
                    ),
                  ],
                ),
              const SizedBox(width: 4),
              _requesting
                  ? const SizedBox.square(
                      dimension: 48,
                      child: Center(child: LnSpinner()),
                    )
                  : CircleIconButton(
                      icon: const Icon(FIcons.refreshCw),
                      semanticLabel: context.t('refresh'),
                      onTap: _requestRefresh,
                    ),
            ],
          ),
        ),
      );
      children.add(const SizedBox(height: LnSpace.sm));
      children.addAll(_scenePart(current, scene));
      if (current.threadId != null && current.threadId != widget.threadId) {
        children
          ..add(const SizedBox(height: LnSpace.lg))
          ..add(
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                horizontal: LnSpace.pageGutter,
              ),
              child: BlockButton(
                label: context.t('openConversation'),
                icon: FIcons.messageCircle,
                variant: BlockButtonVariant.secondary,
                onPressed: () => context.go(Routes.thread(current.threadId!)),
              ),
            ),
          );
      }
    }
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: EdgeInsets.only(
        bottom: LnSpace.xxl + MediaQuery.paddingOf(context).bottom,
      ),
      children: children,
    );
  }

  List<Widget> _scenePart(ChartRow current, ChartScene? scene) {
    final ln = context.ln;
    final c = ln.colors;
    const gutter = EdgeInsetsDirectional.symmetric(
      horizontal: LnSpace.pageGutter,
    );
    if (scene == null) {
      final error = _sceneError;
      if (error is ApiError && error.code == 'chart_initializing') {
        return [
          const SizedBox(height: 60),
          const Center(child: LnSpinner(size: 24)),
          const SizedBox(height: 12),
          Center(
            child: Text(
              context.t('chartInitializing'),
              style: ln.text.caption.copyWith(color: c.fgMuted),
            ),
          ),
        ];
      }
      if (error != null) {
        return [
          const SizedBox(height: 40),
          LoadFailure(
            error: error,
            onRetry: () {
              setState(() => _sceneError = null);
              unawaited(_loadScene());
            },
          ),
        ];
      }
      return [
        const SizedBox(height: 80),
        const Center(child: LnSpinner(size: 28)),
      ];
    }
    if (scene.candles.isEmpty) {
      return [
        const SizedBox(height: 40),
        EmptyState(
          icon: FIcons.chartCandlestick,
          title: context.t('chartDataEmpty'),
        ),
      ];
    }
    final overlays = [
      for (final i in scene.indicators)
        if (i.overlay) ...i.series.values,
    ];
    final panes = [
      for (final i in scene.indicators)
        if (!i.overlay) i,
    ];
    final count = _range == 0 ? null : _range;
    final window = visibleWindow(scene.candles, overlays, count);
    final candles = window.candles;
    final cursor = _cursor != null && _cursor! < candles.length
        ? _cursor
        : null;
    final shown = cursor == null ? candles.last : candles[cursor];
    final span = priceRange(candles);
    final digits = priceDecimals(span.max - span.min);
    String p(double v) => v.toStringAsFixed(digits);
    final readout =
        '${readoutTime(shown.time)} · O ${p(shown.open)}  H ${p(shown.high)}  L ${p(shown.low)}  C ${p(shown.close)}';
    final stale = _sceneError == null
        ? null
        : errorMessage(context, _sceneError!);
    final notes = scene.notes(accountId: current.accountId);
    return [
      // A later read failed (broker gone, offline): the chart shown is the last one read.
      if (stale != null) Footnote(stale, icon: FIcons.triangleAlert),
      Padding(
        padding: gutter,
        child: Semantics(
          liveRegion: cursor != null,
          child: Text(
            readout,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textDirection: TextDirection.ltr,
            style: ln.text.small.copyWith(
              color: cursor == null ? c.fgMuted : c.fg,
              letterSpacing: 0,
            ),
          ),
        ),
      ),
      const SizedBox(height: LnSpace.xs),
      Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(
          LnSpace.pageGutter - 4,
          0,
          LnSpace.xs,
          0,
        ),
        child: CandleChart(
          candles: candles,
          timeframe: scene.timeframe,
          overlays: window.series,
          drawings: scene.drawings(accountId: current.accountId),
          height: 300,
          semanticLabel: '${scene.symbol} · ${scene.timeframe}',
          cursor: cursor,
          onCursor: (i) => setState(() => _cursor = i),
        ),
      ),
      for (final o in panes) ...[
        const SizedBox(height: LnSpace.sm),
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.pageGutter - 4,
            0,
            LnSpace.xs,
            0,
          ),
          child: IndicatorPane(
            label: o.label,
            bounded: o.bounded,
            series: Map.fromIterables(
              o.series.keys,
              visibleWindow(
                scene.candles,
                o.series.values.toList(),
                count,
              ).series,
            ),
            cursor: cursor,
          ),
        ),
      ],
      const SizedBox(height: LnSpace.md),
      Padding(
        padding: gutter,
        child: Semantics(
          label: context.t('ch_range'),
          child: LnSegmented<int>(
            segments: [
              for (final r in _ranges)
                LnSegment(
                  value: r,
                  label: r == 0 ? context.t('sh_fAll') : '$r',
                ),
            ],
            selected: _range,
            onChanged: (r) {
              HapticFeedback.selectionClick();
              setState(() {
                _range = r;
                _cursor = null;
              });
            },
          ),
        ),
      ),
      Footnote(context.t('ch_crosshair'), icon: FIcons.move),
      if (scene.quote != null) ...[
        const SizedBox(height: LnSpace.sm),
        Padding(
          padding: gutter,
          child: FactsCard(
            title: context.t('quote'),
            children: [
              FactRow(
                label: context.t('bid'),
                value: marketNumber(scene.quote!.bid),
              ),
              FactRow(
                label: context.t('ask'),
                value: marketNumber(scene.quote!.ask),
              ),
              FactRow(
                label: context.t('mk_spread'),
                value: scene.quote!.spread,
              ),
              if (scene.quote!.source.isNotEmpty)
                FactRow(
                  label: context.t('mk_source'),
                  value: quoteSource(context, scene.quote!.source),
                ),
            ],
          ),
        ),
      ],
      if (notes.isNotEmpty) ...[
        const SizedBox(height: LnSpace.sm),
        Padding(
          padding: gutter,
          child: FactsCard(
            title: context.t('ch_notes'),
            children: [
              for (final n in notes)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Text(
                    n,
                    textDirection: readingDirection(n),
                    style: ln.text.caption.copyWith(color: c.fg),
                  ),
                ),
            ],
          ),
        ),
      ],
      if (scene.updatedAt != null)
        Footnote(
          // A date: in the date digits; the axes and the crosshair readout stay Latin.
          '${context.t('chartUpdated')} · '
          '${ltr(dateDigits(readoutTime(scene.updatedAt!), context.l10n.lang))}',
        ),
    ];
  }
}

/// Chart creation (apps/mobile app/charts.tsx create): an enabled broker account, then one of
/// its exact symbols (never picked automatically), then an interval; Save posts the chart.
/// An agent bound to a market locks its account and symbol.
class CreateChartSheet extends StatefulWidget {
  const CreateChartSheet({
    super.key,
    this.agentId,
    this.threadId,
    this.lockedAccount,
    this.lockedSymbol,
  });

  final String? agentId;
  final String? threadId;
  final String? lockedAccount;
  final String? lockedSymbol;

  @override
  State<CreateChartSheet> createState() => _CreateChartSheetState();
}

class _CreateChartSheetState extends State<CreateChartSheet> {
  /// Every connection (labels count over all of them, as on the Web).
  List<MarketConnection> _all = const [];
  List<MarketConnection>? _connections;
  Object? _error;
  String? _account;
  List<String>? _symbols;
  String? _symbol;
  String _timeframe = '1h';
  String _query = '';
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(_loadConnections());
  }

  Future<void> _loadConnections() async {
    try {
      final all = await fetchMarketConnections();
      final locked = widget.lockedAccount;
      final enabled = [
        for (final c in all)
          if (c.enabled && (locked == null || locked.isEmpty || c.id == locked))
            c,
      ];
      if (!mounted) return;
      setState(() {
        _all = all;
        _connections = enabled;
      });
      if (locked != null && enabled.any((c) => c.id == locked)) {
        await _pickAccount(locked);
      }
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  Future<void> _pickAccount(String id) async {
    setState(() {
      _account = id;
      _symbols = null;
      _symbol = null;
    });
    try {
      final rows = await fetchMarketSymbols(id);
      if (!mounted || _account != id) return;
      final locked = widget.lockedSymbol;
      final matching = locked == null || locked.isEmpty
          ? rows
          : rows.where((s) => s == locked).toList();
      setState(() {
        _symbols = matching;
        // The broker catalog is not an instruction to pick its first market: only an
        // agent's exact binding fills the field.
        _symbol = id == widget.lockedAccount && matching.contains(locked)
            ? locked
            : null;
      });
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  Future<void> _save() async {
    final account = _account, symbol = _symbol;
    if (account == null || symbol == null || _busy) return;
    setState(() => _busy = true);
    try {
      final chart = await createChart(
        accountId: account,
        symbol: symbol,
        timeframe: _timeframe,
        agentId: widget.agentId,
        threadId: widget.threadId,
      );
      if (mounted) Navigator.of(context).pop(chart);
    } catch (e) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = e;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    final ln = context.ln;
    final c = ln.colors;
    final connections = _connections;
    final symbols = _symbols;
    final needle = _query.trim().toUpperCase();
    final hits = symbols == null
        ? const <String>[]
        : [
            for (final s in symbols)
              if (needle.isEmpty || s.toUpperCase().contains(needle)) s,
          ];
    Widget label(String text) => Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(4, 16, 4, 8),
      child: Text(
        text,
        style: ln.text.footnoteStrong.copyWith(color: c.fgMuted),
      ),
    );
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Flexible(
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_error != null)
                  Footnote(
                    errorMessage(context, _error!) ??
                        context.t('request_failed'),
                    icon: FIcons.triangleAlert,
                  ),
                label(context.t('brokerAccount')),
                if (connections == null)
                  const Padding(
                    padding: EdgeInsets.all(16),
                    child: Center(child: LnSpinner()),
                  )
                else if (connections.isEmpty)
                  Footnote(context.t('brokerMissing'))
                else
                  LnSection(
                    padding: EdgeInsets.zero,
                    children: [
                      for (final x in connections)
                        ChoiceTile(
                          title: brokerAccountLabel(
                            context.l10n,
                            x.raw,
                            _all.indexOf(x),
                          ),
                          icon: x.isSimulation
                              ? FIcons.flaskConical
                              : FIcons.landmark,
                          selected: x.id == _account,
                          enabled: widget.lockedAccount == null,
                          onSelect: () => _pickAccount(x.id),
                        ),
                    ],
                  ),
                if (_account != null) ...[
                  label(context.t('symbol')),
                  if (symbols == null)
                    const Padding(
                      padding: EdgeInsets.all(16),
                      child: Center(child: LnSpinner()),
                    )
                  else ...[
                    if (widget.lockedSymbol == null && symbols.length > 6)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: LnTextField(
                          hint: context.t('searchBrokerSymbols'),
                          prefix: const Icon(FIcons.search),
                          onChanged: (v) => setState(() => _query = v),
                        ),
                      ),
                    if (hits.isEmpty)
                      Footnote(context.t('noResults'))
                    else
                      LnSection(
                        padding: EdgeInsets.zero,
                        children: [
                          for (final s in hits.take(8))
                            ChoiceTile(
                              title: s,
                              selected: s == _symbol,
                              onSelect: () => setState(() => _symbol = s),
                            ),
                        ],
                      ),
                  ],
                ],
                label(context.t('timeframe')),
                Wrap(
                  spacing: 8,
                  children: [
                    for (final tf in chartTimeframes)
                      LnChoiceChip(
                        label: tf,
                        textDirection: TextDirection.ltr,
                        selected: tf == _timeframe,
                        onTap: () => setState(() => _timeframe = tf),
                      ),
                  ],
                ),
                const SizedBox(height: 16),
              ],
            ),
          ),
        ),
        BlockButton(
          label: context.t('save'),
          loading: _busy,
          onPressed: _account == null || _symbol == null ? null : _save,
        ),
      ],
    );
  }
}
