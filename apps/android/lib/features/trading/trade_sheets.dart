// The owner's order sheets: the review every order passes before it is sent (the account and
// its kind, the symbol, side, type, volume, price and levels; old → new for an edit; the
// live-money warning off a simulation), the stop-and-target form (TradesPage.tsx `ModifyForm`)
// and the order ticket (components/trading/TradeActionCard.tsx). The review's confirm button
// is guarded: a second tap during its exit sends and pops nothing more.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/app_state.dart';
import '../market/market_data.dart';
import '../market/market_kit.dart';
import '../market/market_widgets.dart';
import '../settings/settings_common.dart' show errorMessage;
import 'recovery_link.dart';
import 'trade_flows.dart';
import 'trade_rules.dart';
import 'trade_text.dart';
import 'trade_widgets.dart';
import 'trades_data.dart';
import 'trading_strings.dart';

/// One reviewed fact: a label and its value as shown.
typedef ReviewFact = ({String label, String value});

/// The review of an order: completes with true only when the owner taps [confirmLabel]; Cancel,
/// Back, the barrier or a drag complete with false.
Future<bool> showOrderReview(
  BuildContext context, {
  required String title,
  required List<ReviewFact> facts,
  required bool live,
  required String confirmLabel,
  String? message,
  bool destructive = false,
}) async {
  ensureTradingStrings(context);
  final ok = await showLnSheet<bool>(
    context,
    title: title,
    maxHeightFraction: 0.92,
    builder: (_) => _Review(
      facts: facts,
      live: live,
      message: message,
      confirmLabel: confirmLabel,
      destructive: destructive,
    ),
  );
  return ok ?? false;
}

class _Review extends StatefulWidget {
  const _Review({
    required this.facts,
    required this.live,
    required this.confirmLabel,
    required this.destructive,
    this.message,
  });

  final List<ReviewFact> facts;
  final bool live;
  final String confirmLabel;
  final bool destructive;
  final String? message;

  @override
  State<_Review> createState() => _ReviewState();
}

class _ReviewState extends State<_Review> {
  bool _closing = false;

  void _close(bool confirmed) {
    if (_closing) return;
    setState(() => _closing = true);
    Navigator.of(context).pop(confirmed);
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final cancel = BlockButton(
      label: context.t('sh_cancel'),
      variant: BlockButtonVariant.secondary,
      onPressed: _closing ? null : () => _close(false),
    );
    final confirm = BlockButton(
      label: widget.confirmLabel,
      variant: widget.destructive
          ? BlockButtonVariant.destructive
          : BlockButtonVariant.primary,
      onPressed: _closing ? null : () => _close(true),
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
                if (widget.message != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: LnSpace.sm),
                    child: Text(
                      widget.message!,
                      style: ln.text.body.copyWith(color: c.fg),
                    ),
                  ),
                FactsCard(
                  children: [
                    for (final f in widget.facts)
                      FactRow(label: f.label, value: f.value),
                  ],
                ),
                if (widget.live) ...[
                  const SizedBox(height: LnSpace.sm),
                  TradeNotice(
                    text: context.t('tr_liveWarning'),
                    tone: NoticeTone.error,
                    icon: FIcons.triangleAlert,
                  ),
                ],
                const SizedBox(height: LnSpace.md),
              ],
            ),
          ),
        ),
        _ButtonPair(
          first: cancel,
          second: confirm,
          labels: [context.t('sh_cancel'), widget.confirmLabel],
        ),
      ],
    );
  }
}

/// Two full-width buttons side by side while both labels fit, else stacked; [first] comes
/// first in reading order either way.
class _ButtonPair extends StatelessWidget {
  const _ButtonPair({
    required this.first,
    required this.second,
    required this.labels,
  });

  final Widget first;
  final Widget second;
  final List<String> labels;

  @override
  Widget build(BuildContext context) {
    final style = context.ln.text.button;
    final scaler = MediaQuery.textScalerOf(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        final half = (constraints.maxWidth - LnSpace.xs) / 2;
        final fits = labels.every((label) {
          final painter = TextPainter(
            text: TextSpan(text: label, style: style),
            textDirection: Directionality.of(context),
            textScaler: scaler,
            maxLines: 1,
          )..layout();
          final width = painter.width;
          painter.dispose();
          return width + 56 <= half;
        });
        if (fits) {
          return Row(
            children: [
              Expanded(child: first),
              const SizedBox(width: LnSpace.xs),
              Expanded(child: second),
            ],
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            first,
            const SizedBox(height: LnSpace.xs),
            second,
          ],
        );
      },
    );
  }
}

/// Digits (ASCII, Arabic-Indic, Eastern Arabic-Indic) and «.» / «٫» only.
final _decimalInput = FilteringTextInputFormatter.allow(
  RegExp('[0-9٠-٩۰-۹.٫]'),
);

/// A decimal field: its label above, typed left to right, the hint in the interface's
/// direction, the problem under it.
Widget _decimalField(
  BuildContext context, {
  required TextEditingController controller,
  required String label,
  FieldProblem? problem,
  String? helper,
  bool enabled = true,
  ValueChanged<String>? onChanged,
}) => LnTextField(
  controller: controller,
  label: label,
  enabled: enabled,
  keyboardType: const TextInputType.numberWithOptions(decimal: true),
  inputFormatters: [_decimalInput],
  textDirection: TextDirection.ltr,
  hintTextDirection: Directionality.of(context),
  autocorrect: false,
  enableSuggestions: false,
  helper: helper,
  error: problem == null ? null : context.t(problem.key, problem.args),
  onChanged: onChanged,
);

/// «تعديل الوقف والهدف»: the position's levels, «حفظ» once one differs. Completes with the
/// checked request (an emptied level is an explicit clear), or null.
Future<Json?> showModifySheet(
  BuildContext context, {
  required TradeAccount account,
  required MarketPosition position,
}) {
  ensureTradingStrings(context);
  return showLnSheet<Json>(
    context,
    title: context.t('tr_editStopTarget'),
    maxHeightFraction: 0.92,
    builder: (_) => _ModifyForm(account: account, position: position),
  );
}

class _ModifyForm extends StatefulWidget {
  const _ModifyForm({required this.account, required this.position});

  final TradeAccount account;
  final MarketPosition position;

  @override
  State<_ModifyForm> createState() => _ModifyFormState();
}

class _ModifyFormState extends State<_ModifyForm> {
  late final _stop = TextEditingController(
    text: widget.position.stopLoss ?? '',
  );
  late final _target = TextEditingController(
    text: widget.position.takeProfit ?? '',
  );
  InstrumentLimits? _limits;
  bool _reading = true;
  Map<String, FieldProblem> _problems = const {};

  @override
  void initState() {
    super.initState();
    unawaited(_readInstrument());
  }

  @override
  void dispose() {
    _stop.dispose();
    _target.dispose();
    super.dispose();
  }

  /// The tick the levels must sit on; without it the server still checks.
  Future<void> _readInstrument() async {
    try {
      final i = await fetchInstrument(
        widget.account.id,
        widget.position.symbol,
      );
      if (mounted) setState(() => _limits = InstrumentLimits.of(i));
    } catch (_) {
      // Checked by the executor instead.
    } finally {
      if (mounted) setState(() => _reading = false);
    }
  }

  bool get _changed =>
      _stop.text != (widget.position.stopLoss ?? '') ||
      _target.text != (widget.position.takeProfit ?? '');

  void _save() {
    final check = checkModify(
      accountId: widget.account.id,
      position: widget.position,
      stop: _stop.text,
      target: _target.text,
      limits: _limits,
    );
    var problems = check.problems;
    final request = check.request;
    final a = widget.account;
    final snapshot = a.snapshot;
    // The values of a held edit check it (the executor answers from its journal); only a new
    // edit waits for the broker.
    final checking =
        request != null &&
        OrderDesk.instance.held(
              a.scope,
              heldKey('modify_position', a.id, modifyTicket(request)),
            ) !=
            null;
    if (request != null && !checking) {
      if (a.notAllowed) {
        problems = const {'change': FieldProblem('broker_trading_not_allowed')};
      } else if (a.down &&
          (snapshot == null || !riskReducing(request, snapshot))) {
        problems = const {'change': FieldProblem('tr_onlyTighten')};
      }
    }
    if (problems.isNotEmpty || request == null) {
      setState(() => _problems = problems);
      return;
    }
    Navigator.of(context).pop(request);
  }

  @override
  Widget build(BuildContext context) {
    final change = _problems['change'];
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Flexible(
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (widget.account.notAllowed) ...[
                  TradeNotice(
                    text: context.t('broker_trading_not_allowed'),
                    tone: NoticeTone.error,
                    icon: FIcons.ban,
                  ),
                  const SizedBox(height: LnSpace.sm),
                ] else if (widget.account.down) ...[
                  TradeNotice(text: context.t('tr_onlyTighten')),
                  const SizedBox(height: LnSpace.sm),
                ],
                _decimalField(
                  context,
                  controller: _stop,
                  label: context.t('stopLoss'),
                  problem: _problems['stop_loss'],
                  onChanged: (_) => setState(() => _problems = const {}),
                ),
                const SizedBox(height: LnSpace.sm),
                _decimalField(
                  context,
                  controller: _target,
                  label: context.t('takeProfit'),
                  problem: _problems['take_profit'],
                  onChanged: (_) => setState(() => _problems = const {}),
                ),
                if (change != null)
                  Semantics(
                    liveRegion: true,
                    child: Footnote(
                      context.t(change.key, change.args),
                      icon: FIcons.circleAlert,
                    ),
                  ),
                const SizedBox(height: LnSpace.md),
              ],
            ),
          ),
        ),
        BlockButton(
          label: context.t('save'),
          loading: _reading && _changed,
          onPressed: _changed && !_reading ? _save : null,
        ),
      ],
    );
  }
}

/// «فتح أمر»: the order ticket on [symbol], on [accountId] or another enabled account of
/// [connections] ([label] names them as the Market tab does).
Future<void> showOrderTicket(
  BuildContext context, {
  required List<MarketConnection> connections,
  required String accountId,
  required String symbol,
  required String Function(MarketConnection) label,
  VoidCallback? onChanged,
}) {
  ensureTradingStrings(context);
  return showLnSheet<void>(
    context,
    title: context.t('tr_tradeAction'),
    maxHeightFraction: 0.92,
    builder: (_) => OrderTicket(
      connections: connections,
      accountId: accountId,
      symbol: symbol,
      label: label,
      onChanged: onChanged,
    ),
  );
}

/// The order ticket (TradeActionCard.tsx): the exact broker symbol, the action, the volume, a
/// price for a pending entry and the optional levels, every rule checked before the review.
/// While its account holds an order, the form shows that order, locked, and its button reads
/// «فحص العملية الحالية»: the same identity and body are sent again, never a new one.
class OrderTicket extends StatefulWidget {
  const OrderTicket({
    super.key,
    required this.connections,
    required this.accountId,
    required this.symbol,
    required this.label,
    this.onChanged,
  });

  final List<MarketConnection> connections;
  final String accountId;
  final String symbol;
  final String Function(MarketConnection) label;
  final VoidCallback? onChanged;

  @override
  State<OrderTicket> createState() => _OrderTicketState();
}

class _OrderTicketState extends State<OrderTicket> {
  late String _account = widget.accountId;
  String _action = 'buy';
  final _volume = TextEditingController();
  final _price = TextEditingController();
  final _stop = TextEditingController();
  final _target = TextEditingController();
  MarketInstrument? _instrument;
  Object? _instrumentError;
  AccountSnapshot? _snapshot;
  Map<String, FieldProblem> _problems = const {};
  int _generation = 0;

  String? get _scope =>
      orderScope(StoreProvider.state<AppState>(context, notify: false).session);

  List<MarketConnection> get _enabled => [
    for (final c in widget.connections)
      if (c.enabled) c,
  ];

  MarketConnection? get _connection {
    for (final c in widget.connections) {
      if (c.id == _account) return c;
    }
    return null;
  }

  String get _key => openKey(_account);

  @override
  void initState() {
    super.initState();
    OrderDesk.instance.addListener(_onDesk);
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_load()));
  }

  @override
  void dispose() {
    OrderDesk.instance.removeListener(_onDesk);
    _volume.dispose();
    _price.dispose();
    _stop.dispose();
    _target.dispose();
    super.dispose();
  }

  void _onDesk() {
    if (mounted) setState(() {});
  }

  /// The held order of the account, if any (its values fill the locked form), then the
  /// instrument and the account's permissions.
  Future<void> _load() async {
    final scope = _scope;
    if (scope == null) return;
    final gen = ++_generation;
    await OrderDesk.instance.load(scope);
    if (!mounted || gen != _generation) return;
    final held = OrderDesk.instance.held(scope, _key);
    setState(() {
      _instrument = null;
      _instrumentError = null;
      _snapshot = null;
      _problems = const {};
      if (held != null) _fill(held.body);
    });
    final symbol = _symbol;
    await Future.wait([
      () async {
        try {
          final i = await fetchInstrument(_account, symbol);
          if (mounted && gen == _generation) setState(() => _instrument = i);
        } on SessionRequestCancelled {
          return;
        } catch (e) {
          if (mounted && gen == _generation) {
            setState(() => _instrumentError = e);
          }
        }
      }(),
      () async {
        try {
          final s = await fetchAccountSnapshot(_account);
          if (mounted && gen == _generation) setState(() => _snapshot = s);
        } catch (_) {
          // The executor checks the account's permissions anyway.
        }
      }(),
    ]);
  }

  void _fill(Json body) {
    _action = asStr(body['action'], 'buy');
    _volume.text = asStr(body['volume']);
    _price.text = asStr(body['price']);
    _stop.text = asStr(body['stop_loss']);
    _target.text = asStr(body['take_profit']);
  }

  /// The symbol the form is on: the held order's, else the sheet's.
  String get _symbol {
    final scope = _scope;
    final held = scope == null ? null : OrderDesk.instance.held(scope, _key);
    return asString(held?.body['symbol']) ?? widget.symbol;
  }

  TradeAccount _tradeAccount(String scope) {
    final c = _connection;
    return TradeAccount(
      scope: scope,
      id: _account,
      label: c == null ? _account : widget.label(c),
      simulation: c?.isSimulation ?? false,
      snapshot: _snapshot,
      recovery: c?.recovery,
    );
  }

  void _pickAccount(String id) {
    if (id == _account) return;
    setState(() {
      _account = id;
      _action = 'buy';
      for (final c in [_volume, _price, _stop, _target]) {
        c.clear();
      }
    });
    unawaited(_load());
  }

  List<ReviewFact> _facts(L10n l10n, TradeAccount a, Json body) {
    final action = asStr(body['action']);
    String level(Object? v) => v == null || '$v'.isEmpty ? '—' : ltr('$v');
    final pending = pendingEntryActions.contains(action);
    return [
      a.fact(l10n),
      (label: l10n.t('symbol'), value: ltr(asStr(body['symbol']))),
      (label: l10n.t('tr_side'), value: sideWord(l10n, action)),
      (label: l10n.t('tr_type'), value: orderWording(l10n, action).kind),
      (label: l10n.t('receiptVolume'), value: level(body['volume'])),
      (
        label: l10n.t(pending ? 'orderPrice' : 'tr_price'),
        value: pending ? level(body['price']) : l10n.t('approvalAtMarket'),
      ),
      (label: l10n.t('stopLoss'), value: level(body['stop_loss'])),
      (label: l10n.t('takeProfit'), value: level(body['take_profit'])),
    ];
  }

  Future<void> _review() async {
    final scope = _scope;
    if (scope == null) return;
    final l10n = context.l10n;
    final desk = OrderDesk.instance;
    final a = _tradeAccount(scope);
    final held = desk.held(scope, _key);
    final Json body;
    if (held != null) {
      body = held.body;
    } else {
      final instrument = _instrument;
      if (instrument == null) return;
      final check = checkOpen(
        accountId: _account,
        action: _action,
        symbol: _symbol,
        volume: _volume.text,
        price: _price.text,
        stop: _stop.text,
        target: _target.text,
        limits: InstrumentLimits.of(instrument),
      );
      if (!check.ok) {
        setState(() => _problems = check.problems);
        return;
      }
      body = check.request!;
    }
    final ok = await showOrderReview(
      context,
      title: l10n.t('tr_review'),
      facts: [
        ..._facts(l10n, a, body),
        if (held != null) heldFact(l10n, held.createdAt),
      ],
      live: !a.simulation,
      confirmLabel: l10n.t(held != null ? 'tr_checkExisting' : 'tr_execute'),
    );
    if (!ok || !mounted) return;
    await sendReviewed(
      context,
      scope: scope,
      key: _key,
      build: () => body,
      expect: held?.operationId,
    );
    widget.onChanged?.call();
  }

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    ensureTradingStrings(context);
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final scope = _scope;
    if (scope == null) return const SizedBox.shrink();
    final desk = OrderDesk.instance;
    final a = _tradeAccount(scope);
    final held = desk.held(scope, _key);
    final locked = held != null;
    final busy = desk.busy(scope, _key);
    final pending = pendingEntryActions.contains(_action);
    final instrument = _instrument;
    final paused = pausedNotice(
      context,
      a,
      onRecovery: () {
        Navigator.of(context).pop();
        unawaited(context.push(recoveryLocation(account: a.id)));
      },
    );
    final canReview =
        !busy && (locked || (instrument != null && !a.notAllowed && !a.down));
    Widget label(String text) => Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(4, 16, 4, 8),
      child: Text(
        text,
        style: ln.text.footnoteStrong.copyWith(color: c.fgMuted),
      ),
    );
    final limits = instrument == null ? null : InstrumentLimits.of(instrument);
    final helper = limits == null
        ? null
        : [
            '${l10n.t('mk_volumeMin')} ${ltr('${limits.volumeMin ?? '—'}')}',
            '${l10n.t('mk_volumeStep')} ${ltr('${limits.volumeStep ?? '—'}')}',
            '${l10n.t('mk_volumeMax')} ${ltr('${limits.volumeMax ?? '—'}')}',
          ].join(dotSeparator);
    void edited(String _) => setState(() => _problems = const {});
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Flexible(
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_enabled.length > 1 && !busy) ...[
                  label(l10n.t('account')),
                  Wrap(
                    spacing: 8,
                    children: [
                      for (final conn in _enabled)
                        LnChoiceChip(
                          label: widget.label(conn),
                          icon: conn.isSimulation
                              ? FIcons.flaskConical
                              : FIcons.landmark,
                          textDirection: readingDirection(widget.label(conn)),
                          selected: conn.id == _account,
                          onTap: () => _pickAccount(conn.id),
                        ),
                    ],
                  ),
                ] else
                  FactsCard(
                    children: [
                      FactRow(
                        label: a.fact(l10n).label,
                        value: a.fact(l10n).value,
                      ),
                    ],
                  ),
                label(l10n.t('tr_exactSymbol')),
                // A ticker reads left to right but sits at the line's start.
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: Text(
                    _symbol,
                    textDirection: TextDirection.ltr,
                    style: ln.text.headline.copyWith(color: c.fg),
                  ),
                ),
                if (_instrumentError != null)
                  Footnote(
                    errorMessage(context, _instrumentError!) ??
                        l10n.t('marketDataUnavailable'),
                    icon: FIcons.triangleAlert,
                  ),
                if (paused != null && !locked) ...[
                  const SizedBox(height: LnSpace.sm),
                  paused,
                ],
                label(l10n.t('tr_action')),
                Wrap(
                  spacing: 8,
                  children: [
                    for (final action in tradeEntryActions)
                      if (!locked || action == _action)
                        LnChoiceChip(
                          label: entryActionWord(l10n, action),
                          selected: action == _action,
                          onTap: locked
                              ? () {}
                              : () => setState(() {
                                  _action = action;
                                  _problems = const {};
                                }),
                        ),
                  ],
                ),
                const SizedBox(height: LnSpace.sm),
                _decimalField(
                  context,
                  controller: _volume,
                  label: l10n.t('receiptVolume'),
                  helper: helper,
                  enabled: !locked,
                  problem: _problems['volume'],
                  onChanged: edited,
                ),
                if (pending) ...[
                  const SizedBox(height: LnSpace.sm),
                  _decimalField(
                    context,
                    controller: _price,
                    label: l10n.t('orderPrice'),
                    enabled: !locked,
                    problem: _problems['price'],
                    onChanged: edited,
                  ),
                ],
                const SizedBox(height: LnSpace.sm),
                _decimalField(
                  context,
                  controller: _stop,
                  label: l10n.t('tr_stopOptional'),
                  enabled: !locked,
                  problem: _problems['stop_loss'],
                  onChanged: edited,
                ),
                const SizedBox(height: LnSpace.sm),
                _decimalField(
                  context,
                  controller: _target,
                  label: l10n.t('tr_targetOptional'),
                  enabled: !locked,
                  problem: _problems['take_profit'],
                  onChanged: edited,
                ),
                OutcomeView(
                  outcome: desk.outcome(scope, _key, null),
                  error: desk.error(scope, _key),
                ),
                const SizedBox(height: LnSpace.md),
              ],
            ),
          ),
        ),
        BlockButton(
          label: l10n.t(locked ? 'tr_checkExisting' : 'tr_review'),
          loading: busy || (instrument == null && _instrumentError == null),
          onPressed: canReview ? _review : null,
        ),
      ],
    );
  }
}
