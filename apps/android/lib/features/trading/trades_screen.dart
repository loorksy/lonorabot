// «الصفقات» (Routes.agentTrades): the agent's open positions with the owner's own «تعديل الوقف
// والهدف» and «إغلاق الصفقة», its pending orders with «إلغاء الأمر», then «سجل الأوامر» from
// the journal (apps/web shell/agent/TradesPage.tsx; the pending orders as
// components/trading/Orders.tsx). Every order passes a review the owner confirms
// (trade_flows.dart); nothing here sends on its own.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
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
import '../../state/app_state.dart';
import '../../state/realtime.dart';
import '../market/market_data.dart';
import '../market/market_kit.dart';
import '../settings/settings_common.dart' show LnRefresh, errorMessage;
import 'recovery_link.dart';
import 'trade_flows.dart';
import 'trade_widgets.dart';
import 'trades_data.dart';
import 'trading_strings.dart';

class TradesScreen extends StatefulWidget {
  const TradesScreen({super.key, required this.agentId});

  final String agentId;

  @override
  State<TradesScreen> createState() => _TradesScreenState();
}

class _TradesScreenState extends State<TradesScreen> {
  List<MarketConnection>? _connections;
  AccountSnapshot? _snapshot;
  Object? _snapshotError;
  List<JournalEntry>? _journal;
  Object? _journalError;
  int _generation = 0;
  Timer? _debounce;
  StreamSubscription<LonoraEvent>? _events;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_load()));
    try {
      _events = realtime.events.listen(_onEvent);
    } catch (_) {
      // No realtime controller (previews): pull-to-refresh keeps it fresh.
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    unawaited(_events?.cancel());
    super.dispose();
  }

  AppState get _state => StoreProvider.state<AppState>(context, notify: false);

  Agent? get _agent => _state.shell.agents[widget.agentId];

  String? get _scope => orderScope(_state.session);

  /// A trading, operation, receipt or broker event: the account and the journal again.
  void _onEvent(LonoraEvent e) {
    final parts = marketPartsOf(e.kind);
    if (!parts.contains(MarketPart.account) &&
        !parts.contains(MarketPart.connections)) {
      return;
    }
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 800), () {
      if (mounted) unawaited(_load());
    });
  }

  Future<void> _load() async {
    if (!mounted) return;
    final gen = ++_generation;
    final account = _agent?.tradingAccountId ?? '';
    final scope = _scope;
    Future<T?> attempt<T>(
      Future<T> Function() read,
      void Function(Object) failed,
    ) async {
      try {
        return await read();
      } on SessionRequestCancelled {
        return null;
      } catch (e) {
        if (mounted && gen == _generation) setState(() => failed(e));
        return null;
      }
    }

    final results = await Future.wait<Object?>([
      attempt(fetchMarketConnections, (_) {}),
      if (account.isNotEmpty) ...[
        attempt(() => fetchAccountSnapshot(account), (e) => _snapshotError = e),
        attempt(() => fetchJournal(account), (e) => _journalError = e),
      ],
      if (scope != null) OrderDesk.instance.load(scope),
    ]);
    if (!mounted || gen != _generation) return;
    final connections = results[0] as List<MarketConnection>?;
    final snapshot = account.isEmpty ? null : results[1] as AccountSnapshot?;
    final journal = account.isEmpty ? null : results[2] as List<JournalEntry>?;
    setState(() {
      if (connections != null) _connections = connections;
      if (snapshot != null) {
        _snapshot = snapshot;
        _snapshotError = null;
      }
      if (journal != null) {
        _journal = journal;
        _journalError = null;
      }
    });
    if (scope == null || account.isEmpty || journal == null) return;
    await OrderDesk.instance.settle(scope, account, journal);
    if (snapshot != null) {
      await OrderDesk.instance.dropGone(scope, account, snapshot, journal);
    }
  }

  void _openRecovery(String account) =>
      unawaited(context.push(recoveryLocation(account: account)));

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    ensureTradingStrings(context);
    final l10n = context.l10n;
    final agent = context.select(
      (AppState s) => s.shell.agents[widget.agentId],
    );
    final loaded = context.select((AppState s) => s.shell.loaded);
    final scope = context.select((AppState s) => orderScope(s.session));
    final Widget body;
    if (agent == null || scope == null) {
      body = loaded
          ? EmptyState(icon: FIcons.userX, title: l10n.t('agentMissing'))
          : SkeletonRows(count: 4, semanticLabel: l10n.t('sh_loading'));
    } else if ((agent.tradingAccountId ?? '').isEmpty) {
      body = EmptyState(
        icon: FIcons.folder,
        title: l10n.t(
          (_connections ?? const []).isNotEmpty
              ? 'tr_noAccountChosen'
              : 'mk_linkAccount',
        ),
      );
    } else {
      body = LnRefresh(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(
            bottom: LnSpace.xxl + MediaQuery.paddingOf(context).bottom,
          ),
          children: _content(context, agent, scope),
        ),
      );
    }
    return PushedPage(
      title: l10n.t('tr_title'),
      fallback: Routes.agent(widget.agentId),
      body: body,
    );
  }

  List<Widget> _content(BuildContext context, Agent agent, String scope) {
    final l10n = context.l10n;
    final accountId = agent.tradingAccountId!;
    final connections = _connections ?? const <MarketConnection>[];
    final index = connections.indexWhere((c) => c.id == accountId);
    final connection = index < 0 ? null : connections[index];
    final a = TradeAccount(
      scope: scope,
      id: accountId,
      label: connection == null
          ? l10n.t('unverifiedBrokerAccount')
          : brokerAccountLabel(l10n, connection.raw, index),
      simulation: connection?.isSimulation ?? false,
      snapshot: _snapshot,
      recovery: connection?.recovery,
      journal: _journal,
    );
    final symbol = agent.tradingSymbol;
    bool mine(String s) => symbol == null || symbol.isEmpty || s == symbol;
    Widget gutter(Widget child) => Padding(
      padding: const EdgeInsetsDirectional.symmetric(
        horizontal: LnSpace.pageGutter,
      ),
      child: child,
    );
    Widget section(String title) => Padding(
      padding: const EdgeInsets.only(top: 27, bottom: 8),
      child: SectionHeader(title: title),
    );
    Widget alert(Object error) => Semantics(
      liveRegion: true,
      child: Footnote(
        errorMessage(context, error) ?? l10n.t('request_failed'),
        icon: FIcons.circleAlert,
      ),
    );
    final skeleton = SkeletonRows(
      count: 2,
      semanticLabel: l10n.t('sh_loading'),
      animate: !(MediaQuery.maybeDisableAnimationsOf(context) ?? false),
    );
    void reload() => unawaited(_load());

    final out = <Widget>[];
    final paused = pausedNotice(
      context,
      a,
      onRecovery: () => _openRecovery(accountId),
    );
    if (paused != null) {
      out
        ..add(gutter(paused))
        ..add(const SizedBox(height: LnSpace.sm));
    }
    final snapshot = _snapshot;
    if (snapshot == null) {
      out.add(_snapshotError != null ? alert(_snapshotError!) : skeleton);
    } else {
      final positions = [
        for (final p in snapshot.positions)
          if (mine(p.symbol)) p,
      ];
      if (positions.isEmpty) {
        out.add(
          EmptyState(icon: FIcons.folder, title: l10n.t('tr_noOpenTrade')),
        );
      } else {
        for (final (i, p) in positions.indexed) {
          if (i > 0) out.add(const SizedBox(height: LnSpace.xs));
          out.add(
            gutter(
              PositionCard(
                key: ValueKey('position:${p.id}'),
                account: a,
                position: p,
                onChanged: reload,
              ),
            ),
          );
        }
      }
      final orders = [
        for (final o in snapshot.orders)
          if (mine(o.symbol)) o,
      ];
      out.add(section(l10n.t('mk_pendingOrders')));
      if (orders.isEmpty) {
        out.add(Footnote(l10n.t('tr_noPendingOrders'), underHeader: true));
      } else {
        for (final (i, o) in orders.indexed) {
          if (i > 0) out.add(const SizedBox(height: LnSpace.xs));
          out.add(
            gutter(
              PendingOrderCard(
                key: ValueKey('order:${o.id}'),
                account: a,
                order: o,
                onChanged: reload,
              ),
            ),
          );
        }
      }
    }

    out.add(section(l10n.t('mk_orderLog')));
    final journal = _journal;
    if (journal == null) {
      out.add(_journalError != null ? alert(_journalError!) : skeleton);
    } else {
      final rows =
          [
            for (final e in journal)
              if (e.agentId == agent.id) e,
          ]..sort(
            (x, y) => (y.updatedAt ?? DateTime(0)).compareTo(
              x.updatedAt ?? DateTime(0),
            ),
          );
      if (rows.isEmpty) {
        out.add(Footnote(l10n.t('tr_noOrders'), underHeader: true));
      } else {
        out.add(
          gutter(
            Container(
              decoration: BoxDecoration(
                color: context.ln.colors.fill1,
                borderRadius: const BorderRadius.all(
                  Radius.circular(LnRadius.card),
                ),
              ),
              child: Column(
                children: [
                  for (final e in rows)
                    OrderLogRow(key: ValueKey(e.operationId), entry: e),
                ],
              ),
            ),
          ),
        );
      }
    }
    out.add(Footnote(l10n.t('tr_filledNote'), icon: FIcons.info));
    return out;
  }
}
