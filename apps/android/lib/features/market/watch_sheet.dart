// A new watch on one market (apps/web components/market/MarketWatch.tsx and the shell's
// conditional schedule, SchedulesPages.tsx): its source (price · indicator · position · account
// changes · economic calendar) with that source's fields, the agent it wakes, the condition, the
// level and the task it is woken with; `POST /watches {payload, agent_id}`. A watch carries no
// authority: it only wakes the agent (apps/web shell/domain/api.ts `createWatch`). The server's
// Watch contract decides; its refusal codes are shown through `errorText`.
import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../app/services.dart';
import '../../avatar/avatar.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../settings/settings_common.dart' show errorMessage, showErrorToast;
import 'market_data.dart';
import 'market_kit.dart';

/// The sources a watch can read (lonora_contracts Watch `kind`, as the Web offers them).
const watchKinds = ['price', 'indicator', 'position', 'account', 'calendar'];

/// The level conditions; the others need no level.
const watchThresholds = ['cross_above', 'cross_below', 'above', 'below'];

/// The conditions each source accepts, in the Web's order.
List<String> watchConditionsFor(String kind) => switch (kind) {
  'calendar' => const ['due'],
  'account' => const ['changed', ...watchThresholds],
  'position' => const ['changed', 'closed', 'opened', ...watchThresholds],
  _ => watchThresholds,
};

/// The condition a source starts with (apps/web MarketWatch `setCondition`).
String defaultWatchCondition(String kind) => switch (kind) {
  'calendar' => 'due',
  'position' => 'closed',
  'account' => 'changed',
  _ => 'cross_above',
};

/// The metrics an account or position watch reads.
List<String> watchMetricsFor(String kind) => kind == 'position'
    ? const ['profit', 'volume']
    : const ['equity', 'balance', 'margin', 'free_margin'];

/// The indicators and timeframes an indicator watch offers (apps/web MarketWatch).
const watchIndicators = ['sma', 'ema', 'rsi', 'macd', 'atr', 'bollinger'];
const watchTimeframes = ['1m', '5m', '15m', '1h', '4h', '1d'];

String _conditionKey(String c) => switch (c) {
  'cross_above' => 'mk_crossAbove',
  'cross_below' => 'mk_crossBelow',
  'above' => 'mk_above',
  'below' => 'mk_below',
  'changed' => 'mk_changed',
  'closed' => 'mk_closed',
  'opened' => 'mk_opened',
  _ => 'mk_due',
};

String _kindKey(String k) => switch (k) {
  'price' => 'mk_srcPrice',
  'indicator' => 'mk_srcIndicator',
  'position' => 'mk_srcPosition',
  'account' => 'mk_srcAccount',
  _ => 'mk_calendar',
};

String _metricKey(String m) => switch (m) {
  'equity' => 'mk_equity',
  'balance' => 'mk_balance',
  'margin' => 'mk_margin',
  'free_margin' => 'mk_freeMargin',
  'profit' => 'mk_profit',
  _ => 'receiptVolume',
};

/// The `POST /watches` payload of one source: only that source's fields, the level only for
/// a level condition (the server's defaults fill the rest).
Json watchPayload({
  required String kind,
  required String accountId,
  required String symbol,
  required String condition,
  required String prompt,
  String level = '',
  String indicator = 'rsi',
  int period = 14,
  String timeframe = '1h',
  String metric = 'equity',
  String? positionId,
  String? integrationId,
}) => {
  'kind': kind,
  'account_id': accountId,
  'symbol': symbol,
  'condition': condition,
  if (watchThresholds.contains(condition)) 'level': level,
  'prompt': prompt,
  if (kind == 'indicator') ...{
    'indicator': indicator,
    'period': period,
    'timeframe': timeframe,
  },
  if (kind == 'account' || kind == 'position') 'metric': metric,
  if (kind == 'position') 'position_id': positionId,
  if (kind == 'calendar') 'integration_id': integrationId,
};

/// `POST /watches`: a watch of [payload] for [agentId] (outside any conversation, so the
/// server files it in the agent's hidden work thread).
Future<MarketWatch> createWatch({
  required String agentId,
  required Json payload,
}) async => MarketWatch(
  asJson(
    await api.post('/watches', {
      'payload': payload,
      'agent_id': agentId,
      'thread_id': null,
    }),
  ),
);

/// Opens the sheet; completes with the created watch.
Future<MarketWatch?> showCreateWatchSheet(
  BuildContext context, {
  required String accountId,
  required String symbol,
  required List<Agent> agents,
  List<MarketPosition> positions = const [],
  String? preferredAgent,
}) => showLnSheet<MarketWatch>(
  context,
  title: '${context.t('mk_createWatch')} · ${ltr(symbol)}',
  maxHeightFraction: 0.94,
  builder: (_) => CreateWatchSheet(
    accountId: accountId,
    symbol: symbol,
    agents: agents,
    positions: positions,
    preferredAgent: preferredAgent,
  ),
);

class CreateWatchSheet extends StatefulWidget {
  const CreateWatchSheet({
    super.key,
    required this.accountId,
    required this.symbol,
    required this.agents,
    this.positions = const [],
    this.preferredAgent,
  });

  final String accountId;
  final String symbol;
  final List<Agent> agents;

  /// The account's open positions on this market (offered for a position watch).
  final List<MarketPosition> positions;
  final String? preferredAgent;

  @override
  State<CreateWatchSheet> createState() => _CreateWatchSheetState();
}

class _CreateWatchSheetState extends State<CreateWatchSheet> {
  late String? _agent =
      widget.preferredAgent ??
      (widget.agents.length == 1 ? widget.agents.first.id : null);
  String _kind = 'price';
  String _condition = 'cross_above';
  String _metric = 'equity';
  String _indicator = 'rsi';
  String _timeframe = '1h';
  String? _feed;
  Map<String, String>? _feeds;
  Object? _feedsError;
  final _period = TextEditingController(text: '14');
  final _positionId = TextEditingController();
  final _level = TextEditingController();
  final _prompt = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _period.dispose();
    _positionId.dispose();
    _level.dispose();
    _prompt.dispose();
    super.dispose();
  }

  void _pickKind(String kind) {
    setState(() {
      _kind = kind;
      _condition = defaultWatchCondition(kind);
      _metric = kind == 'position' ? 'profit' : 'equity';
    });
    if (kind == 'calendar' && _feeds == null) unawaited(_loadFeeds());
  }

  Future<void> _loadFeeds() async {
    setState(() => _feedsError = null);
    try {
      final feeds = await fetchCalendarFeeds();
      if (!mounted) return;
      setState(() {
        _feeds = feeds;
        if (feeds.length == 1) _feed = feeds.keys.first;
      });
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted) setState(() => _feedsError = e);
    }
  }

  bool get _needsLevel => watchThresholds.contains(_condition);

  int? get _periodValue {
    final p = int.tryParse(_period.text.trim());
    return p != null && p >= 2 && p <= 500 ? p : null;
  }

  bool get _valid {
    if (_agent == null || _prompt.text.trim().isEmpty) return false;
    if (_needsLevel) {
      final level = double.tryParse(_level.text.trim());
      if (level == null || (_kind == 'price' && level <= 0)) return false;
    }
    return switch (_kind) {
      'indicator' => _periodValue != null,
      'position' => _positionId.text.trim().isNotEmpty,
      'calendar' => _feed != null,
      _ => true,
    };
  }

  Future<void> _save() async {
    if (!_valid || _busy) return;
    setState(() => _busy = true);
    try {
      final watch = await createWatch(
        agentId: _agent!,
        payload: watchPayload(
          kind: _kind,
          accountId: widget.accountId,
          symbol: widget.symbol,
          condition: _condition,
          level: _level.text.trim(),
          prompt: _prompt.text.trim(),
          indicator: _indicator,
          period: _periodValue ?? 14,
          timeframe: _timeframe,
          metric: _metric,
          positionId: _positionId.text.trim(),
          integrationId: _feed,
        ),
      );
      if (mounted) Navigator.of(context).pop(watch);
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
    final ln = context.ln;
    final c = ln.colors;
    Widget label(String text) => Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(4, 16, 4, 8),
      child: Text(
        text,
        style: ln.text.footnoteStrong.copyWith(color: c.fgMuted),
      ),
    );
    Widget chips<T>(
      Iterable<T> values,
      T selected,
      String Function(T) text,
      void Function(T) pick, {
      TextDirection? direction,
    }) => Wrap(
      spacing: 8,
      children: [
        for (final v in values)
          LnChoiceChip(
            label: text(v),
            textDirection: direction,
            selected: v == selected,
            onTap: () => setState(() => pick(v)),
          ),
      ],
    );

    final source = <Widget>[
      label(context.t('mk_watchSource')),
      Wrap(
        spacing: 8,
        children: [
          for (final k in watchKinds)
            LnChoiceChip(
              label: context.t(_kindKey(k)),
              selected: k == _kind,
              onTap: () => _pickKind(k),
            ),
        ],
      ),
      if (_kind == 'indicator') ...[
        label(context.t('mk_indicator')),
        chips(
          watchIndicators,
          _indicator,
          (v) => v.toUpperCase(),
          (v) => _indicator = v,
          direction: TextDirection.ltr,
        ),
        label(context.t('timeframe')),
        chips(
          watchTimeframes,
          _timeframe,
          (v) => v,
          (v) => _timeframe = v,
          direction: TextDirection.ltr,
        ),
        const SizedBox(height: 8),
        LnTextField(
          controller: _period,
          label: context.t('mk_period'),
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
          onChanged: (_) => setState(() {}),
        ),
      ],
      if (_kind == 'position') ...[
        label(context.t('mk_positionId')),
        if (widget.positions.isNotEmpty) ...[
          Wrap(
            spacing: 8,
            children: [
              for (final p in widget.positions)
                LnChoiceChip(
                  label:
                      '${context.t(p.isSell ? 'mk_sell' : 'mk_buy')} ${ltr(p.volume)}',
                  selected: p.id == _positionId.text.trim(),
                  onTap: () => setState(() => _positionId.text = p.id),
                ),
            ],
          ),
          const SizedBox(height: 8),
        ],
        LnTextField(
          controller: _positionId,
          hint: context.t('mk_positionId'),
          onChanged: (_) => setState(() {}),
        ),
      ],
      if (_kind == 'account' || _kind == 'position') ...[
        label(context.t('mk_metric')),
        chips(
          watchMetricsFor(_kind),
          _metric,
          (v) => context.t(_metricKey(v)),
          (v) => _metric = v,
        ),
      ],
      if (_kind == 'calendar') ...[
        label(context.t('mk_calendarFeed')),
        if (_feedsError != null)
          Footnote(
            errorMessage(context, _feedsError!) ?? context.t('request_failed'),
            icon: FIcons.triangleAlert,
          )
        else if (_feeds == null)
          const Padding(
            padding: EdgeInsets.all(12),
            child: Center(child: LnSpinner()),
          )
        else if (_feeds!.isEmpty)
          Footnote(context.t('mk_calendarEmpty'))
        else
          Wrap(
            spacing: 8,
            children: [
              for (final e in _feeds!.entries)
                LnChoiceChip(
                  label: e.value,
                  textDirection: readingDirection(e.value),
                  selected: e.key == _feed,
                  onTap: () => setState(() => _feed = e.key),
                ),
            ],
          ),
      ],
    ];

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Flexible(
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                ...source,
                label(context.t('mk_agent')),
                Wrap(
                  spacing: 8,
                  children: [
                    for (final a in widget.agents)
                      LnChoiceChip(
                        label: a.name,
                        leading: LonoraAvatar(
                          agentId: a.id,
                          face: a.avatar,
                          color: a.color,
                          size: 20,
                          animate: false,
                        ),
                        selected: a.id == _agent,
                        onTap: () => setState(() => _agent = a.id),
                      ),
                  ],
                ),
                label(context.t('mk_condition')),
                chips(
                  watchConditionsFor(_kind),
                  _condition,
                  (v) => context.t(_conditionKey(v)),
                  (v) => _condition = v,
                ),
                if (_needsLevel) ...[
                  const SizedBox(height: 8),
                  LnTextField(
                    controller: _level,
                    label: context.t(
                      _kind == 'price' ? 'mk_priceLevel' : 'mk_level',
                    ),
                    keyboardType: TextInputType.numberWithOptions(
                      decimal: true,
                      signed: _kind != 'price',
                    ),
                    inputFormatters: [
                      FilteringTextInputFormatter.allow(
                        RegExp(_kind == 'price' ? r'[0-9.]' : r'[0-9.\-]'),
                      ),
                    ],
                    onChanged: (_) => setState(() {}),
                  ),
                ],
                const SizedBox(height: 12),
                LnTextField(
                  controller: _prompt,
                  label: context.t('mk_watchTask'),
                  minLines: 2,
                  maxLines: 5,
                  onChanged: (_) => setState(() {}),
                ),
                Footnote(context.t('mk_watchNote'), icon: FIcons.shieldCheck),
                const SizedBox(height: 8),
              ],
            ),
          ),
        ),
        BlockButton(
          label: context.t('mk_createWatch'),
          loading: _busy,
          onPressed: _valid ? _save : null,
        ),
      ],
    );
  }
}
