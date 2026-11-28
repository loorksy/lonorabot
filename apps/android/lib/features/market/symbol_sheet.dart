// Sheets of the Market tab: the broker account picker, the symbol search over the account's
// exact broker symbols (`GET /market/symbols`), and one market's sheet: its quote, the last two
// days of hourly closes, the instrument facts (Web MarketQuote/MarketOverview), the owner's open
// positions on it, «فتح أمر» (the order ticket, lib/features/trading) and links into its chart
// and the agents that trade it.
import 'dart:async';

import 'package:flutter/services.dart' show TextInputAction;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../core/api/api_error.dart';
import '../../core/models/models.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/realtime.dart';
import '../charts/candle_chart.dart';
import '../settings/settings_common.dart'
    show ChoiceTile, errorMessage, LoadFailure;
import 'market_data.dart';
import 'market_kit.dart';
import 'market_widgets.dart';

/// Picks one of [connections] (listed and numbered as on the Web; a switched-off one is
/// shown but cannot be chosen); completes with its id (null when dismissed).
Future<String?> showAccountPicker(
  BuildContext context, {
  required List<MarketConnection> connections,
  required String? selected,
  required String Function(MarketConnection, int) label,
}) => showLnSheet<String>(
  context,
  title: context.t('chooseBrokerAccount'),
  builder: (sheet) => SingleChildScrollView(
    child: LnSection(
      padding: EdgeInsets.zero,
      children: [
        for (final (i, c) in connections.indexed)
          ChoiceTile(
            title: label(c, i),
            subtitle: sheet.t(
              !c.enabled
                  ? 'mk_disabled'
                  : c.isSimulation
                  ? 'mk_simulationNote'
                  : 'brokerAccount',
            ),
            icon: c.isSimulation ? FIcons.flaskConical : FIcons.landmark,
            selected: c.id == selected,
            enabled: c.enabled,
            onSelect: () => Navigator.of(sheet).pop(c.id),
          ),
      ],
    ),
  ),
);

/// Searches the account's exact broker symbols; completes with the chosen one.
Future<String?> showSymbolSearch(
  BuildContext context, {
  required String accountId,
}) => showLnSheet<String>(
  context,
  title: context.t('symbol'),
  maxHeightFraction: 0.92,
  builder: (_) => _SymbolSearch(accountId: accountId),
);

class _SymbolSearch extends StatefulWidget {
  const _SymbolSearch({required this.accountId});
  final String accountId;

  @override
  State<_SymbolSearch> createState() => _SymbolSearchState();
}

class _SymbolSearchState extends State<_SymbolSearch> {
  List<String>? _symbols;
  Object? _error;
  String _query = '';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final symbols = await fetchMarketSymbols(widget.accountId);
      if (mounted) setState(() => _symbols = symbols);
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final needle = _query.trim().toUpperCase();
    final all = _symbols;
    final hits = all == null
        ? const <String>[]
        : [
            for (final s in all)
              if (needle.isEmpty || s.toUpperCase().contains(needle)) s,
          ];
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        LnTextField(
          hint: context.t('searchBrokerSymbols'),
          prefix: const Icon(FIcons.search),
          autofocus: true,
          textInputAction: TextInputAction.search,
          onChanged: (v) => setState(() => _query = v),
        ),
        const SizedBox(height: 8),
        Flexible(
          child: _error != null
              ? LoadFailure(error: _error!, onRetry: _load)
              : all == null
              ? const Padding(
                  padding: EdgeInsets.all(32),
                  child: Center(child: LnSpinner()),
                )
              : hits.isEmpty
              ? EmptyState(icon: FIcons.searchX, title: context.t('noResults'))
              : ListView.builder(
                  shrinkWrap: true,
                  itemCount: hits.length,
                  itemBuilder: (context, i) => LnTappable(
                    onTap: () => Navigator.of(context).pop(hits[i]),
                    semanticLabel: hits[i],
                    excludeChildSemantics: true,
                    child: SizedBox(
                      height: 52,
                      child: Row(
                        children: [
                          const SizedBox(width: 8),
                          Icon(FIcons.chartLine, size: 18, color: c.fgMuted),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              hits[i],
                              textDirection: TextDirection.ltr,
                              textAlign: TextAlign.start,
                              style: ln.text.title.copyWith(color: c.fg),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
        ),
      ],
    );
  }
}

/// What the symbol sheet can open; the screen navigates after the sheet closed.
sealed class SymbolSheetResult {
  const SymbolSheetResult();
}

class OpenChartResult extends SymbolSheetResult {
  const OpenChartResult(this.chartId);
  final String chartId;
}

class CreateChartResult extends SymbolSheetResult {
  const CreateChartResult();
}

class CreateWatchResult extends SymbolSheetResult {
  const CreateWatchResult();
}

/// «فتح أمر»: the order ticket on this market (its review and send live in
/// lib/features/trading).
class OpenTicketResult extends SymbolSheetResult {
  const OpenTicketResult();
}

class OpenAgentResult extends SymbolSheetResult {
  const OpenAgentResult(this.agent);
  final Agent agent;
}

/// One market's sheet. Completes with what the owner chose to open.
Future<SymbolSheetResult?> showSymbolSheet(
  BuildContext context, {
  required String accountId,
  required String symbol,
  List<MarketPosition> positions = const [],
  String? chartId,
  List<Agent> agents = const [],
  MarketQuote? quote,
  double? change,
}) => showLnSheet<SymbolSheetResult>(
  context,
  maxHeightFraction: 0.92,
  builder: (_) => SymbolSheet(
    accountId: accountId,
    symbol: symbol,
    positions: [
      for (final p in positions)
        if (p.symbol == symbol) p,
    ],
    chartId: chartId,
    agents: agents,
    quote: quote,
    change: change,
  ),
);

class SymbolSheet extends StatefulWidget {
  /// How often the quote is read again while the sheet is open (apps/web useMarket: 5 s,
  /// one read at a time).
  static const quoteEvery = Duration(seconds: 5);

  const SymbolSheet({
    super.key,
    required this.accountId,
    required this.symbol,
    this.positions = const [],
    this.chartId,
    this.agents = const [],
    this.quote,
    this.change,
  });

  final String accountId;
  final String symbol;
  final List<MarketPosition> positions;
  final String? chartId;
  final List<Agent> agents;
  final MarketQuote? quote;
  final double? change;

  @override
  State<SymbolSheet> createState() => _SymbolSheetState();
}

class _SymbolSheetState extends State<SymbolSheet> {
  late MarketQuote? _quote = widget.quote;
  Object? _quoteError;
  MarketInstrument? _instrument;
  List<MarketCandle>? _candles;
  Timer? _poll;
  StreamSubscription<LonoraEvent>? _events;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    try {
      _events = realtime.events.listen(_onEvent);
    } catch (_) {
      // No realtime controller (previews): the poll keeps the quote fresh.
    }
  }

  @override
  void dispose() {
    _poll?.cancel();
    unawaited(_events?.cancel());
    super.dispose();
  }

  void _onEvent(LonoraEvent e) {
    final p = e.payload;
    if (e.kind != 'market.quote_updated' ||
        p['connection_id'] != widget.accountId ||
        p['symbol'] != widget.symbol) {
      return;
    }
    final quote = MarketQuote.fromJson(
      p['quote'] is Map ? (p['quote']! as Map).cast<String, dynamic>() : {},
    );
    if (quote.symbol == widget.symbol && quote.supersedes(_quote) && mounted) {
      setState(() {
        _quote = quote;
        _quoteError = null;
      });
    }
  }

  /// The next quote read, [SymbolSheet.quoteEvery] after the last one ended.
  void _schedulePoll() {
    _poll?.cancel();
    if (!mounted) return;
    _poll = Timer(SymbolSheet.quoteEvery, () async {
      if (!mounted) return;
      if (TickerMode.getValuesNotifier(context).value.enabled) {
        await _readQuote();
      }
      _schedulePoll();
    });
  }

  Future<void> _readQuote() => _quiet(() async {
    final q = await fetchQuote(widget.accountId, widget.symbol);
    if (mounted && q.supersedes(_quote, orSame: true)) {
      setState(() {
        _quote = q;
        _quoteError = null;
      });
    }
  }, onError: (e) => _quoteError = e);

  Future<void> _load() async {
    await Future.wait([
      _readQuote().whenComplete(_schedulePoll),
      _quiet(() async {
        final i = await fetchInstrument(widget.accountId, widget.symbol);
        if (mounted) setState(() => _instrument = i);
      }),
      _quiet(() async {
        final k = await fetchCandles(
          widget.accountId,
          widget.symbol,
          timeframe: '1h',
          limit: 48,
        );
        if (mounted) setState(() => _candles = k);
      }),
    ]);
  }

  Future<void> _quiet(
    Future<void> Function() read, {
    void Function(Object)? onError,
  }) async {
    try {
      await read();
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted && onError != null) setState(() => onError(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    final ln = context.ln;
    final c = ln.colors;
    final q = _quote;
    final ch = widget.change;
    final instrument = _instrument;
    final candles = _candles;
    final pop = Navigator.of(context).pop;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Semantics(
                      header: true,
                      child: Text(
                        widget.symbol,
                        textDirection: TextDirection.ltr,
                        style: ln.text.display.copyWith(color: c.fg),
                      ),
                    ),
                    if (instrument != null && instrument.description.isNotEmpty)
                      Text(
                        instrument.description,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: ln.text.footnote.copyWith(color: c.fgMuted),
                      ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    q == null ? '—' : marketNumber(q.bid),
                    textDirection: TextDirection.ltr,
                    style: ln.text.display.copyWith(color: c.fg),
                  ),
                  if (ch != null)
                    Text(
                      signedPercent(ch),
                      textDirection: TextDirection.ltr,
                      style: ln.text.footnoteStrong.copyWith(
                        color: ch >= 0 ? c.positiveText : c.negative,
                      ),
                    ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (candles != null && candles.length > 1)
            PriceSparkline(
              candles: candles,
              semanticLabel: '${widget.symbol} · 1h',
            )
          else
            const SizedBox(height: 8),
          const SizedBox(height: 12),
          if (_quoteError != null && q == null)
            Footnote(
              errorMessage(context, _quoteError!) ??
                  context.t('marketDataUnavailable'),
              icon: FIcons.triangleAlert,
            ),
          if (q != null)
            FactsCard(
              title: context.t('quote'),
              children: [
                FactRow(label: context.t('bid'), value: marketNumber(q.bid)),
                FactRow(label: context.t('ask'), value: marketNumber(q.ask)),
                FactRow(label: context.t('mk_spread'), value: q.spread),
                if (q.source.isNotEmpty)
                  FactRow(
                    label: context.t('mk_source'),
                    value: quoteSource(context, q.source),
                  ),
                if (q.observedAt != null)
                  FactRow(
                    label: context.t('chartUpdated'),
                    // A date: in the date digits (a chart's own readout stays Latin).
                    value: ltr(
                      dateDigits(readoutTime(q.observedAt!), context.l10n.lang),
                    ),
                  ),
              ],
            ),
          if (instrument != null) ...[
            const SizedBox(height: 12),
            FactsCard(
              title: context.t('mk_instrument'),
              children: [
                FactRow(
                  label: context.t('mk_tickSize'),
                  value: marketNumber(instrument.tickSize),
                ),
                FactRow(
                  label: context.t('mk_volumeMin'),
                  value: marketNumber(instrument.volumeMin),
                ),
                FactRow(
                  label: context.t('mk_volumeStep'),
                  value: marketNumber(instrument.volumeStep),
                ),
                FactRow(
                  label: context.t('mk_volumeMax'),
                  value: marketNumber(instrument.volumeMax),
                ),
              ],
            ),
          ],
          if (widget.positions.isNotEmpty) ...[
            const SizedBox(height: 12),
            FactsCard(
              title: context.t('mk_positions'),
              children: [
                for (final p in widget.positions)
                  FactRow(
                    label:
                        '${context.t(p.isSell ? 'mk_sell' : 'mk_buy')} ${ltr(p.volume)}',
                    value: p.profit == null ? '—' : signedMoney(p.profit!),
                  ),
              ],
            ),
          ],
          const SizedBox(height: 16),
          BlockButton(
            label: context.t('tr_openOrder'),
            icon: FIcons.arrowLeftRight,
            onPressed: () => pop(const OpenTicketResult()),
          ),
          const SizedBox(height: 8),
          if (widget.chartId != null)
            BlockButton(
              label: context.t('mk_openChart'),
              icon: FIcons.chartCandlestick,
              variant: BlockButtonVariant.secondary,
              onPressed: () => pop(OpenChartResult(widget.chartId!)),
            )
          else
            BlockButton(
              label: context.t('createChart'),
              icon: FIcons.chartCandlestick,
              variant: BlockButtonVariant.secondary,
              onPressed: () => pop(const CreateChartResult()),
            ),
          const SizedBox(height: 8),
          BlockButton(
            label: context.t('mk_createWatch'),
            icon: FIcons.eye,
            variant: BlockButtonVariant.secondary,
            onPressed: () => pop(const CreateWatchResult()),
          ),
          for (final a in widget.agents) ...[
            const SizedBox(height: 8),
            BlockButton(
              label: '${context.t('openConversation')} · ${isolate(a.name)}',
              icon: FIcons.messageCircle,
              variant: BlockButtonVariant.secondary,
              onPressed: () => pop(OpenAgentResult(a)),
            ),
          ],
        ],
      ),
    );
  }
}
