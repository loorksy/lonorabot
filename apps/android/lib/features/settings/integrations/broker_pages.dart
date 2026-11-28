// «ربط الوسيط» and «حساب التداول», built from tile groups, fields and block buttons. Lonora's
// counterparts of apps/web ConnectionPages.tsx `BrokerFormPage`, `BrokerAccountPage` and
// `SimulationImport`: the same endpoints (`POST /trading/connections`, `/trading/connections/test`
// — a read-only round trip that stores nothing — `GET /trading/accounts/{id}`, `GET
// /market/symbols`, `DELETE /trading/connections/{id}`). Nothing here trades: there is no order
// path, no global trading switch; each agent's Mandate is set in that agent's settings, which the
// account page links to.
import 'dart:async';
import 'dart:convert';

import 'package:async_redux/async_redux.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../../app/routes.dart';
import '../../../core/api/api_error.dart';
import '../../../core/json.dart';
import '../../../core/models/models.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../../state/actions/base.dart';
import '../../../state/actions/shell_actions.dart';
import '../../../state/app_state.dart';
import '../../market/market_data.dart' show BrokerRecovery;
import '../../market/market_kit.dart' show metaApiName, money;
import '../../trading/recovery_link.dart';
import '../../trading/trade_text.dart' show recoveryStatusName;
import '../settings_common.dart';
import 'ext_common.dart';
import 'integrations_data.dart';

/// A balance as the market's account amounts read (grouped, two decimals); a value that is not
/// a number as the server sent it.
String _balance(Object? value) {
  final amount = asDouble(value);
  return amount == null ? asStr(value) : money(amount);
}

/// The broker's display name (the simulation is named as one, never «Demo»).
String brokerName(BuildContext context, String provider) => switch (provider) {
  'simulation' => context.t('ix_simulationSnapshot'),
  'metaapi' => metaApiName,
  _ => provider,
};

/// The row title of a connection: «Broker · login», the simulation and its id, or an
/// unverified MetaApi account.
String connectionTitle(BuildContext context, BrokerConnection c) {
  final identity = c.identity;
  // A simulation's row says «Simulation · its id»; its page names it in full.
  final broker =
      identity?.broker ??
      (c.isSimulation ? context.t('ix_simulation') : 'MetaApi');
  final number = c.number;
  return number != null
      ? '${isolate(broker)} · ${ltr(number)}'
      : '${isolate(broker)} · ${context.t('unverifiedBrokerAccount')}';
}

/// «MetaApi · 2 agents», «Simulation · No agents».
String connectionSubtitle(BuildContext context, BrokerConnection c, int count) {
  final l10n = context.l10n;
  final agents = count == 0 ? l10n.t('ix_noAgents') : l10n.agentsWord(count);
  if (c.isSimulation) return l10n.t('ix_simulationAgents', [agents]);
  return c.identity?.broker != null ? 'MetaApi · $agents' : agents;
}

/// Simulation and broker accounts are told apart on every row (a paper account is never
/// presented as a live one).
class ConnectionKindChip extends StatelessWidget {
  const ConnectionKindChip({super.key, required this.connection});

  final BrokerConnection connection;

  @override
  Widget build(BuildContext context) => StatusChip(
    label: context.t(
      connection.isSimulation ? 'ix_simulation' : 'brokerAccount',
    ),
    kind: connection.isSimulation
        ? StatusChipKind.neutral
        : StatusChipKind.brand,
  );
}

/// «ربط الوسيط»: MetaApi (preselected) or the simulation; test, then link. Pops the new
/// connection id once linked (the caller says so).
class BrokerFormPage extends StatefulWidget {
  const BrokerFormPage({super.key});

  @override
  State<BrokerFormPage> createState() => _BrokerFormPageState();
}

class _BrokerFormPageState extends State<BrokerFormPage> {
  String _provider = 'metaapi';
  final Map<String, TextEditingController> _fields = {
    'account_id': TextEditingController(),
    'api_key': TextEditingController(),
    'region': TextEditingController(),
  };
  ({bool ok, String text})? _test;
  FormAction? _running;

  bool get _busy => _running != null;

  @override
  void dispose() {
    for (final c in _fields.values) {
      c
        ..clear()
        ..dispose();
    }
    super.dispose();
  }

  bool get _simulation => _provider == 'simulation';

  Json? _body() {
    final fields = brokerFields[_provider]!;
    for (final f in fields) {
      if (f.required && _fields[f.name]!.text.trim().isEmpty) {
        LnToast.show(
          context,
          context.t(
            f.name == 'account_id' ? 'ix_enterAccount' : 'ix_enterToken',
          ),
          kind: LnToastKind.notice,
        );
        return null;
      }
    }
    return brokerBody(_provider, {
      for (final f in fields) f.name: _fields[f.name]!.text,
    });
  }

  Future<void> _runTest() async {
    final body = _body();
    if (body == null || _busy) return;
    setState(() {
      _running = FormAction.test;
      _test = null;
    });
    try {
      final result = await testBroker(body);
      if (!mounted) return;
      final identity = asJson(result['identity']);
      final who = [
        asString(identity['broker']),
        asString(identity['server']),
        asString(identity['login']),
      ].whereType<String>().where((s) => s.isNotEmpty).join(dotSeparator);
      setState(
        () => _test = (
          ok: true,
          text: result['provider'] == 'simulation'
              ? context.t('ix_fieldsValid')
              : who.isNotEmpty
              ? context.t('ix_connectionWorksWho', [isolate(who)])
              : context.t('ix_connectionWorks'),
        ),
      );
    } catch (e) {
      final text = mounted ? errorMessage(context, e) : null;
      if (mounted && text != null) {
        setState(() => _test = (ok: false, text: text));
      }
    } finally {
      if (mounted) setState(() => _running = null);
    }
  }

  Future<void> _link() async {
    final body = _body();
    if (body == null || _busy) return;
    setState(() => _running = FormAction.save);
    try {
      final row = await linkBroker(body);
      _fields['api_key']!.clear();
      if (!mounted) return;
      // The shell's agents and accounts follow the new link (as the Web's data refresh).
      context.dispatch(RefreshShellAction());
      Navigator.of(context).pop(row.id);
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _running = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final fields = brokerFields[_provider]!;
    final test = _test;
    return SettingsPageScaffold(
      title: context.t('ix_linkBroker'),
      children: [
        LnSection(
          title: context.t('ix_broker'),
          children: [
            for (final p in brokerFields.keys)
              ChoiceTile(
                title: brokerName(context, p),
                icon: p == 'simulation'
                    ? FIcons.flaskConical
                    : FIcons.trendingUp,
                selected: p == _provider,
                enabled: !_busy,
                onSelect: () => setState(() {
                  _provider = p;
                  _test = null;
                }),
              ),
          ],
        ),
        const SectionGap(),
        if (_simulation) ...[
          LnSection(
            children: [
              LnListTile(
                title: context.t('ix_accountType'),
                value: context.t('ix_simulation'),
              ),
            ],
          ),
          const SectionGap(),
        ],
        for (final f in fields)
          Gutter(
            key: ValueKey('$_provider:${f.name}'),
            bottom: LnSpace.md,
            child: f.secret
                ? SecretField(
                    controller: _fields[f.name]!,
                    label: context.t('ix_accessTokenField'),
                    enabled: !_busy,
                  )
                : LnTextField(
                    controller: _fields[f.name]!,
                    label: context.t(
                      f.name == 'account_id' ? 'ix_accountNumber' : 'ix_region',
                    ),
                    hint: f.name == 'account_id'
                        ? context.t('ix_accountHint')
                        : null,
                    enabled: !_busy,
                    keyboardType: TextInputType.visiblePassword,
                    autocorrect: false,
                    textDirection: TextDirection.ltr,
                    // The Arabic hint stays under its label.
                    hintTextDirection: Directionality.of(context),
                  ),
          ),
        if (test != null)
          Gutter(
            bottom: LnSpace.md,
            child: TestResultLine(ok: test.ok, text: test.text),
          ),
        Gutter(
          bottom: LnSpace.sm,
          child: BlockButton(
            label: context.t(
              _simulation ? 'ix_checkFields' : 'ix_testConnection',
            ),
            variant: BlockButtonVariant.secondary,
            loading: _running == FormAction.test,
            onPressed: _busy ? null : _runTest,
          ),
        ),
        Gutter(
          bottom: LnSpace.lg,
          child: BlockButton(
            label: context.t('ix_linkTheAccount'),
            loading: _running == FormAction.save,
            onPressed: _busy ? null : _link,
          ),
        ),
        SettingsNote(context.t('ix_symbolsAfterLink')),
      ],
    );
  }
}

/// One linked account: who it is, its balance, its symbols, the agents on it (each opening
/// its own settings, where its Mandate lives) and «Unlink the account». Pops the toast text
/// when the account was unlinked.
class BrokerAccountPage extends StatefulWidget {
  const BrokerAccountPage({super.key, required this.connectionId});

  final String connectionId;

  @override
  State<BrokerAccountPage> createState() => _BrokerAccountPageState();
}

class _BrokerAccountPageState extends State<BrokerAccountPage> {
  BrokerConnection? _row;
  bool _missing = false;
  Object? _error;
  Json? _account;
  Object? _accountError;
  List<String>? _symbols;
  Object? _symbolsError;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final rows = await fetchConnections();
      if (!mounted) return;
      final row = rows.where((r) => r.id == widget.connectionId).firstOrNull;
      setState(() {
        _row = row;
        _missing = row == null;
        _error = null;
      });
      if (row != null) await Future.wait([_loadAccount(), _loadSymbols()]);
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (!mounted) return;
      // A failed refresh keeps the account on screen and says so.
      if (_row != null) {
        showErrorToast(context, e);
      } else {
        setState(() => _error = e);
      }
    }
  }

  Future<void> _loadAccount() async {
    try {
      final account = await fetchAccount(widget.connectionId);
      if (mounted) {
        setState(() {
          _account = account;
          _accountError = null;
        });
      }
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted) setState(() => _accountError = e);
    }
  }

  Future<void> _loadSymbols() async {
    if (mounted) {
      setState(() {
        _symbols = null;
        _symbolsError = null;
      });
    }
    try {
      final symbols = await fetchSymbols(widget.connectionId);
      if (mounted) setState(() => _symbols = symbols);
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted) setState(() => _symbolsError = e);
    }
  }

  bool get _needsSnapshot =>
      _row?.isSimulation == true &&
      _accountError is ApiError &&
      (_accountError! as ApiError).code == 'simulation_snapshot_required';

  String _broker(BuildContext context) {
    final row = _row!;
    return asString(_account?['broker']) ??
        row.identity?.broker ??
        (row.isSimulation ? context.t('ix_simulationSnapshot') : 'MetaApi');
  }

  String? get _number => asString(_account?['login']) ?? _row?.number;

  Future<void> _import() async {
    if (_busy) return;
    final picked = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['json'],
    );
    final file = picked.firstOrNull;
    if (file == null || !mounted) return;
    setState(() => _busy = true);
    try {
      final Object? snapshot;
      try {
        // Read through the picker (a file path or a content URI alike).
        snapshot = jsonDecode(utf8.decode(await file.readAsBytes()));
      } on FormatException {
        if (mounted) {
          LnToast.show(
            context,
            context.t('ix_notJson'),
            kind: LnToastKind.error,
          );
        }
        return;
      }
      await importSimulation(widget.connectionId, snapshot);
      if (!mounted) return;
      LnToast.show(
        context,
        context.t('ix_simulationImported'),
        kind: LnToastKind.positive,
      );
      await Future.wait([_loadAccount(), _loadSymbols()]);
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _unlink(List<Agent> agents) async {
    final broker = isolate(_broker(context));
    final number = _number;
    final body = [
      number != null
          ? context.t('ix_unlinkBody', [ltr(number), broker])
          : context.t('ix_unlinkBodyNoNumber', [broker]),
      if (agents.isNotEmpty)
        context.t('ix_unlinkAgents', [
          agents
              .map((a) => isolate(a.name))
              .join(listSeparator(context.l10n.lang)),
        ]),
    ].join(' ');
    final ok = await showLnConfirm(
      context,
      title: context.t('ix_unlinkAccount'),
      message: body,
      confirmLabel: context.t('ix_unlink'),
      cancelLabel: context.t('sh_cancel'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() => _busy = true);
    try {
      await unlinkBroker(widget.connectionId);
      if (!mounted) return;
      // The server cleared the agents' account and revoked their delegations: the shell reads
      // its agents again so no page shows the removed account (the Web's data refresh).
      context.dispatch(RefreshShellAction());
      Navigator.of(context).pop(
        number != null
            ? context.t('ix_accountUnlinkedN', [ltr(number)])
            : context.t('ix_accountUnlinked'),
      );
    } catch (e) {
      // The server's refusal (e.g. an operation without a confirmed outcome) is shown.
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final title = context.t('ix_tradingAccount');
    final row = _row;
    if (row == null) {
      return SettingsPageScaffold(
        title: title,
        body: _missing
            ? EmptyState(
                icon: FIcons.trendingUp,
                title: context.t('ix_noAccountLinked'),
              )
            : _error != null
            ? LoadFailure(error: _error!, onRetry: _load)
            : const PageLoading(groups: [2, 3]),
      );
    }
    final ln = context.ln;
    final c = ln.colors;
    final agents = context.select(
      (AppState s) => [
        for (final a in s.shell.orderedAgents)
          if (a.tradingAccountId == row.id) a,
      ],
    );
    final broker = _broker(context);
    final number = _number;
    final server = asString(_account?['server']) ?? row.identity?.server;
    final account = _account;
    final symbols = _symbols;
    return SettingsPageScaffold(
      title: title,
      onRefresh: _load,
      children: [
        Gutter(
          bottom: LnSpace.lg,
          child: LnCardSurface(
            child: Padding(
              padding: const EdgeInsets.all(LnSpace.cardPadding),
              child: Row(
                children: [
                  Container(
                    width: LnSize.iconTile,
                    height: LnSize.iconTile,
                    decoration: BoxDecoration(
                      color: c.fill2,
                      borderRadius: const BorderRadius.all(
                        Radius.circular(LnRadius.iconTile),
                      ),
                    ),
                    child: Icon(
                      row.isSimulation
                          ? FIcons.flaskConical
                          : FIcons.trendingUp,
                      color: c.fg,
                    ),
                  ),
                  const SizedBox(width: LnSpace.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          broker,
                          style: ln.text.title.copyWith(color: c.fg),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          number != null
                              ? ltr(number)
                              : context.t('unverifiedBrokerAccount'),
                          style: ln.text.footnote.copyWith(color: c.fgMuted),
                        ),
                        if (server != null)
                          Text(
                            ltr(server),
                            style: ln.text.footnote.copyWith(color: c.fgMuted),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(width: LnSpace.xs),
                  ConnectionKindChip(connection: row),
                ],
              ),
            ),
          ),
        ),
        if (_needsSnapshot) ...[
          SettingsNote(context.t('ix_simulationIntro')),
          Gutter(
            bottom: LnSpace.lg,
            child: BlockButton(
              label: context.t('ix_importSimulation'),
              icon: FIcons.fileUp,
              loading: _busy,
              onPressed: _busy ? null : _import,
            ),
          ),
        ] else ...[
          LnSection(
            children: [
              LnListTile(
                icon: FIcons.wallet,
                title: context.t('ix_balance'),
                value: account != null
                    ? ltr(
                        // Grouped, two decimals: the market's account amounts.
                        '${_balance(account['balance'])} ${asStr(account['currency'])}'
                            .trim(),
                      )
                    : _accountError != null
                    ? errorMessage(context, _accountError!)
                    : '…',
              ),
              if (row.isSimulation)
                LnListTile(
                  icon: FIcons.flaskConical,
                  title: context.t('ix_accountType'),
                  value: context.t('ix_simulation'),
                ),
            ],
          ),
          const SectionGap(),
          _SymbolsBlock(
            broker: broker,
            symbols: symbols,
            error: _symbolsError,
            agents: agents,
            onRefresh: _loadSymbols,
          ),
        ],
        const SectionGap(),
        // «التعطل والاستعادة» of this connection, with its execution state while it is down.
        LnSection(
          children: [
            LnListTile(
              icon: FIcons.activity,
              title: context.t('rc_title'),
              value: _recoveryValue(context, row),
              onTap: () => context.push(recoveryLocation(account: row.id)),
            ),
          ],
        ),
        const SectionGap(),
        if (agents.isEmpty)
          SettingsNote(
            context.t('ix_noAgentOnAccount'),
            padding: const EdgeInsetsDirectional.fromSTEB(
              LnSpace.pageGutter,
              0,
              LnSpace.pageGutter,
              LnSpace.xs,
            ),
          )
        else
          LnSection(
            title: context.t('ix_agentsOnAccount'),
            children: [
              for (final a in agents)
                WrapTile(
                  icon: FIcons.bot,
                  title: a.name,
                  subtitle: a.tradingSymbol == null
                      ? null
                      : ltr(a.tradingSymbol!),
                  trailing: Icon(FIcons.chevronRight, color: c.chevron),
                  onTap: () => context.push(Routes.agentSettings(a.id)),
                ),
            ],
          ),
        SettingsNote(
          context.t('ix_mandateNote'),
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.pageGutter,
            LnSpace.xs,
            LnSpace.pageGutter,
            LnSpace.lg,
          ),
        ),
        Gutter(
          bottom: LnSpace.lg,
          child: BlockButton(
            label: context.t('ix_unlinkAccount'),
            variant: BlockButtonVariant.destructive,
            onPressed: _busy ? null : () => _unlink(agents),
          ),
        ),
      ],
    );
  }
}

/// The execution state of a connection that is down, else none.
String? _recoveryValue(BuildContext context, BrokerConnection row) {
  final recovery = BrokerRecovery(asJson(row.state['broker_recovery']));
  return recovery.down
      ? recoveryStatusName(context.l10n, recovery.status)
      : null;
}

class _SymbolsBlock extends StatelessWidget {
  const _SymbolsBlock({
    required this.broker,
    required this.symbols,
    required this.error,
    required this.agents,
    required this.onRefresh,
  });

  final String broker;
  final List<String>? symbols;
  final Object? error;
  final List<Agent> agents;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final list = symbols;
    // At the notes' inset (SettingsNote), over the chips.
    final header = Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter,
        0,
        LnSpace.pageGutter,
        LnSpace.xs,
      ),
      child: Semantics(
        header: true,
        child: Text(
          list == null
              ? context.t('ix_availableSymbols')
              : context.t('ix_availableSymbolsN', [list.length]),
          style: ln.text.footnoteStrong.copyWith(color: c.fgMuted),
        ),
      ),
    );
    final Widget body;
    if (error != null) {
      body = SettingsNote(errorMessage(context, error!) ?? '');
    } else if (list == null) {
      body = Gutter(
        bottom: LnSpace.md,
        child: Row(
          children: [
            const LnSpinner(size: 16),
            const SizedBox(width: LnSpace.xs),
            Expanded(
              child: Text(
                context.t('ix_fetchingSymbols', [isolate(broker)]),
                style: ln.text.footnote.copyWith(color: c.fgMuted),
              ),
            ),
          ],
        ),
      );
    } else {
      body = Gutter(
        bottom: LnSpace.sm,
        child: Wrap(
          spacing: LnSpace.xs,
          runSpacing: LnSpace.xs,
          children: [
            for (final s in list)
              _SymbolChip(
                symbol: s,
                agents: [
                  for (final a in agents)
                    if (a.tradingSymbol == s) a.name,
                ],
              ),
          ],
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        header,
        body,
        SettingsNote(context.t('ix_symbolsNote')),
        if (list != null || error != null)
          Gutter(
            bottom: 0,
            child: BlockButton(
              label: context.t('ix_refreshSymbols'),
              variant: BlockButtonVariant.secondary,
              icon: FIcons.refreshCw,
              onPressed: onRefresh,
            ),
          ),
      ],
    );
  }
}

class _SymbolChip extends StatelessWidget {
  const _SymbolChip({required this.symbol, required this.agents});

  final String symbol;
  final List<String> agents;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: LnSpace.sm,
        vertical: LnSpace.xs,
      ),
      decoration: BoxDecoration(
        color: c.fill1,
        border: Border.all(color: c.border),
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.field)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            symbol,
            textDirection: TextDirection.ltr,
            style: ln.text.footnoteStrong.copyWith(color: c.fg),
          ),
          if (agents.isNotEmpty)
            Text(
              agents.join(listSeparator(context.l10n.lang)),
              style: ln.text.small.copyWith(color: c.fgMuted),
            ),
        ],
      ),
    );
  }
}

/// The trading-account rows of the integrations page (kept here with the account pages).
List<WrapTile> connectionTiles(
  BuildContext context,
  List<BrokerConnection> rows,
  Map<String, Agent> agents,
  void Function(BrokerConnection row) onOpen,
) => [
  for (final row in rows)
    WrapTile(
      icon: row.isSimulation ? FIcons.flaskConical : FIcons.trendingUp,
      title: connectionTitle(context, row),
      subtitle: connectionSubtitle(
        context,
        row,
        agents.values.where((a) => a.tradingAccountId == row.id).length,
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          ConnectionKindChip(connection: row),
          const SizedBox(width: LnSpace.xxs),
          Icon(FIcons.chevronRight, color: context.ln.colors.chevron),
        ],
      ),
      onTap: () => onOpen(row),
    ),
];
