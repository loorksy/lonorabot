// The Market tab: a tab-root title with a trailing context value (the broker account), strips of a
// wide 296 × 128 card and 144 dp tiles that scroll sideways, then "… ›" section headers over
// full-width recommendation cards. Content is Lonora's (apps/web pages/Market.tsx,
// components/market/*, shell/agent/TradesPage.tsx; apps/mobile app/charts.tsx): the account
// snapshot, the markets the owner follows with quotes and the day's change, symbol search, open
// positions and pending orders with the owner's own edit, close and cancel, opportunities, watches
// (with the owner's Pause / Resume / Cancel brake), the economic calendar and the order log, with
// links into charts, agent conversations and «التعطل والاستعادة» when the account is down.
//
// SAFETY: an order is placed, changed, closed or cancelled only from the owner's tap on a review
// sheet (lib/features/trading/trade_flows.dart, trade_sheets.dart); nothing on this screen calls
// `/trading/execute` by itself. Paper (simulation) and broker accounts are labelled.
import 'dart:async';
import 'dart:math' as math;

import 'package:async_redux/async_redux.dart';
import 'package:flutter/foundation.dart' show ValueListenable;
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
import '../../state/actions/base.dart';
import '../../state/actions/thread_actions.dart';
import '../../state/app_state.dart';
import '../../state/realtime.dart';
import '../charts/charts_data.dart' show createChart;
import '../settings/settings_common.dart'
    show LnRefresh, LoadFailure, errorMessage, showErrorToast;
import '../trading/recovery_link.dart';
import '../trading/trade_flows.dart';
import '../trading/trade_rules.dart' show heldKey;
import '../trading/trade_sheets.dart' show showOrderTicket;
import '../trading/trade_text.dart';
import '../trading/trade_widgets.dart';
import '../trading/trades_data.dart';
import 'market_data.dart';
import 'market_kit.dart';
import 'market_widgets.dart';
import 'symbol_sheet.dart';
import 'watch_sheet.dart';

class MarketScreen extends StatefulWidget {
  const MarketScreen({super.key});

  /// How often the followed quotes are read again while the tab is in front.
  static const quoteEvery = Duration(seconds: 15);

  @override
  State<MarketScreen> createState() => _MarketScreenState();
}

/// A read that failed (each section tolerates its own failure).
class _Failed {
  const _Failed(this.error);
  final Object error;
}

Future<Object?> _attempt(Future<Object?> Function() read) async {
  try {
    return await read();
  } catch (e) {
    return _Failed(e);
  }
}

class _MarketScreenState extends State<MarketScreen>
    with WidgetsBindingObserver {
  List<MarketConnection>? _connections;
  Object? _connectionsError;
  String? _account;
  AccountSnapshot? _snapshot;
  Object? _snapshotError;
  List<MarketWatch> _watches = const [];
  List<CalendarEvent>? _calendar;
  Object? _calendarError;
  List<Opportunity> _opportunities = const [];
  List<JournalEntry> _journal = const [];
  List<ChartRef> _charts = const [];
  final Map<String, MarketQuote> _quotes = {};
  final Map<String, double> _changes = {};
  List<String> _symbols = const [];

  /// Symbols whose quote and day change were read for the current account.
  final Set<String> _marketsRead = {};

  bool _loaded = false;
  Object? _fatal;
  int _generation = 0;

  /// Paused or hidden by the system (the notification shade only makes it inactive).
  bool _background = false;
  bool _polling = false;
  Timer? _timer;
  Timer? _debounce;
  StreamSubscription<LonoraEvent>? _events;
  ValueListenable<TickerModeData>? _ticker;

  /// Parts an event made stale; read when the tab is in front again.
  final Set<MarketPart> _stale = {};

  final _watchesKey = GlobalKey();
  final _calendarKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_load());
    OrderDesk.instance.addListener(_onDesk);
    _timer = Timer.periodic(MarketScreen.quoteEvery, (_) {
      if (_visible) unawaited(_pollQuotes());
    });
    try {
      _events = realtime.events.listen(_onEvent);
    } catch (_) {
      // No realtime controller (previews): pull-to-refresh and the timer keep it fresh.
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Offstage in the tab stack (or under a pushed page) the ticker mode is off.
    final ticker = TickerMode.getValuesNotifier(context);
    if (!identical(ticker, _ticker)) {
      _ticker?.removeListener(_scheduleFlush);
      _ticker = ticker..addListener(_scheduleFlush);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    OrderDesk.instance.removeListener(_onDesk);
    _ticker?.removeListener(_scheduleFlush);
    _timer?.cancel();
    _debounce?.cancel();
    unawaited(_events?.cancel());
    super.dispose();
  }

  /// An order's state changed (sent, answered, released): its card says so.
  void _onDesk() {
    if (mounted) setState(() {});
  }

  /// In front: the app in the foreground and this tab shown.
  bool get _visible =>
      mounted && !_background && (_ticker?.value.enabled ?? true);

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused ||
          AppLifecycleState.hidden ||
          AppLifecycleState.detached:
        _background = true;
      case AppLifecycleState.resumed:
        if (!_background) return;
        _background = false;
        // Events may have gone by meanwhile: read the live parts again (not the calendar).
        _stale.addAll(MarketPart.values);
        _scheduleFlush();
      case AppLifecycleState.inactive:
        // The notification shade or the app switcher's peek: nothing was missed.
        break;
    }
  }

  void _onEvent(LonoraEvent e) {
    if (e.kind == 'market.quote_updated') {
      final p = e.payload;
      final quote = MarketQuote.fromJson(asQuote(p['quote']));
      if (p['connection_id'] != _account || !_symbols.contains(quote.symbol)) {
        return;
      }
      if (mounted && quote.supersedes(_quotes[quote.symbol])) {
        setState(() => _quotes[quote.symbol] = quote);
      }
      return;
    }
    final parts = marketPartsOf(e.kind);
    if (parts.isEmpty) return;
    _stale.addAll(parts);
    _scheduleFlush();
  }

  /// Reads the stale parts shortly, once the tab is in front.
  void _scheduleFlush() {
    if (!_visible || _stale.isEmpty) return;
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 800), () {
      if (mounted) unawaited(_flush());
    });
  }

  static Map<String, dynamic> asQuote(Object? v) =>
      v is Map ? v.cast<String, dynamic>() : const {};

  Iterable<Agent> get _agents =>
      StoreProvider.state<AppState>(context).shell.orderedAgents;

  /// Everything, the calendar included: first load, pull-to-refresh and retry.
  Future<void> _load() async {
    final gen = ++_generation;
    _stale.clear();
    final results = await Future.wait([
      _attempt(fetchMarketConnections),
      _attempt(fetchWatches),
      _attempt(fetchCalendar),
      _attempt(fetchOpportunities),
      _attempt(fetchChartRefs),
    ]);
    if (!mounted || gen != _generation) return;
    final failures = results.whereType<_Failed>().toList();
    if (failures.any((f) => f.error is SessionRequestCancelled)) return;
    if (failures.length == results.length) {
      setState(() {
        if (!_loaded) _fatal = failures.first.error;
      });
      if (_loaded && mounted) showErrorToast(context, failures.first.error);
      return;
    }
    T? ok<T>(int i) => results[i] is _Failed ? null : results[i] as T;
    setState(() {
      _fatal = null;
      _loaded = true;
      final connections = ok<List<MarketConnection>>(0);
      _connectionsError = results[0] is _Failed
          ? (results[0]! as _Failed).error
          : null;
      if (connections != null) _connections = connections;
      _watches = ok<List<MarketWatch>>(1) ?? _watches;
      final calendar = ok<List<CalendarEvent>>(2);
      _calendarError = results[2] is _Failed
          ? (results[2]! as _Failed).error
          : null;
      if (calendar != null) _calendar = calendar;
      _opportunities = ok<List<Opportunity>>(3) ?? _opportunities;
      _charts = ok<List<ChartRef>>(4) ?? _charts;
      _keepAccount();
    });
    await _loadAccount(gen);
  }

  /// Keeps the chosen account while it is listed and enabled, else picks the default one.
  /// True when the account changed.
  bool _keepAccount() {
    final list = _connections ?? const <MarketConnection>[];
    if (list.any((c) => c.id == _account && c.enabled)) return false;
    final next = defaultAccount(list, _agents);
    if (next == _account) return false;
    _account = next;
    _snapshot = null;
    _snapshotError = null;
    _quotes.clear();
    _changes.clear();
    _marketsRead.clear();
    return true;
  }

  /// Only the parts events made stale, never the calendar.
  Future<void> _flush() async {
    if (!_visible || !_loaded || _stale.isEmpty) return;
    final parts = {..._stale};
    _stale.clear();
    final gen = _generation;
    Future<void> read<T>(Future<T> Function() fetch, void Function(T) apply) =>
        fetch().then<void>(
          (value) {
            if (mounted && gen == _generation) setState(() => apply(value));
          },
          // What is shown stays; a pull-to-refresh says why a read fails.
          onError: (Object _) {},
        );
    await Future.wait([
      if (parts.contains(MarketPart.connections))
        read(fetchMarketConnections, (v) => _connections = v),
      if (parts.contains(MarketPart.watches))
        read(fetchWatches, (v) => _watches = v),
      if (parts.contains(MarketPart.opportunities))
        read(fetchOpportunities, (v) => _opportunities = v),
      if (parts.contains(MarketPart.charts))
        read(fetchChartRefs, (v) => _charts = v),
    ]);
    if (!mounted || gen != _generation) return;
    var changed = false;
    setState(() => changed = _keepAccount());
    if (changed) return _loadAccount(++_generation);
    if (parts.contains(MarketPart.account)) {
      await _loadAccount(gen, all: false);
    } else {
      setState(() => _symbols = _followed());
      await _loadMarkets(gen, all: false);
    }
    if (parts.contains(MarketPart.quotes)) await _pollQuotes();
  }

  /// The account's snapshot and order log, then its markets ([all]: every followed market's
  /// quote and day change again; otherwise only markets not read yet).
  Future<void> _loadAccount(int gen, {bool all = true}) async {
    final account = _account;
    if (account == null) {
      setState(() {
        _snapshot = null;
        _snapshotError = null;
        _journal = const [];
        _symbols = _followed();
      });
      return;
    }
    final results = await Future.wait([
      _attempt(() => fetchAccountSnapshot(account)),
      _attempt(() => fetchJournal(account)),
    ]);
    if (!mounted || gen != _generation) return;
    setState(() {
      final snap = results[0];
      if (snap is _Failed) {
        if (snap.error is! SessionRequestCancelled) _snapshotError = snap.error;
      } else {
        _snapshot = snap as AccountSnapshot?;
        _snapshotError = null;
      }
      final journal = results[1];
      if (journal is List<JournalEntry>) {
        _journal = [...journal]
          ..sort(
            (a, b) => (b.updatedAt ?? DateTime(0)).compareTo(
              a.updatedAt ?? DateTime(0),
            ),
          );
      }
      _symbols = _followed();
    });
    await _settleOrders(account, results[0], results[1]);
    await _loadMarkets(gen, all: all);
  }

  /// Releases the held order identities the fresh journal settled, and those of tickets the
  /// fresh account no longer lists.
  Future<void> _settleOrders(
    String account,
    Object? snapshot,
    Object? journal,
  ) async {
    final scope = _scope;
    if (scope == null || journal is! List<JournalEntry>) return;
    final desk = OrderDesk.instance;
    await desk.settle(scope, account, journal);
    if (snapshot is AccountSnapshot) {
      await desk.dropGone(scope, account, snapshot, journal);
    }
  }

  String? get _scope =>
      orderScope(StoreProvider.state<AppState>(context, notify: false).session);

  /// The current account as the order flows see it.
  TradeAccount? get _tradeAccount {
    final scope = _scope;
    final connection = _connection;
    if (scope == null || connection == null) return null;
    return TradeAccount(
      scope: scope,
      id: connection.id,
      label: _accountLabel(connection),
      simulation: connection.isSimulation,
      snapshot: _snapshot,
      recovery: connection.recovery,
      journal: _journal,
    );
  }

  /// After an order: the account and its order log again.
  void _ordersChanged() {
    if (mounted) unawaited(_loadAccount(_generation, all: false));
  }

  void _openRecovery() {
    final account = _account;
    unawaited(context.push(recoveryLocation(account: account)));
  }

  /// A position's actions: «تعديل الوقف والهدف», «إغلاق الصفقة» (or «تحقق من نتيجة الإغلاق»
  /// while a close is held), and its market. Each order passes its review.
  Future<void> _positionMenu(MarketPosition p) async {
    final a = _tradeAccount;
    if (a == null) return _openSymbol(p.symbol);
    await OrderDesk.instance.load(a.scope);
    if (!mounted) return;
    final l10n = context.l10n;
    final state = positionState(a, p);
    // While the broker refuses trading, only a held close or edit can still be checked.
    final edit = !state.busy && (!a.notAllowed || state.editHeld);
    final close = !state.busy && (!a.notAllowed || state.closeHeld);
    final action = await showLnActionMenu<String>(
      context,
      title: '${ltr(p.symbol)} · ${sideWord(l10n, p.side)} ${ltr(p.volume)}',
      actions: [
        LnMenuAction(
          label: l10n.t('tr_editStopTarget'),
          icon: FIcons.shieldCheck,
          value: 'edit',
          enabled: edit,
        ),
        LnMenuAction(
          label: l10n.t(
            state.closeHeld ? 'tr_checkCloseResult' : 'tr_closeTrade',
          ),
          icon: FIcons.circleX,
          value: 'close',
          destructive: true,
          enabled: close,
        ),
        LnMenuAction(
          label: l10n.t('tr_viewMarket'),
          icon: FIcons.chartLine,
          value: 'market',
        ),
      ],
    );
    if (action == null || !mounted) return;
    switch (action) {
      case 'edit':
        await editStopTarget(context, a, p, onDone: _ordersChanged);
      case 'close':
        await confirmClose(context, a, p, onDone: _ordersChanged);
      default:
        await _openSymbol(p.symbol);
    }
  }

  /// A pending order's actions: «إلغاء الأمر» (or «تحقق من نتيجة الإلغاء»), and its market.
  Future<void> _orderMenu(MarketOrder o) async {
    final a = _tradeAccount;
    if (a == null) return _openSymbol(o.symbol);
    await OrderDesk.instance.load(a.scope);
    if (!mounted) return;
    final l10n = context.l10n;
    final state = orderCardState(a, o);
    final action = await showLnActionMenu<String>(
      context,
      title:
          '${ltr(o.symbol)} · ${orderKindWord(l10n, o.side)} ${ltr(o.volume)}',
      actions: [
        LnMenuAction(
          label: l10n.t(state.held ? 'tr_checkCancelResult' : 'tr_cancelOrder'),
          icon: FIcons.circleX,
          value: 'cancel',
          destructive: true,
          enabled: !state.blocked,
        ),
        LnMenuAction(
          label: l10n.t('tr_viewMarket'),
          icon: FIcons.chartLine,
          value: 'market',
        ),
      ],
    );
    if (action == null || !mounted) return;
    if (action == 'cancel') {
      await confirmCancel(context, a, o, onDone: _ordersChanged);
    } else {
      await _openSymbol(o.symbol);
    }
  }

  List<String> _followed() {
    final account = _account;
    if (account == null) return const [];
    return followedSymbols(
      accountId: account,
      positions: _snapshot?.positions ?? const [],
      agents: _agents,
      watches: _watches,
      opportunities: _opportunities,
      charts: _charts,
    );
  }

  /// The quote and the day's change (two daily candles) of the followed markets: all of
  /// them once per load, or ([all] false) those not read yet for this account.
  Future<void> _loadMarkets(int gen, {required bool all}) async {
    final account = _account;
    if (account == null) return;
    final symbols = [
      for (final s in _symbols)
        if (all || !_marketsRead.contains(s)) s,
    ];
    if (symbols.isEmpty) return;
    _marketsRead.addAll(symbols);
    await Future.wait([
      for (final symbol in symbols) ...[
        _attempt(() => fetchQuote(account, symbol)).then((q) {
          if (q is MarketQuote && mounted && gen == _generation) {
            _showQuote(symbol, q);
          }
        }),
        _attempt(() => fetchCandles(account, symbol, timeframe: '1d', limit: 2))
            .then((k) {
              if (k is List<MarketCandle> && mounted && gen == _generation) {
                final change = closeChange(k);
                if (change != null) setState(() => _changes[symbol] = change);
              }
            }),
      ],
    ]);
  }

  /// Reads the followed quotes again; a tick is skipped while the previous one still runs.
  Future<void> _pollQuotes() async {
    final account = _account;
    if (account == null || _symbols.isEmpty || _polling) return;
    _polling = true;
    final gen = _generation;
    try {
      await Future.wait([
        for (final symbol in _symbols)
          _attempt(() => fetchQuote(account, symbol)).then((q) {
            if (q is MarketQuote && mounted && gen == _generation) {
              _showQuote(symbol, q);
            }
          }),
      ]);
    } finally {
      _polling = false;
    }
  }

  /// A read quote replaces the shown one unless that one was observed later (a streamed
  /// quote may have overtaken the read).
  void _showQuote(String symbol, MarketQuote q) {
    if (q.supersedes(_quotes[symbol], orSame: true)) {
      setState(() => _quotes[symbol] = q);
    }
  }

  /// Labels count over every connection, as the Web and the Expo app number them.
  String _accountLabel(MarketConnection c) => brokerAccountLabel(
    context.l10n,
    c.raw,
    (_connections ?? const <MarketConnection>[]).indexOf(c),
  );

  MarketConnection? get _connection {
    for (final c in _connections ?? const <MarketConnection>[]) {
      if (c.id == _account) return c;
    }
    return null;
  }

  Future<void> _pickAccount() async {
    final list = _connections;
    if (list == null) return;
    final chosen = await showAccountPicker(
      context,
      connections: list,
      selected: _account,
      label: (c, i) => brokerAccountLabel(context.l10n, c.raw, i),
    );
    if (chosen == null || chosen == _account || !mounted) return;
    setState(() {
      _account = chosen;
      _snapshot = null;
      _snapshotError = null;
      _quotes.clear();
      _changes.clear();
      _marketsRead.clear();
    });
    await _loadAccount(++_generation);
  }

  Future<void> _search() async {
    final account = _account;
    if (account == null) return;
    final symbol = await showSymbolSearch(context, accountId: account);
    if (symbol != null && mounted) await _openSymbol(symbol);
  }

  Future<void> _openSymbol(String symbol) async {
    final account = _account;
    if (account == null) return;
    String? chartId;
    for (final c in _charts) {
      if (c.accountId == account && c.symbol == symbol) {
        chartId = c.id;
        break;
      }
    }
    final result = await showSymbolSheet(
      context,
      accountId: account,
      symbol: symbol,
      positions: _snapshot?.positions ?? const [],
      chartId: chartId,
      agents: [
        for (final a in _agents)
          if (a.tradingAccountId == account && a.tradingSymbol == symbol) a,
      ],
      quote: _quotes[symbol],
      change: _changes[symbol],
    );
    if (!mounted || result == null) return;
    switch (result) {
      case OpenChartResult(:final chartId):
        unawaited(context.push(Routes.charts(chartId: chartId)));
      case CreateChartResult():
        try {
          final chart = await createChart(
            accountId: account,
            symbol: symbol,
            timeframe: '1h',
          );
          if (mounted) {
            unawaited(context.push(Routes.charts(chartId: chart.id)));
          }
        } catch (e) {
          if (mounted) showErrorToast(context, e);
        }
      case CreateWatchResult():
        final traders = [
          for (final a in _agents)
            if (a.tradingAccountId == account && a.tradingSymbol == symbol) a,
        ];
        final watch = await showCreateWatchSheet(
          context,
          accountId: account,
          symbol: symbol,
          positions: [
            for (final p in _snapshot?.positions ?? const <MarketPosition>[])
              if (p.symbol == symbol) p,
          ],
          agents: [
            for (final a in _agents)
              if (!a.paused) a,
          ],
          preferredAgent: traders.firstOrNull?.id,
        );
        if (watch != null && mounted) {
          setState(() => _watches = [watch, ..._watches]);
          LnToast.show(
            context,
            context.t('mk_watchCreated'),
            kind: LnToastKind.positive,
          );
        }
      case OpenTicketResult():
        await showOrderTicket(
          context,
          connections: _connections ?? const [],
          accountId: account,
          symbol: symbol,
          label: _accountLabel,
          onChanged: _ordersChanged,
        );
      case OpenAgentResult(:final agent):
        await _openAgent(agent.id);
    }
  }

  Future<void> _openAgent(String agentId) async {
    final ensure = EnsureAgentThreadAction(agentId);
    await context.dispatchAndWait(ensure);
    if (!mounted) return;
    final id = ensure.threadId;
    if (ensure.status.originalError != null || id == null) {
      showErrorToast(context, ensure.status.originalError ?? 'request_failed');
      return;
    }
    context.go(Routes.thread(id));
  }

  void _openThread(String? threadId, {int? around}) {
    if (threadId == null || threadId.isEmpty) return;
    context.go(Routes.thread(threadId, around: around));
  }

  Future<void> _watchMenu(MarketWatch w) async {
    final l10n = context.l10n;
    final action = await showLnActionMenu<String>(
      context,
      title: watchCondition(w.summary, l10n.lang),
      actions: [
        if (w.threadId != null)
          LnMenuAction(
            label: l10n.t('openConversation'),
            icon: FIcons.messageCircle,
            value: 'open',
          ),
        if (!w.ended)
          w.paused
              ? LnMenuAction(
                  label: l10n.t('resume'),
                  icon: FIcons.play,
                  value: 'resume',
                )
              : LnMenuAction(
                  label: l10n.t('pause'),
                  icon: FIcons.pause,
                  value: 'pause',
                ),
        if (w.extendable)
          LnMenuAction(
            label: l10n.t('mk_extendWatch'),
            icon: FIcons.clockPlus,
            value: 'extend',
          ),
        if (!w.ended)
          LnMenuAction(
            label: l10n.t('mk_cancelWatch'),
            icon: FIcons.circleX,
            value: 'cancel',
            destructive: true,
          ),
      ],
    );
    if (action == null || !mounted) return;
    if (action == 'open') return _openThread(w.threadId);
    if (action == 'cancel') {
      final ok = await showLnConfirm(
        context,
        title: l10n.t('mk_cancelWatchQ'),
        message: l10n.t('mk_cancelWatchBody'),
        confirmLabel: l10n.t('mk_cancelWatch'),
        cancelLabel: l10n.t('mk_keep'),
        destructive: true,
      );
      if (!ok || !mounted) return;
    }
    await _controlWatch(w, action);
  }

  /// Posts the owner's brake and shows the watch as the server returns it. A cancel can be
  /// undone from its toast: resuming a cancelled watch undoes the cancel (control_watch).
  Future<void> _controlWatch(MarketWatch w, String action) async {
    final l10n = context.l10n;
    try {
      final updated = await controlWatch(
        w.id,
        action,
        hours: action == 'extend' ? 2 : null,
      );
      if (!mounted) return;
      setState(() {
        _watches = [for (final x in _watches) x.id == w.id ? updated : x];
      });
      final done = switch (action) {
        'cancel' => 'mk_watchCancelled',
        'extend' => 'mk_watchExtended',
        'resume' => 'mk_watchResumed',
        _ => 'mk_watchPaused',
      };
      LnToast.show(
        context,
        l10n.t(done),
        kind: LnToastKind.positive,
        action: action == 'cancel'
            ? (l10n.t('sh_undo'), () => unawaited(_controlWatch(w, 'resume')))
            : null,
        duration: action == 'cancel'
            ? const Duration(seconds: 5)
            : LnToast.defaultDuration,
      );
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    }
  }

  void _reveal(GlobalKey key) {
    final target = key.currentContext;
    if (target == null) return;
    unawaited(
      Scrollable.ensureVisible(
        target,
        duration: LnMotion.slow,
        curve: LnMotion.standard,
      ),
    );
  }

  Future<void> _showCalendar() async {
    final events = _upcoming(all: true);
    await showLnSheet<void>(
      context,
      title: context.t('mk_calendar'),
      padding: EdgeInsets.zero,
      builder: (sheet) => ListView(
        shrinkWrap: true,
        children: [
          for (final e in events) CalendarRow(event: e, time: _eventTime(e)),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  List<CalendarEvent> _upcoming({bool all = false}) {
    final list = [...?_calendar]
      ..sort(
        (a, b) => (a.scheduledAt ?? DateTime(0)).compareTo(
          b.scheduledAt ?? DateTime(0),
        ),
      );
    if (all) return list;
    final since = DateTime.now().subtract(const Duration(hours: 2));
    final next = [
      for (final e in list)
        if (e.scheduledAt == null || e.scheduledAt!.isAfter(since)) e,
    ];
    return (next.isEmpty ? list.reversed.toList() : next).take(6).toList();
  }

  String _eventTime(CalendarEvent e) {
    final t = e.scheduledAt;
    if (t == null) return '—';
    String two(int v) => v.toString().padLeft(2, '0');
    // A date and time: in the date digits of the interface language.
    return dateDigits(
      '${t.day}/${t.month} ${two(t.hour)}:${two(t.minute)}',
      context.l10n.lang,
    );
  }

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    final ln = context.ln;
    final c = ln.colors;
    // Rebuild when the agents change (fixed markets, names on watches and opportunities).
    final agents = context.select((AppState s) => s.shell.agents);
    final bottom = FloatingTabBar.occupiedHeight(context) + LnSpace.xl;

    final Widget body;
    if (!_loaded && _fatal == null) {
      body = ListView(
        physics: const NeverScrollableScrollPhysics(),
        padding: EdgeInsets.only(bottom: bottom),
        children: [
          LargeTitleHeader(title: context.t('android_market')),
          const SizedBox(height: 64),
          ExploreSkeleton(
            semanticLabel: context.t('sh_loading'),
            animate: !_disableAnimations(context),
          ),
        ],
      );
    } else if (!_loaded) {
      body = ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.only(bottom: bottom),
        children: [
          LargeTitleHeader(title: context.t('android_market')),
          const SizedBox(height: 80),
          LoadFailure(
            error: _fatal!,
            onRetry: () {
              setState(() => _fatal = null);
              unawaited(_load());
            },
          ),
        ],
      );
    } else {
      body = ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.only(bottom: bottom),
        children: _content(context, agents),
      );
    }
    return ColoredBox(
      color: c.bg,
      child: LnRefresh(onRefresh: _load, child: body),
    );
  }

  bool _disableAnimations(BuildContext context) =>
      MediaQuery.maybeDisableAnimationsOf(context) ?? false;

  List<Widget> _content(BuildContext context, Map<String, Agent> agents) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final connection = _connection;
    final account = _account;
    final snapshot = _snapshot;
    String agentName(String? id) => id == null ? '' : (agents[id]?.name ?? '');

    final title = context.t('android_market');
    // The selector takes the width the title leaves: the header's own width less the gutters,
    // the title and a gap.
    final painter = TextPainter(
      text: TextSpan(text: title, style: ln.text.display),
      textDirection: Directionality.of(context),
      textScaler: MediaQuery.textScalerOf(context),
      maxLines: 1,
    )..layout();
    final titleWidth = painter.width;
    painter.dispose();
    final header = LayoutBuilder(
      builder: (context, constraints) => LargeTitleHeader(
        title: title,
        trailing: connection == null
            ? null
            : LnTappable(
                onTap: _pickAccount,
                haptic: true,
                semanticLabel:
                    '${context.t('mk_accountMenu')}: ${_accountLabel(connection)}',
                excludeChildSemantics: true,
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    maxWidth: math.max(
                      0,
                      constraints.maxWidth -
                          2 * LnSpace.pageGutter -
                          titleWidth -
                          LnSpace.md,
                    ),
                    minHeight: 48,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Flexible(
                        child: Text(
                          _accountLabel(connection),
                          textDirection: readingDirection(
                            _accountLabel(connection),
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: ln.text.body.copyWith(color: c.fg),
                        ),
                      ),
                      const SizedBox(width: 4),
                      Icon(FIcons.chevronDown, size: 18, color: c.fgMuted),
                    ],
                  ),
                ),
              ),
      ),
    );

    final search = Padding(
      padding: const EdgeInsetsDirectional.symmetric(
        horizontal: LnSpace.pageGutter,
      ),
      child: LnTappable(
        onTap: _search,
        semanticLabel: context.t('searchBrokerSymbols'),
        excludeChildSemantics: true,
        // A 44 dp pill inside a 48 dp touch target.
        child: Container(
          height: 48,
          alignment: Alignment.center,
          child: Container(
            height: 44,
            padding: const EdgeInsetsDirectional.symmetric(horizontal: 14),
            decoration: BoxDecoration(
              color: c.fill2,
              borderRadius: const BorderRadius.all(
                Radius.circular(LnRadius.stadium),
              ),
            ),
            child: Row(
              children: [
                Icon(FIcons.search, size: 18, color: c.fgMuted),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    context.t('searchBrokerSymbols'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: ln.text.body.copyWith(color: c.fgMuted),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    final accountTile = connection == null
        ? ExploreTile.wide(
            label: _connectionsError != null
                ? (errorMessage(context, _connectionsError!) ??
                      context.t('marketDataUnavailable'))
                : context.t('mk_linkAccount'),
            leading: const Icon(FIcons.link),
            color: c.selection,
            onTap: () => context.push(Routes.integrations),
          )
        : AccountTile(
            label: _accountLabel(connection),
            simulation: connection.isSimulation,
            snapshot: snapshot,
            error: snapshot == null && _snapshotError != null
                ? (errorMessage(context, _snapshotError!) ??
                      context.t('marketDataUnavailable'))
                : null,
            onTap: _pickAccount,
          );

    const gap = SizedBox(width: LnSpace.tileGap);
    final strip = SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsetsDirectional.symmetric(
        horizontal: LnSpace.pageGutter,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              accountTile,
              gap,
              LinkTile(
                label: context.t('charts'),
                icon: FIcons.chartCandlestick,
                color: c.brand,
                onTap: () => context.push(Routes.charts()),
              ),
              gap,
              LinkTile(
                label: context.t('mk_watches'),
                icon: FIcons.eye,
                color: c.attention,
                onTap: () => _reveal(_watchesKey),
              ),
              gap,
              LinkTile(
                label: context.t('mk_calendar'),
                icon: FIcons.calendarDays,
                color: c.warning,
                onTap: () => _reveal(_calendarKey),
              ),
            ],
          ),
          if (account != null) ...[
            const SizedBox(height: LnSpace.tileGap),
            Row(
              children: [
                if (_symbols.isEmpty)
                  ExploreTile(
                    label: context.t('mk_noSymbols'),
                    leading: const Icon(FIcons.search),
                    color: ln.opaque(c.fill2),
                    foreground: c.fg,
                    width: LnSize.wideTileWidth,
                    labelStyle: ln.text.caption.copyWith(color: c.fg),
                    onTap: _search,
                  )
                else
                  for (final s in _symbols) ...[
                    SymbolTile(
                      symbol: s,
                      quote: _quotes[s],
                      change: _changes[s],
                      onTap: () => _openSymbol(s),
                    ),
                    gap,
                  ],
              ],
            ),
          ],
        ],
      ),
    );

    final recovery = connection?.recovery;
    final children = <Widget>[
      header,
      const SizedBox(height: LnSpace.xs),
      if (account != null) ...[search, const SizedBox(height: LnSpace.md)],
      strip,
      if (connection?.isSimulation ?? false)
        Footnote(context.t('mk_simulationNote'), icon: FIcons.flaskConical),
      // The account is not connected: «التعطل والاستعادة» says why and offers a retry.
      if (recovery != null && recovery.down)
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.pageGutter,
            LnSpace.sm,
            LnSpace.pageGutter,
            0,
          ),
          child: TradeNotice(
            title: context.t('rc_dropped'),
            text:
                '${context.t('rc_state')}: ${recoveryStatusName(l10n, recovery.status)}',
            icon: FIcons.unplug,
            onTap: _openRecovery,
            linkLabel: context.t('rc_title'),
          ),
        ),
    ];

    Widget cards(List<Widget> items) => Padding(
      padding: const EdgeInsetsDirectional.symmetric(
        horizontal: LnSpace.pageGutter,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (i, w) in items.indexed) ...[
            if (i > 0) const SizedBox(height: LnSpace.xs),
            w,
          ],
        ],
      ),
    );
    Widget section(String title, {Key? key, VoidCallback? onTap}) => Padding(
      key: key,
      padding: const EdgeInsets.only(top: 27, bottom: 8),
      child: SectionHeader(title: title, onTap: onTap),
    );

    // Positions and pending orders, with the owner's own orders (each one reviewed first).
    final trade = _tradeAccount;
    String? outcomeLine(String? key) {
      if (trade == null || key == null) return null;
      final o = OrderDesk.instance.outcome(trade.scope, key, _journal);
      return o == null
          ? null
          : operationStatusText(o.status, o.details, l10n.lang);
    }

    if (snapshot != null) {
      final positions = snapshot.positions;
      children.add(section(context.t('mk_positions')));
      final paused = trade == null
          ? null
          : pausedNotice(context, trade, onRecovery: _openRecovery);
      if (paused != null) {
        children.add(
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(
              LnSpace.pageGutter,
              0,
              LnSpace.pageGutter,
              LnSpace.xs,
            ),
            child: paused,
          ),
        );
      }
      if (positions.isEmpty) {
        children.add(Footnote(context.t('mk_noPositions'), underHeader: true));
      } else {
        children.add(
          cards([
            for (final p in positions)
              RecommendationCard(
                leading: CardIcon(
                  p.isSell ? FIcons.trendingDown : FIcons.trendingUp,
                  color: p.isSell ? c.negative : c.positive,
                ),
                title:
                    '${ltr(p.symbol)} · ${context.t(p.isSell ? 'mk_sell' : 'mk_buy')} ${ltr(p.volume)}',
                subtitle: [
                  '${context.t('mk_openPrice')} ${ltr(marketNumber(p.openPrice))}',
                  if (p.profit != null)
                    '${context.t('mk_profit')} ${ltr('${signedMoney(p.profit!)} ${snapshot.currency}')}',
                  ?outcomeLine(
                    trade == null
                        ? null
                        : OrderDesk.instance.lastOn(
                            trade.scope,
                            positionCard(trade.id, p.id),
                          ),
                  ),
                ].join(dotSeparator),
                onTap: () => _positionMenu(p),
              ),
          ]),
        );
      }
      if (snapshot.orders.isNotEmpty) {
        children
          ..add(section(context.t('mk_pendingOrders')))
          ..add(
            cards([
              for (final o in snapshot.orders)
                RecommendationCard(
                  leading: CardIcon(
                    FIcons.clock,
                    color: o.isSell ? c.negative : c.positive,
                  ),
                  title:
                      '${ltr(o.symbol)} · ${tradeActionText(l10n.lang)[o.side] ?? context.t(o.isSell ? 'mk_sell' : 'mk_buy')} ${ltr(o.volume)}',
                  subtitle: [
                    '${context.t('orderPrice')} ${ltr(marketNumber(o.price))}',
                    ?outcomeLine(
                      trade == null
                          ? null
                          : heldKey('cancel_order', trade.id, o.id),
                    ),
                  ].join(dotSeparator),
                  onTap: () => _orderMenu(o),
                ),
            ]),
          );
      }
      children.add(
        Footnote(context.t('tr_confirmNote'), icon: FIcons.shieldCheck),
      );
    }

    // Opportunities that still stand.
    final opportunities = [
      for (final o in _opportunities)
        if (o.live) o,
    ];
    if (opportunities.isNotEmpty) {
      children
        ..add(section(context.t('mk_opportunities')))
        ..add(
          cards([
            for (final o in opportunities)
              RecommendationCard(
                leading: CardIcon(
                  FIcons.sparkles,
                  color: o.status == 'confirmed' ? c.positive : c.brand,
                ),
                title: '${ltr(o.symbol)} · ${ltr(o.timeframe)}',
                subtitle: [
                  context.t('mk_opp_${o.status}'),
                  if (agentName(o.agentId).isNotEmpty)
                    isolate(agentName(o.agentId)),
                ].join(dotSeparator),
                onTap: o.threadId == null
                    ? null
                    : () => _openThread(o.threadId),
              ),
          ]),
        );
    }

    // Watches (the owner's brake: pause, resume, cancel).
    final watches = [
      for (final w in _watches)
        if (!w.ended) w,
    ];
    children.add(section(context.t('mk_watches'), key: _watchesKey));
    if (watches.isEmpty) {
      children.add(Footnote(context.t('nothingKnown'), underHeader: true));
    } else {
      final now = DateTime.now();
      children.add(
        cards([
          for (final w in watches)
            RecommendationCard(
              leading: CardIcon(
                w.paused ? FIcons.pause : FIcons.eye,
                color: w.paused ? c.fgMuted : c.attention,
              ),
              title: watchCondition(w.summary, l10n.lang),
              subtitle: [
                if (agentName(w.agentId).isNotEmpty)
                  isolate(agentName(w.agentId)),
                if (w.paused) context.t('live_paused'),
                watchUntil(w.summary, l10n.lang, now),
              ].join(dotSeparator),
              onTap: () => _watchMenu(w),
            ),
        ]),
      );
    }

    // Economic calendar.
    final upcoming = _upcoming();
    final more = (_calendar?.length ?? 0) > upcoming.length;
    children.add(
      section(
        context.t('mk_calendar'),
        key: _calendarKey,
        onTap: more ? _showCalendar : null,
      ),
    );
    if (_calendarError != null && _calendar == null) {
      children.add(
        Footnote(
          errorMessage(context, _calendarError!) ??
              context.t('marketDataUnavailable'),
          icon: FIcons.triangleAlert,
          underHeader: true,
        ),
      );
    } else if (upcoming.isEmpty) {
      children.add(Footnote(context.t('mk_calendarEmpty'), underHeader: true));
    } else {
      children.addAll([
        for (final e in upcoming) CalendarRow(event: e, time: _eventTime(e)),
      ]);
    }

    // Order log (read-only).
    if (_journal.isNotEmpty) {
      children
        ..add(section(context.t('mk_orderLog')))
        ..add(
          cards([
            for (final j in _journal.take(5))
              () {
                final action = orderLineAction(j.request, l10n.lang);
                return RecommendationCard(
                  leading: CardIcon(
                    action.direction == 'down'
                        ? FIcons.arrowDownRight
                        : action.direction == 'up'
                        ? FIcons.arrowUpRight
                        : FIcons.receipt,
                    color: action.direction == 'down'
                        ? c.negative
                        : action.direction == 'up'
                        ? c.positive
                        : c.fgMuted,
                  ),
                  title: [
                    action.label,
                    ltr(j.symbol),
                    if (action.volume != null) ltr(action.volume!),
                  ].join(' '),
                  subtitle: [
                    operationStatusText(j.status, j.details, l10n.lang),
                    if (j.updatedAt != null)
                      ltr(_shortTime(j.updatedAt!, l10n.lang)),
                  ].join(dotSeparator),
                  onTap: j.threadId == null
                      ? null
                      : () => _openThread(j.threadId, around: j.timelineSeq),
                );
              }(),
          ]),
        );
    }
    return children;
  }

  /// «27/11 14:05» in [lang]'s date digits.
  static String _shortTime(DateTime t, String lang) {
    String two(int v) => v.toString().padLeft(2, '0');
    return dateDigits(
      '${t.day}/${t.month} ${two(t.hour)}:${two(t.minute)}',
      lang,
    );
  }
}
