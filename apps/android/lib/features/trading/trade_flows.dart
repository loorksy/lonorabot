// The owner's order flows. Each one ends in a review sheet the owner confirms, and only that
// tap calls OrderDesk.run (ARCHITECTURE.md «Safety»): close a trade, edit its stop and target,
// cancel a pending order. Opening an order lives on its ticket (trade_sheets.dart).
import 'package:flutter/widgets.dart';

import '../../core/json.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../market/market_data.dart';
import 'trade_numbers.dart';
import 'trade_rules.dart';
import 'trade_sheets.dart';
import 'trade_text.dart';
import 'trades_data.dart';

/// What an order needs to know about its account: the held identities' scope, its label and
/// kind, and its fresh state (broker permissions, recovery, journal) when read.
@immutable
class TradeAccount {
  const TradeAccount({
    required this.scope,
    required this.id,
    required this.label,
    required this.simulation,
    this.snapshot,
    this.recovery,
    this.journal,
  });

  final String scope;
  final String id;
  final String label;
  final bool simulation;
  final AccountSnapshot? snapshot;
  final BrokerRecovery? recovery;
  final List<JournalEntry>? journal;

  /// The broker refuses every order on this account.
  bool get notAllowed => snapshot?.tradingNotAllowed ?? false;

  /// The account's state cannot be verified: only exits are admitted.
  bool get down => recovery?.blocksNewRisk ?? false;

  /// «الحساب»: its label and whether it is a simulation or a broker account.
  ReviewFact fact(L10n l10n) => (
    label: l10n.t('account'),
    value:
        '${isolate(label)} · ${l10n.t(simulation ? 'simulation' : 'brokerAccount')}',
  );
}

/// The card a position's last action is remembered on.
String positionCard(String accountId, String positionId) =>
    'position:$accountId:$positionId';

/// What a position card shows (TradesPage.tsx `PositionCard`): the last action the owner took
/// on it this session, else the journal's newest edit or close of it by when the owner acted.
/// [closeHeld] / [editHeld]: a close, or the last edit, is held, so its button checks it (a check
/// stays possible while the broker refuses new orders).
({
  bool busy,
  bool closeBusy,
  bool closeHeld,
  bool editHeld,
  TicketOutcome? outcome,
  Object? error,
})
positionState(TradeAccount a, MarketPosition p) {
  final desk = OrderDesk.instance;
  final closeKey = heldKey('close_position', a.id, p.id);
  final last = desk.lastOn(a.scope, positionCard(a.id, p.id));
  final closeBusy = desk.busy(a.scope, closeKey);
  final lastBusy = last != null && last != closeKey && desk.busy(a.scope, last);
  TicketOutcome? outcome;
  if (last != null) {
    outcome = desk.outcome(a.scope, last, a.journal);
  } else {
    JournalEntry? latest;
    DateTime at(JournalEntry e) => e.submittedAt ?? e.updatedAt ?? DateTime(0);
    for (final e in a.journal ?? const <JournalEntry>[]) {
      if (e.positionId != p.id ||
          !const {'modify_position', 'close_position'}.contains(e.action)) {
        continue;
      }
      if (latest == null || at(e).isAfter(at(latest))) latest = e;
    }
    if (latest != null) outcome = TicketOutcome.fromJournal(latest);
  }
  return (
    busy: closeBusy || lastBusy,
    closeBusy: closeBusy,
    closeHeld: desk.held(a.scope, closeKey) != null,
    editHeld:
        last != null && last != closeKey && desk.held(a.scope, last) != null,
    outcome: outcome,
    error: last == null ? null : desk.error(a.scope, last),
  );
}

/// What a pending-order card shows; [blocked] when its cancel cannot be sent now (a held cancel
/// can always be checked).
({
  bool busy,
  bool held,
  bool protective,
  bool blocked,
  TicketOutcome? outcome,
  Object? error,
})
orderCardState(TradeAccount a, MarketOrder o) {
  final desk = OrderDesk.instance;
  final key = heldKey('cancel_order', a.id, o.id);
  final busy = desk.busy(a.scope, key);
  final held = desk.held(a.scope, key) != null;
  final protective = protectiveOrder(o, a.snapshot?.positions ?? const []);
  return (
    busy: busy,
    held: held,
    protective: protective,
    blocked: busy || (!held && (a.notAllowed || (a.down && protective))),
    outcome: desk.outcome(a.scope, key, a.journal),
    error: desk.error(a.scope, key),
  );
}

/// Announces a settled or unsettled answer in a toast: the card and its status line can leave
/// the screen with the next account read (a closed position, a filled order).
void announceOutcome(BuildContext context, TicketOutcome o) {
  final lines = outcomeLines(context.l10n, o);
  LnToast.show(
    context,
    lines.take(2).join(' '),
    kind: switch (o.status) {
      'confirmed' => LnToastKind.positive,
      'failed' => LnToastKind.error,
      _ => LnToastKind.notice,
    },
    duration: const Duration(seconds: 5),
  );
}

/// Sends the order the owner just confirmed in its review. A review of a held identity
/// ([expect]) is a check: when that identity settled or went while the review was open, nothing
/// is sent (never a new identity) and what settled it is shown.
Future<void> sendReviewed(
  BuildContext context, {
  required String scope,
  required String key,
  required Json Function() build,
  String? expect,
  String? card,
}) async {
  final desk = OrderDesk.instance;
  if (expect != null && desk.held(scope, key)?.operationId != expect) {
    final settled = desk.outcome(scope, key, null);
    if (settled != null && settled.settled) {
      announceOutcome(context, settled);
    } else {
      LnToast.show(
        context,
        context.t('operation_already_settled'),
        kind: LnToastKind.notice,
      );
    }
    return;
  }
  final outcome = await desk.run(
    scope: scope,
    key: key,
    build: build,
    card: card,
    expect: expect,
  );
  if (outcome != null && context.mounted) announceOutcome(context, outcome);
}

/// «العملية الحالية منذ»: when the held identity a check reviews was created.
ReviewFact heldFact(L10n l10n, DateTime createdAt) =>
    (label: l10n.t('tr_heldSince'), value: operationTime(l10n, createdAt));

List<ReviewFact> _positionFacts(L10n l10n, TradeAccount a, MarketPosition p) =>
    [
      a.fact(l10n),
      (label: l10n.t('symbol'), value: ltr(p.symbol)),
      (label: l10n.t('tr_side'), value: sideWord(l10n, p.side)),
      (label: l10n.t('receiptVolume'), value: ltr(p.volume)),
    ];

/// «إغلاق الصفقة» (or «تحقق من نتيجة الإغلاق» while a close is held): the whole position at
/// the market price, after the review. A held close keeps the review: if the first send never
/// reached the server, this send is the first.
Future<void> confirmClose(
  BuildContext context,
  TradeAccount a,
  MarketPosition p, {
  VoidCallback? onDone,
}) async {
  final l10n = context.l10n;
  final desk = OrderDesk.instance;
  final key = heldKey('close_position', a.id, p.id);
  await desk.load(a.scope);
  if (!context.mounted) return;
  final held = desk.held(a.scope, key);
  final ok = await showOrderReview(
    context,
    title: l10n.t('tr_closeTrade'),
    message: l10n.t('tr_closeBody', [ltr(p.symbol)]),
    facts: [
      ..._positionFacts(l10n, a, p),
      (label: l10n.t('tr_price'), value: l10n.t('approvalAtMarket')),
      if (held != null) heldFact(l10n, held.createdAt),
    ],
    live: !a.simulation,
    confirmLabel: l10n.t(
      held != null ? 'tr_checkCloseResult' : 'tr_closeTrade',
    ),
    destructive: true,
  );
  if (!ok || !context.mounted) return;
  await sendReviewed(
    context,
    scope: a.scope,
    key: key,
    build: () => closeRequest(accountId: a.id, p: p),
    expect: held?.operationId,
    card: positionCard(a.id, p.id),
  );
  onDone?.call();
}

/// «old → new» of a protection level in a reviewed edit; a level sent with the same value
/// («2365» for «2365.00») reads unchanged.
String levelChange(String? before, Json request, String field, String clear) {
  final was = (before ?? '').trim();
  final now = request[clear] == true
      ? ''
      : (request[field] == null ? was : '${request[field]}');
  String shown(String v) => v.isEmpty ? '—' : v;
  final sent = Dec.fromServer(now);
  if (now == was || (sent != null && sent == Dec.fromServer(was))) {
    return ltr(shown(was));
  }
  return ltr('${shown(was)} → ${shown(now)}');
}

/// «تعديل الوقف والهدف»: the form, then the review of old → new, then the send. The same
/// values as a held edit reuse its identity; different values are a new operation.
Future<void> editStopTarget(
  BuildContext context,
  TradeAccount a,
  MarketPosition p, {
  VoidCallback? onDone,
}) async {
  final request = await showModifySheet(context, account: a, position: p);
  if (request == null || !context.mounted) return;
  final l10n = context.l10n;
  final desk = OrderDesk.instance;
  final key = heldKey('modify_position', a.id, modifyTicket(request));
  await desk.load(a.scope);
  if (!context.mounted) return;
  final held = desk.held(a.scope, key);
  final ok = await showOrderReview(
    context,
    title: l10n.t('tr_editStopTarget'),
    facts: [
      ..._positionFacts(l10n, a, p),
      (
        label: l10n.t('stopLoss'),
        value: levelChange(p.stopLoss, request, 'stop_loss', 'clear_stop_loss'),
      ),
      (
        label: l10n.t('takeProfit'),
        value: levelChange(
          p.takeProfit,
          request,
          'take_profit',
          'clear_take_profit',
        ),
      ),
      if (held != null) heldFact(l10n, held.createdAt),
    ],
    live: !a.simulation,
    confirmLabel: l10n.t(held != null ? 'tr_checkExisting' : 'save'),
  );
  if (!ok || !context.mounted) return;
  await sendReviewed(
    context,
    scope: a.scope,
    key: key,
    build: () => request,
    expect: held?.operationId,
    card: positionCard(a.id, p.id),
  );
  onDone?.call();
}

/// «إلغاء الأمر» (or «تحقق من نتيجة الإلغاء» while held), after the review.
Future<void> confirmCancel(
  BuildContext context,
  TradeAccount a,
  MarketOrder o, {
  VoidCallback? onDone,
}) async {
  final l10n = context.l10n;
  final desk = OrderDesk.instance;
  final key = heldKey('cancel_order', a.id, o.id);
  await desk.load(a.scope);
  if (!context.mounted) return;
  final held = desk.held(a.scope, key);
  String level(String? v) => v == null || v.isEmpty ? '—' : ltr(v);
  final ok = await showOrderReview(
    context,
    title: l10n.t('tr_cancelOrder'),
    facts: [
      a.fact(l10n),
      (label: l10n.t('symbol'), value: ltr(o.symbol)),
      (label: l10n.t('tr_type'), value: orderKindWord(l10n, o.side)),
      (label: l10n.t('receiptVolume'), value: ltr(o.volume)),
      (label: l10n.t('orderPrice'), value: ltr(o.price)),
      (label: l10n.t('stopLoss'), value: level(o.stopLoss)),
      (label: l10n.t('takeProfit'), value: level(o.takeProfit)),
      if (held != null) heldFact(l10n, held.createdAt),
    ],
    live: !a.simulation,
    confirmLabel: l10n.t(
      held != null ? 'tr_checkCancelResult' : 'tr_cancelOrder',
    ),
    destructive: true,
  );
  if (!ok || !context.mounted) return;
  await sendReviewed(
    context,
    scope: a.scope,
    key: key,
    build: () => cancelRequest(accountId: a.id, o: o),
    expect: held?.operationId,
  );
  onDone?.call();
}
