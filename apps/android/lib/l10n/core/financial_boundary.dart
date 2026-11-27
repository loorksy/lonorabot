/// Port of packages/core/src/financial-boundary.ts: why the financial boundary did not send
/// (or could not confirm) a request, the operation, approval and run status lines.
library;

import 'core_tables.g.dart';
import 'text.dart';
import 'values.dart';

/// Why the financial boundary did not send (or could not confirm) a request; null if unknown
/// (financial-boundary.ts:54-61).
String? financialBoundaryError(String? code, String locale) {
  if (code == null || code.isEmpty) return null;
  return financialBoundaryMessages[code]?.pick(locale);
}

/// The one reason line under a financial operation's status: an uncertain result says it will
/// not be resent, a known not-sent cause says why, any other status has none
/// (financial-boundary.ts:89-105).
String? financialResultReason(String status, String? code, String locale) {
  if (status == 'ambiguous') {
    final text = code != null && code.isNotEmpty
        ? financialUncertainMessages[code]
        : null;
    return (text ?? financialUnconfirmed).pick(locale);
  }
  if (status == 'failed') return financialBoundaryError(code, locale);
  return null;
}

Object? _field(Object? value, String key) => value is Map ? value[key] : null;

/// The stage the server's evidence establishes for a durable financial operation, one of the
/// TS `OperationStatusKey` values (financial-boundary.ts:126-162).
String operationStatusKey(String status, [Object? details]) {
  final verification = _field(_field(details, 'verification'), 'status');
  final resolution = _field(details, 'resolution');
  switch (status) {
    case 'reserved':
      return 'preparing';
    case 'submitted':
      return 'awaiting_broker';
    case 'confirmed':
      if (verification == 'pending') return 'awaiting_broker';
      if (verification == 'unverified') return 'acknowledged_unverified';
      return 'confirmed';
    case 'failed':
      return _field(details, 'send_state') == 'not_sent'
          ? 'not_sent'
          : 'failed';
    case 'ambiguous':
      return 'uncertain';
    case 'resolved':
      if (_field(resolution, 'source') == 'owner') return 'resolved_by_owner';
      switch (_field(resolution, 'basis')) {
        case 'target_closed':
          return 'resolved_position_closed';
        case 'target_no_longer_pending':
          return 'resolved_order_gone';
        case 'target_changed':
          return 'resolved_target_changed';
        default:
          return 'resolved_unconfirmed';
      }
    default:
      return 'awaiting_reconciliation';
  }
}

/// The status line of a durable financial operation (financial-boundary.ts:198-201).
String operationStatusText(String status, Object? details, String locale) =>
    operationStatusTexts[operationStatusKey(status, details)]!.pick(locale);

/// One label per approval-card state (financial-boundary.ts:217-220).
String approvalStatusText(String status, String locale) =>
    (approvalStatusTexts[status] ?? approvalStatusTexts['completed']!).pick(
      locale,
    );

const Set<String> _unsettled = {'reserved', 'submitted', 'ambiguous'};

/// The tone of a decided approval's end state: ok, wait, warn or plain; a failed or
/// unconfirmed operation never reads as a success. [row] is the approval JSON
/// (`status`, `results[].status`) (financial-boundary.ts:225-242).
String approvalEndTone(Map<String, Object?> row) {
  final status = row['status'];
  final results = list(row['results']).map((r) => obj(r)['status']).toList();
  if (status == 'approved') return 'wait';
  if (status == 'drifted') return 'warn';
  if (status != 'completed') return 'plain';
  if (results.isNotEmpty && results.every((s) => s == 'confirmed')) return 'ok';
  return results.any(_unsettled.contains) ? 'warn' : 'plain';
}

/// "Broker ticket" before a broker reference (financial-boundary.ts:244-247).
String brokerTicketLabel(String locale) =>
    language(locale) == 'ar' ? 'تذكرة الوسيط' : 'Broker ticket';

/// The label before a price the broker returned with a result; [key] is `price` or
/// `execution_price` (financial-boundary.ts:249-254).
String brokerPriceLabel(String key, String locale) {
  final ar = language(locale) == 'ar';
  if (key == 'execution_price') return ar ? 'سعر التنفيذ' : 'Execution price';
  return ar ? 'سعر الوسيط' : 'Broker price';
}

/// The reason under a failed result no table explains; never «try again»
/// (financial-boundary.ts:256-263).
String failedResultFallback(String locale) => language(locale) == 'ar'
    ? 'لم يُنفَّذ هذا الطلب.'
    : 'This request was not carried out.';

/// The label before the broker's own sentence (financial-boundary.ts:265-268).
String brokerWordsLabel(String locale) =>
    language(locale) == 'ar' ? 'بكلمات الوسيط' : "In the broker's words";

/// One label per run status; unknown statuses read as queued (financial-boundary.ts:282-285).
String runStatusText(String status, String locale) =>
    (runStatusTexts[status] ?? runStatusTexts['queued']!).pick(locale);
