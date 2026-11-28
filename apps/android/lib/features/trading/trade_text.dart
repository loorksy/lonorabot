// The words of the owner's orders: the status line of an operation (TradesPage.tsx and
// TradeActionCard.tsx: `operationStatusLabel` plus the boundary's reason; the approval card's
// broker ticket, price and words), the text of a send that got no settled answer, and the order
// log's wording (TradesPage.tsx `orderWording`, `stateName`).
import '../../core/api/api_error.dart';
import '../../l10n/core/values.dart' show jsString;
import '../../l10n/l10n.dart';
import '../market/market_data.dart';
import 'trade_rules.dart';
import 'trades_data.dart';

const _unknown = '\u0000';

/// The owner text of an executor code: Lonora's words when it has them (`errorText`), a family
/// of health reasons (`broker_account_*`, `market_quote_*`), else the generic line with the
/// code isolated.
String tradeCodeText(L10n l10n, String code) {
  final text = l10n.errorText(code, fallback: _unknown);
  if (text != _unknown) return text;
  if (code.startsWith('broker_account_')) return l10n.t('tr_accountUnverified');
  if (code.startsWith('market_quote_')) return l10n.t('tr_quoteUnusable');
  return l10n.t('tr_failedWithCode', [ltr(code)]);
}

/// Why a send got no settled answer. No answer from Lonora (offline, a timeout, a bare proxy
/// error) never invites a plain retry: it reads `broker_gateway_no_answer`, which says to check
/// the trades first; a server failure reads as uncertain; a refusal reads its code.
String tradeErrorText(L10n l10n, Object error) {
  if (error is ApiError) {
    final status = error.status;
    if (!error.serverAnswered) return l10n.t('broker_gateway_no_answer');
    if (status != null && status >= 500) {
      final text = l10n.errorText(error.code, fallback: _unknown);
      return text == _unknown || error.code == 'request_failed'
          ? l10n.t('tr_uncertainSend')
          : text;
    }
    return tradeCodeText(l10n, error.code);
  }
  return l10n.t('tr_uncertainSend');
}

/// The status line of an operation, in reading order: its stage, why (an uncertain result
/// says it is not resent; a failure says its cause), that an unsettled one is not sent again,
/// then the broker's ticket, price and own words, labelled.
List<String> outcomeLines(L10n l10n, TicketOutcome o) {
  final lang = l10n.lang;
  final code = o.code;
  final reason =
      financialResultReason(o.status, code, lang) ??
      (o.status == 'failed' && code != null
          ? tradeCodeText(l10n, code)
          : o.status == 'failed'
          ? failedResultFallback(lang)
          : null);
  final details = o.details;
  return [
    operationStatusText(o.status, details, lang),
    ?reason,
    if (o.status == 'reserved' || o.status == 'submitted')
      l10n.t('tr_notSentAgain'),
    if (o.brokerId != null && o.brokerId!.isNotEmpty)
      '${brokerTicketLabel(lang)}: ${ltr(o.brokerId!)}',
    for (final key in const ['price', 'execution_price'])
      if (details[key] != null && details[key] != '')
        '${brokerPriceLabel(key, lang)}: ${ltr(jsString(details[key]))}',
    if (details['description'] != null && details['description'] != '')
      '${brokerWordsLabel(lang)}: ${isolate(jsString(details['description']))}',
  ];
}

/// The side's word (msgctxt "side").
String sideWord(L10n l10n, String side) =>
    l10n.t(sideOf(side) == 'sell' ? 'mk_sell' : 'mk_buy');

/// An entry action's word on the ticket («شراء بسعر السوق» …).
String entryActionWord(L10n l10n, String action) => l10n.t(switch (action) {
  'sell' => 'tr_marketSell',
  'buy_limit' => 'tr_buyLimit',
  'sell_limit' => 'tr_sellLimit',
  'buy_stop' => 'tr_buyStop',
  'sell_stop' => 'tr_sellStop',
  _ => 'tr_marketBuy',
});

/// A pending order's kind: the ticket's own words («شراء بحد سعري» …), else its side.
String orderKindWord(L10n l10n, String side) {
  final s = side.replaceFirst('ORDER_TYPE_', '').toLowerCase();
  return tradeEntryActions.contains(s)
      ? entryActionWord(l10n, s)
      : sideWord(l10n, s);
}

/// Each executor action under the Web's words: what was asked, and how (`orderWording`).
({String title, String kind}) orderWording(L10n l10n, String action) {
  final side = sideWord(l10n, action);
  return switch (action) {
    'buy' || 'sell' => (title: side, kind: l10n.t('approvalAtMarket')),
    'buy_limit' || 'sell_limit' => (title: side, kind: l10n.t('tr_limitOrder')),
    'buy_stop' || 'sell_stop' => (title: side, kind: l10n.t('tr_stopOrder')),
    'close_position' => (
      title: l10n.t('tr_closeTrade'),
      kind: l10n.t('approvalAtMarket'),
    ),
    'modify_position' => (
      title: l10n.t('tr_editStopTarget'),
      kind: l10n.t('tr_protectionChange'),
    ),
    'cancel_order' => (
      title: l10n.t('tr_cancelOrder'),
      kind: l10n.t('tr_pendingOrder'),
    ),
    'modify_order' => (
      title: l10n.t('tr_editOrder'),
      kind: l10n.t('tr_pendingOrder'),
    ),
    _ => (title: action, kind: ''),
  };
}

/// An order state's name (`stateName`).
String orderStateName(L10n l10n, OrderState s) => l10n.t('tr_st_${s.name}');

/// A journal row's time: HH:mm of when the owner acted, in the interface's digits.
String orderTime(L10n l10n, JournalEntry e) {
  final at = e.submittedAt ?? e.updatedAt;
  return at == null ? '' : clockTime(at, lang: l10n.lang);
}

/// A date and time of an operation («٢٧ نوفمبر ٢٠٢٦، ٠٩:١٢»), isolated.
String operationTime(L10n l10n, DateTime at) {
  final lang = l10n.lang;
  return isolate(
    formatDate(
      lang == 'ar' ? 'd MMM y، HH:mm' : 'd MMM y, HH:mm',
      lang,
      at.toLocal(),
    ),
  );
}

/// The execution-state name of a broker recovery status (RecoveryPage.tsx `statusName`).
String recoveryStatusName(L10n l10n, String status) => l10n.t(switch (status) {
  'recovering' => 'rc_reconnecting',
  'reconciling' => 'rc_reconciling',
  _ => 'rc_paused',
});
