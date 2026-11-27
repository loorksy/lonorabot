// The trade approval card (apps/mobile/components/trade-approval.tsx, web TradeApprovals.tsx)
// laid out as an approval card: header band, «طلب موافقة · SYMBOL» with the
// account's simulation / broker badge, each request in words with its fact rows, the
// tolerance, the agent's reason labelled as the agent's words, and Reject / Approve as two
// equal stadiums. Decided, it keeps its frame: the disabled past-state stadium, the end state
// in the right tone (never a success look on a failure), and every unconfirmed result with
// its reason.
//
// SAFETY: the decision is sent only by the owner's tap on this card, to
// `POST /trading/approvals/{id}/decision` exactly as Web and Expo do. Nothing approves by
// itself; a refusal is shown in the owner's words and the card is read again.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../design/design.dart';
import '../../l10n/core/values.dart' show jsString;
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import 'card_parts.dart';
import 'cards_actions.dart';
import 'cards_strings.dart';

class TradeApprovalCardView extends StatelessWidget {
  const TradeApprovalCardView({
    super.key,
    required this.threadId,
    required this.approvalId,
    this.width,
  });

  final String threadId;
  final String approvalId;
  final double? width;

  @override
  Widget build(BuildContext context) {
    final row = context.select(
      (AppState s) => sideList(
        s.thread(threadId),
        SideKeys.approvals,
      ).where((r) => asStr(r['id']) == approvalId).firstOrNull,
    );
    if (row == null) return const SizedBox.shrink();
    final accountId = asJsonList(row['requests'])
        .map((r) => asString(r['account_id']))
        .whereType<String>()
        .firstOrNull;
    final provider = context.select(
      (AppState s) => accountProvider(s.thread(threadId), accountId),
    );
    return TradeApprovalCard(
      key: ValueKey(approvalId),
      threadId: threadId,
      row: row,
      provider: provider,
      width: width,
    );
  }
}

class TradeApprovalCard extends StatefulWidget {
  const TradeApprovalCard({
    super.key,
    required this.threadId,
    required this.row,
    this.provider,
    this.width,
  });

  final String threadId;

  /// The server's approval JSON.
  final Json row;

  /// The account's broker provider (`simulation` = paper), null when unknown.
  final String? provider;
  final double? width;

  @override
  State<TradeApprovalCard> createState() => _TradeApprovalCardState();
}

class _TradeApprovalCardState extends State<TradeApprovalCard> {
  bool _busy = false;
  String? _pressed;
  String? _error;

  Json get _row => widget.row;
  String get _reference => asStr(_row['reference_price']);

  Future<void> _run(String key, Future<void> Function() task) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _pressed = key;
      _error = null;
    });
    try {
      await task();
    } on ApiError catch (e) {
      if (mounted) setState(() => _error = context.l10n.errorText(e.code));
    } on SessionRequestCancelled {
      // Signed out.
    } catch (_) {
      if (mounted) {
        setState(() => _error = context.l10n.errorText('request_failed'));
      }
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _pressed = null;
        });
      }
    }
  }

  Future<void> _decide(String decision) => _run(decision, () async {
    unawaited(HapticFeedback.selectionClick());
    await context.dispatchAndWait(
      TradeApprovalDecisionAction(
        threadId: widget.threadId,
        approvalId: asStr(_row['id']),
        decision: decision,
      ),
    );
  });

  Future<void> _renew() => _run('renew', () async {
    await context.dispatchAndWait(
      TradeApprovalRenewAction(
        threadId: widget.threadId,
        approvalId: asStr(_row['id']),
      ),
    );
  });

  @override
  Widget build(BuildContext context) {
    registerCardsStrings(context.l10n);
    final l10n = context.l10n;
    final locale = l10n.lang;
    final status = asStr(_row['status'], 'pending');
    final requests = asJsonList(_row['requests']);
    final symbol = requests
        .map((r) => r['symbol'])
        .where((s) => s != null && '$s'.isNotEmpty)
        .firstOrNull;
    final tone = approvalEndTone(_row);

    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        CardKicker(
          icon: FIcons.shield,
          text: symbol == null
              ? l10n.t('tradeApproval')
              // No-break spaces keep «· SYMBOL» with the word before it: a wrapped kicker
              // neither ends nor starts a line with the dot.
              : '${l10n.t('tradeApproval')}\u00a0·\u00a0${ltr('$symbol')}',
          trailing: AccountBadge(provider: widget.provider),
        ),
        for (final request in requests) ..._request(context, request, locale),
        if (asString(_row['tolerance']) case final tolerance?
            when tolerance.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: LnSpace.sm),
            child: FactRows(
              rows: [
                FactRow(
                  l10n.t('validWithin'),
                  // «2346.80 ± 1.50» stays whole and in order inside Arabic.
                  _reference.isEmpty
                      ? '±\u00a0$tolerance'
                      : '$_reference\u00a0±\u00a0$tolerance',
                  ltr: true,
                ),
              ],
            ),
          ),
        if (asString(_row['reason']) case final reason? when reason.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: LnSpace.sm),
            child: EvidenceLine(
              tone: 'plain',
              icon: FIcons.messageCircle,
              child: Text.rich(
                TextSpan(
                  children: [
                    TextSpan(
                      text: '${l10n.t('agentWords')}: ',
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    TextSpan(text: isolate(reason)),
                  ],
                ),
              ),
            ),
          ),
        if (status != 'pending')
          Padding(
            padding: const EdgeInsets.only(top: LnSpace.sm),
            child: Semantics(
              liveRegion: true,
              child: EvidenceLine(
                tone: tone,
                icon: toneIcon(tone),
                child: Text(approvalStatusText(status, locale)),
              ),
            ),
          ),
        // A confirmed result is shown once: as its Execution Receipt (10.3).
        for (final result in asJsonList(_row['results']))
          if (result['status'] != 'confirmed')
            Padding(
              padding: const EdgeInsets.only(top: LnSpace.xs),
              child: _ResultLine(result: result),
            ),
        CardError(text: _error),
      ],
    );

    final actions = <Widget>[
      if (status == 'pending')
        ButtonPair(
          first: BlockButton(
            label: l10n.t('reject'),
            variant: BlockButtonVariant.secondary,
            loading: _pressed == 'reject',
            onPressed: _busy ? null : () => _decide('reject'),
          ),
          second: BlockButton(
            label: l10n.t('approve'),
            loading: _pressed == 'approve',
            onPressed: _busy ? null : () => _decide('approve'),
          ),
        )
      // The disabled past-state stadium where Lonora has a word for it; a drifted or
      // withdrawn card ends on its status line alone (no owner decision to name).
      else if (switch (status) {
            'approved' || 'completed' => l10n.t('cards_approved'),
            'rejected' => l10n.t('rejected'),
            'expired' => ownerActionText(locale).statusExpired,
            'cancelled' => ownerActionText(locale).statusCancelled,
            _ => null,
          }
          case final done?)
        BlockButton(label: done, variant: BlockButtonVariant.done),
      if (status == 'expired')
        BlockButton(
          label: ownerActionText(locale).renew,
          variant: BlockButtonVariant.secondary,
          loading: _pressed == 'renew',
          onPressed: _busy ? null : _renew,
        ),
    ];

    return ActionCard(
      width: widget.width,
      semanticLabel: l10n.t('tradeApproval'),
      header: CardHeaderArt(agentId: asString(_row['agent_id'])),
      body: body,
      actions: actions,
    );
  }

  List<Widget> _request(BuildContext context, Json request, String locale) {
    final ln = context.ln;
    final l10n = context.l10n;
    // The request in words and its volume («شراء 0.10»), never a raw action id.
    final action = orderLineAction(request, locale);
    final market = request['action'] == 'buy' || request['action'] == 'sell';
    String s(Object? v) => jsString(v);
    final rows = <FactRow>[
      if (market)
        FactRow(l10n.t('approvalEntry'), l10n.t('approvalAtMarket'))
      else if (request['price'] != null)
        FactRow(l10n.t('approvalEntry'), s(request['price']), ltr: true),
      if (request['stop_loss'] != null)
        FactRow(l10n.t('stopLoss'), s(request['stop_loss']), ltr: true),
      if (request['take_profit'] != null)
        FactRow(l10n.t('takeProfit'), s(request['take_profit']), ltr: true),
      if (request['clear_stop_loss'] == true)
        FactRow(l10n.t('stopLoss'), l10n.t('clearStopLoss')),
      if (request['clear_take_profit'] == true)
        FactRow(l10n.t('takeProfit'), l10n.t('clearTakeProfit')),
      if ((request['position_id'] ?? request['order_id']) case final ticket?)
        FactRow(l10n.t('approvalTicket'), s(ticket), ltr: true),
    ];
    return [
      Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Text(
          action.volume == null
              ? action.label
              : '${action.label} ${isolate(action.volume!)}',
          style: ln.text.title.copyWith(color: ln.colors.fg),
        ),
      ),
      if (rows.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: LnSpace.xs),
          child: FactRows(rows: rows),
        ),
    ];
  }
}

/// A result the broker has not confirmed: its stage, ticket, reason, prices and the broker's
/// own words, labelled (trade-approval.tsx:147-208).
class _ResultLine extends StatelessWidget {
  const _ResultLine({required this.result});
  final Json result;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final locale = l10n.lang;
    final status = asStr(result['status']);
    final code = asString(result['code']);
    final details = asJson(result['details']);
    final reason =
        financialResultReason(status, code, locale) ??
        (status == 'failed' && code != null
            ? l10n.errorText(code, fallback: failedResultFallback(locale))
            : null);
    final lines = <InlineSpan>[
      TextSpan(
        text: operationStatusText(status, details, locale),
        style: const TextStyle(fontWeight: FontWeight.w600),
      ),
      if (result['broker_id'] != null)
        TextSpan(
          text:
              '\n${brokerTicketLabel(locale)}: ${ltr(jsString(result['broker_id']))}',
        ),
      if (reason != null) TextSpan(text: '\n$reason'),
      for (final key in const ['price', 'execution_price'])
        if (details[key] != null && details[key] != '')
          TextSpan(
            text:
                '\n${brokerPriceLabel(key, locale)}: ${ltr(jsString(details[key]))}',
          ),
      if (details['description'] != null && details['description'] != '')
        TextSpan(
          children: [
            TextSpan(
              text: '\n${brokerWordsLabel(locale)}: ',
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            TextSpan(text: isolate(jsString(details['description']))),
          ],
        ),
    ];
    return EvidenceLine(
      tone: status == 'failed' ? 'bad' : 'warn',
      icon: FIcons.triangleAlert,
      child: Text.rich(TextSpan(children: lines)),
    );
  }
}
