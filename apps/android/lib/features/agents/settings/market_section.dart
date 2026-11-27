// The agent's market scope (apps/mobile/components/agent-market-picker.tsx and
// broker-pair-picker.tsx, packages/core/src/agent-scope.ts): keep the current fixed market, a
// general agent, or a default market (an account and one of its symbols). Saving is the
// server's scope change with its revision (`PATCH /agents/{id}`); it never changes the trading
// mode. Shown for root team agents only (not Lonora, not a delegated agent).
import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../app/services.dart';
import '../../../core/api/api_error.dart';
import '../../../core/broker_identity.dart';
import '../../../core/json.dart';
import '../../../core/models/models.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../../state/actions/shell_actions.dart';
import '../../settings/settings_common.dart';
import '../profile/agent_data.dart';
import '../profile/agent_page.dart';

enum MarketMode { fixed, general, market }

/// packages/core/src/agent-scope.ts `agentMarketMode`.
MarketMode agentMarketMode(Agent agent) =>
    agent.scopeMode != 'flexible' && agent.role != 'personal'
    ? MarketMode.fixed
    : (agent.tradingAccountId ?? '').isNotEmpty
    ? MarketMode.market
    : MarketMode.general;

/// packages/core/src/agent-scope.ts `marketScopeChange`: the PATCH fields of a scope change,
/// empty when nothing changes.
Json marketScopeChange(
  MarketMode mode,
  String account,
  String symbol,
  Agent current,
) {
  if (mode == MarketMode.fixed) return {};
  String? orNull(String? v) => v == null || v.isEmpty ? null : v;
  final change = {
    'scope_mode': 'flexible',
    'trading_account_id': mode == MarketMode.market ? account : null,
    'trading_symbol': mode == MarketMode.market ? symbol : null,
    'expected_scope_revision': current.scopeRevision,
  };
  if (current.scopeMode == 'flexible' &&
      orNull(current.tradingAccountId) == change['trading_account_id'] &&
      orNull(current.tradingSymbol) == change['trading_symbol']) {
    return {};
  }
  return change;
}

/// Whether the agent may change its market scope here.
bool offersMarketScope(Agent agent) =>
    (agent.parentId ?? '').isEmpty &&
    agent.role != 'personal' &&
    agent.role != 'delegated';

class MarketSection extends StatefulWidget {
  const MarketSection({super.key, required this.agent, this.dirty});

  final Agent agent;

  /// Set to whether an unsaved scope change is drafted (the page asks before leaving).
  final ValueNotifier<bool>? dirty;

  @override
  State<MarketSection> createState() => _MarketSectionState();
}

class _MarketSectionState extends State<MarketSection>
    with AutomaticKeepAliveClientMixin {
  /// Kept while scrolled out of the page's list, so a draft is not lost.
  @override
  bool get wantKeepAlive => true;

  late MarketMode _mode = agentMarketMode(widget.agent);
  late final bool _allowFixed = _mode == MarketMode.fixed;
  late String _account = widget.agent.tradingAccountId ?? '';
  late String _symbol = widget.agent.tradingSymbol ?? '';
  List<Json>? _connections;
  Object? _connectionsError;
  List<String>? _symbols;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _loadConnections();
    if (_account.isNotEmpty) _loadSymbols(_account);
  }

  Future<void> _loadConnections() async {
    if (_connectionsError != null) setState(() => _connectionsError = null);
    try {
      final rows = asJsonList(await api.get('/trading/connections'));
      if (mounted) {
        setState(
          () => _connections = rows
              .where((r) => asJson(r['payload'])['enabled'] == true)
              .toList(),
        );
      }
    } catch (error) {
      // A failed read is not «no broker»: its words and a retry.
      if (error is! SessionRequestCancelled && mounted) {
        setState(() => _connectionsError = error);
      }
    }
  }

  Future<void> _loadSymbols(String account) async {
    setState(() => _symbols = null);
    try {
      final rows = await api.get(
        '/market/symbols',
        query: {'account_id': account},
      );
      if (mounted && account == _account) {
        setState(() => _symbols = [for (final s in rows as List) '$s']);
      }
    } catch (error) {
      // Only the account still chosen: a late failure of an earlier one changes nothing.
      if (mounted && account == _account) {
        setState(() => _symbols = const []);
        showErrorToast(context, error);
      }
    }
  }

  Future<void> _chooseAccount() async {
    final l10n = context.l10n;
    final rows = _connections ?? const [];
    final chosen = await showLnSheet<String>(
      context,
      title: l10n.t('brokerAccount'),
      builder: (sheet) => SingleChildScrollView(
        child: LnSection(
          padding: EdgeInsets.zero,
          children: [
            for (final (i, row) in rows.indexed)
              ChoiceTile(
                title: brokerAccountLabel(l10n, row, i),
                selected: row['id'] == _account,
                onSelect: () => Navigator.of(sheet).pop(asStr(row['id'])),
              ),
          ],
        ),
      ),
    );
    if (chosen == null || chosen == _account || !mounted) return;
    setState(() => (_account = chosen, _symbol = ''));
    await _loadSymbols(chosen);
  }

  Future<void> _chooseSymbol() async {
    final l10n = context.l10n;
    final all = _symbols ?? const <String>[];
    final chosen = await showLnSheet<String>(
      context,
      title: l10n.t('chooseTradingPair'),
      builder: (sheet) => _SymbolPicker(symbols: all, selected: _symbol),
    );
    if (chosen != null && mounted) setState(() => _symbol = chosen);
  }

  Future<void> _save(Json change) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final updated = await patchAgent(widget.agent.id, change);
      if (!mounted) return;
      context.dispatch(UpsertAgentAction(updated));
      LnToast.show(
        context,
        context.t('ag_marketSaved'),
        kind: LnToastKind.positive,
      );
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final l10n = context.l10n;
    final c = context.ln.colors;
    final rows = _connections;
    final accountIndex = rows?.indexWhere((r) => r['id'] == _account) ?? -1;
    final change = marketScopeChange(_mode, _account, _symbol, widget.agent);
    final complete =
        _mode != MarketMode.market ||
        (_account.isNotEmpty && _symbol.isNotEmpty);
    final dirty = change.isNotEmpty;
    final notifier = widget.dirty;
    if (notifier != null && notifier.value != dirty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) notifier.value = dirty;
      });
    }
    final error = _connectionsError;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        LnSection(
          title: l10n.t('agentMarketScope'),
          footer: l10n.t(
            _mode == MarketMode.fixed
                ? 'keepFixedMarketHint'
                : 'defaultMarketHint',
          ),
          children: [
            for (final mode in [
              if (_allowFixed) MarketMode.fixed,
              MarketMode.general,
              MarketMode.market,
            ])
              ChoiceTile(
                title: l10n.t(switch (mode) {
                  MarketMode.fixed => 'keepFixedMarket',
                  MarketMode.general => 'generalAgent',
                  MarketMode.market => 'defaultMarket',
                }),
                selected: _mode == mode,
                enabled: !_busy,
                onSelect: () => setState(() => _mode = mode),
              ),
          ],
        ),
        if (_mode == MarketMode.market) ...[
          const SizedBox(height: LnSpace.sm),
          if (rows == null && error != null)
            LnSection(
              children: [
                WrapTile(
                  icon: FIcons.landmark,
                  title:
                      errorMessage(context, error) ?? l10n.t('request_failed'),
                  trailing: Icon(FIcons.rotateCw, color: c.fgMuted),
                  onTap: _loadConnections,
                ),
              ],
            )
          else if (rows != null && rows.isEmpty)
            SettingsNote(l10n.t('connectBrokerFirst'))
          else
            LnSection(
              children: [
                WrapTile(
                  icon: FIcons.landmark,
                  title: l10n.t('brokerAccount'),
                  subtitle: accountIndex >= 0
                      ? brokerAccountLabel(
                          l10n,
                          rows![accountIndex],
                          accountIndex,
                        )
                      : l10n.t('chooseBrokerAccount'),
                  enabled: rows != null && !_busy,
                  trailing: rows == null
                      ? const LnSpinner(size: 18)
                      : const TileChevron(),
                  onTap: _chooseAccount,
                ),
                WrapTile(
                  icon: FIcons.chartCandlestick,
                  title: l10n.t('symbol'),
                  subtitle: _symbol.isNotEmpty
                      ? ltr(_symbol)
                      : l10n.t('chooseTradingPair'),
                  enabled: _account.isNotEmpty && _symbols != null && !_busy,
                  trailing: _account.isNotEmpty && _symbols == null
                      ? const LnSpinner(size: 18)
                      : Icon(FIcons.chevronRight, color: c.chevron),
                  onTap: _chooseSymbol,
                ),
              ],
            ),
        ],
        if (change.isNotEmpty) ...[
          const SizedBox(height: LnSpace.sm),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
            child: BlockButton(
              label: l10n.t('save'),
              loading: _busy,
              onPressed: complete ? () => _save(change) : null,
            ),
          ),
        ],
      ],
    );
  }
}

class _SymbolPicker extends StatefulWidget {
  const _SymbolPicker({required this.symbols, required this.selected});

  final List<String> symbols;
  final String selected;

  @override
  State<_SymbolPicker> createState() => _SymbolPickerState();
}

class _SymbolPickerState extends State<_SymbolPicker> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final q = _query.trim().toLowerCase();
    final shown = [
      for (final s in widget.symbols)
        if (q.isEmpty || s.toLowerCase().contains(q)) s,
    ].take(200).toList();
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        LnTextField(
          hint: context.t('searchBrokerSymbols'),
          prefix: const Icon(FIcons.search),
          autofocus: true,
          onChanged: (v) => setState(() => _query = v),
        ),
        const SizedBox(height: LnSpace.sm),
        Flexible(
          child: ListView(
            shrinkWrap: true,
            children: [
              LnSection(
                padding: EdgeInsets.zero,
                children: [
                  for (final s in shown)
                    ChoiceTile(
                      title: ltr(s),
                      selected: s == widget.selected,
                      onSelect: () => Navigator.of(context).pop(s),
                    ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}
