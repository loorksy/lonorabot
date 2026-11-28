// «التعطل والاستعادة» (Routes.recovery, `?account=` narrows it): each broker connection's own
// recovery state, `state.broker_recovery` of `GET /trading/connections` (apps/web
// shell/agent/RecoveryPage.tsx). While a session is down the executor holds the affected
// trading until reconnect and reconciliation. «إعادة المحاولة» only reads each down account
// again (`GET /trading/accounts/{id}`), which nudges the broker manager; nothing here settles,
// executes or reconnects anything.
import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../core/broker_identity.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/realtime.dart';
import '../market/market_data.dart';
import '../market/market_kit.dart';
import '../market/market_widgets.dart';
import '../settings/settings_common.dart';
import 'trade_text.dart';
import 'trading_strings.dart';

class RecoveryScreen extends StatefulWidget {
  const RecoveryScreen({super.key, this.account});

  /// Only this connection; read from the route's `?account=` when not given.
  final String? account;

  @override
  State<RecoveryScreen> createState() => _RecoveryScreenState();
}

class _RecoveryScreenState extends State<RecoveryScreen> {
  List<MarketConnection>? _connections;
  Object? _error;
  bool _busy = false;
  Timer? _debounce;
  StreamSubscription<LonoraEvent>? _events;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
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

  void _onEvent(LonoraEvent e) {
    if (!e.kind.startsWith('broker') &&
        !e.kind.startsWith('trading_connections.')) {
      return;
    }
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 800), () {
      if (mounted) unawaited(_load());
    });
  }

  Future<void> _load() async {
    try {
      final rows = await fetchMarketConnections();
      if (mounted) {
        setState(() {
          _connections = rows;
          _error = null;
        });
      }
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (!mounted) return;
      if (_connections == null) {
        setState(() => _error = e);
      } else {
        showErrorToast(context, e);
      }
    }
  }

  String? get _wanted {
    if (widget.account != null) return widget.account;
    try {
      return GoRouterState.of(context).uri.queryParameters['account'];
    } catch (_) {
      return null;
    }
  }

  List<MarketConnection> get _down {
    final wanted = _wanted;
    return [
      for (final c in _connections ?? const <MarketConnection>[])
        if ((c.recovery?.down ?? false) && (wanted == null || c.id == wanted))
          c,
    ];
  }

  String _label(MarketConnection c) => brokerAccountLabel(
    context.l10n,
    c.raw,
    (_connections ?? const <MarketConnection>[]).indexOf(c),
  );

  /// A fresh read through the broker manager per down account (errors ignored), then the
  /// connections again; the reconciliation writes the new state.
  Future<void> _retry() async {
    if (_busy) return;
    final down = _down;
    setState(() => _busy = true);
    try {
      for (final c in down) {
        try {
          await fetchAccountSnapshot(c.id);
        } catch (_) {
          // The state updates when the broker answers.
        }
      }
      await _load();
      if (mounted) {
        LnToast.show(
          context,
          context.t('rc_retried'),
          kind: LnToastKind.notice,
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _when(DateTime? at) {
    if (at == null) return '—';
    final lang = context.l10n.lang;
    return isolate(
      formatDate(
        lang == 'ar' ? 'd MMM y، HH:mm' : 'd MMM y, HH:mm',
        lang,
        at.toLocal(),
      ),
    );
  }

  /// The reason in Lonora's words when it has them, else the raw code, isolated.
  String _reason(String? code) {
    if (code == null || code.isEmpty) return '—';
    final l10n = context.l10n;
    const unknown = '\u0000';
    final text = l10n.errorText(code, fallback: unknown);
    return text == unknown ? ltr(code) : text;
  }

  Future<void> _details() async {
    final down = _down;
    await showLnSheet<void>(
      context,
      title: context.t('rc_details'),
      builder: (sheet) => SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final (i, c) in down.indexed) ...[
              if (i > 0) const SizedBox(height: LnSpace.sm),
              FactsCard(
                children: [
                  FactRow(label: sheet.t('account'), value: isolate(_label(c))),
                  FactRow(
                    label: sheet.t('rc_since'),
                    value: _when(c.recovery?.since),
                  ),
                  FactRow(
                    label: sheet.t('rc_lastSuccess'),
                    value: _when(c.recovery?.lastSuccessAt),
                  ),
                  FactRow(
                    label: sheet.t('rc_reason'),
                    value: _reason(c.recovery?.reasonCode),
                  ),
                  FactRow(
                    label: sheet.t('rc_awaiting'),
                    value: ltr(
                      '${c.recovery?.unresolvedOperations.length ?? 0}',
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: LnSpace.md),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    ensureTradingStrings(context);
    final l10n = context.l10n;
    final title = l10n.t('rc_title');
    if (_connections == null) {
      return SettingsPageScaffold(
        title: title,
        fallback: Routes.settings,
        body: _error != null
            ? LoadFailure(
                error: _error!,
                onRetry: () {
                  setState(() => _error = null);
                  unawaited(_load());
                },
              )
            : SettingsSkeleton(
                groups: const [3],
                animate:
                    !(MediaQuery.maybeDisableAnimationsOf(context) ?? false),
              ),
      );
    }
    final down = _down;
    if (down.isEmpty) {
      return SettingsPageScaffold(
        title: title,
        fallback: Routes.settings,
        onRefresh: _load,
        children: [
          _Hero(
            icon: FIcons.circleCheck,
            positive: true,
            title: l10n.t('rc_connected'),
            body: l10n.t('rc_connectedBody'),
          ),
        ],
      );
    }
    return SettingsPageScaffold(
      title: title,
      fallback: Routes.settings,
      onRefresh: _load,
      children: [
        _Hero(
          icon: FIcons.unplug,
          positive: false,
          title: l10n.t('rc_dropped'),
          body: l10n.t('rc_droppedBody'),
        ),
        LnSection(
          children: [
            for (final c in down)
              LnListTile(
                icon: c.isSimulation ? FIcons.flaskConical : FIcons.landmark,
                title: l10n.t('rc_state'),
                subtitle: down.length > 1 ? isolate(_label(c)) : null,
                value: recoveryStatusName(l10n, c.recovery!.status),
              ),
          ],
        ),
        const SectionGap(height: LnSpace.lg),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              BlockButton(
                label: l10n.t('rc_details'),
                icon: FIcons.info,
                variant: BlockButtonVariant.secondary,
                onPressed: _details,
              ),
              const SizedBox(height: LnSpace.xs),
              BlockButton(
                label: l10n.t('rc_tryAgain'),
                icon: FIcons.refreshCw,
                loading: _busy,
                onPressed: _busy ? null : _retry,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// The page's state: a decorative icon in a tinted circle, the heading and its line.
class _Hero extends StatelessWidget {
  const _Hero({
    required this.icon,
    required this.positive,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final bool positive;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final tint = positive ? c.success : c.warning;
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter,
        LnSpace.lg,
        LnSpace.pageGutter,
        LnSpace.lg,
      ),
      child: Column(
        children: [
          ExcludeSemantics(
            child: Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: tint.withValues(alpha: c.isDark ? 0.2 : 0.14),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, size: 32, color: tint),
            ),
          ),
          const SizedBox(height: LnSpace.md),
          Semantics(
            header: true,
            child: Text(
              title,
              textAlign: TextAlign.center,
              style: ln.text.display.copyWith(color: c.fg),
            ),
          ),
          const SizedBox(height: LnSpace.xs),
          Text(
            body,
            textAlign: TextAlign.center,
            style: ln.text.body.copyWith(color: c.fgMuted),
          ),
        ],
      ),
    );
  }
}
