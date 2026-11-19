/**
 * Owner-facing explanations for financial-boundary outcomes, shared by Web and Mobile.
 *
 * Every text says why nothing (new) was sent and what stays possible, in the owner's
 * language, instead of a raw code. Unknown codes return null so each client keeps its
 * normal handling.
 */

type Text = { readonly en: string; readonly ar: string };

const EXITS_EN =
  "Closing positions, cancelling pending orders and tightening stops remain available.";
const EXITS_AR = "يبقى إغلاق المراكز وإلغاء الأوامر المعلقة وتقريب وقف الخسارة متاحًا.";

const messages: Readonly<Record<string, Text>> = {
  broker_reconciliation_required: {
    en: `A previous operation on this market still needs broker verification, so this request was not sent. ${EXITS_EN}`,
    ar: `عملية سابقة على هذا السوق ما زالت تحتاج إلى تحقق من الوسيط، لذلك لم يُرسل هذا الطلب. ${EXITS_AR}`,
  },
  broker_reconciliation_pending: {
    en: `A previous operation on this market still needs broker verification, so this request was not sent. ${EXITS_EN}`,
    ar: `عملية سابقة على هذا السوق ما زالت تحتاج إلى تحقق من الوسيط، لذلك لم يُرسل هذا الطلب. ${EXITS_AR}`,
  },
  broker_observation_unavailable: {
    en: `The broker account state could not be verified, so new risk on this account is paused and this request was not sent. ${EXITS_EN}`,
    ar: `تعذّر التحقق من حالة حساب الوسيط، لذلك توقفت المخاطرة الجديدة على هذا الحساب ولم يُرسل هذا الطلب. ${EXITS_AR}`,
  },
  batch_halted_after_unconfirmed_result: {
    en: "Not sent: an earlier operation in this batch has no confirmed result yet.",
    ar: "لم يُرسل: عملية سابقة في هذه الدفعة لا تملك نتيجة مؤكدة بعد.",
  },
  target_state_not_reached: {
    en: "The broker shows the requested change was not applied.",
    ar: "يُظهر الوسيط أن التغيير المطلوب لم يُطبّق.",
  },
  order_filled_before_cancel: {
    en: "The order was filled before it could be cancelled. Check the resulting position.",
    ar: "نُفّذ الأمر قبل إلغائه. تحقّق من المركز الناتج.",
  },
  delete_blocked_unresolved_operation: {
    en: "This can’t be deleted yet: a trade linked to it still has no confirmed broker result. Settle that operation first; nothing was deleted.",
    ar: "لا يمكن الحذف الآن: صفقة مرتبطة به ما زالت بلا نتيجة مؤكدة من الوسيط. احسم تلك العملية أولًا؛ لم يُحذف شيء.",
  },
};

function language(locale: string): "ar" | "en" {
  return locale.startsWith("ar") ? "ar" : "en";
}

/** Why the financial boundary did not send (or could not confirm) a request; null if unknown. */
export function financialBoundaryError(
  code: string | null | undefined,
  locale: string,
): string | null {
  if (!code || !Object.hasOwn(messages, code)) return null;
  return messages[code][language(locale)];
}

const CHECK_EN = "Check your positions and orders before acting.";
const CHECK_AR = "تحقّق من مراكزك وأوامرك قبل أي إجراء.";

const UNCONFIRMED: Text = {
  en: `The broker's answer was not confirmed, so this will not be sent again. ${CHECK_EN}`,
  ar: `لم يتأكد رد الوسيط، لذلك لن يُرسل هذا الطلب مجددًا. ${CHECK_AR}`,
};

// After the send boundary nothing may be resent, so an uncertain result never reads as
// "not sent" or "try again", whatever code the executor recorded.
const uncertainMessages: Readonly<Record<string, Text>> = {
  broker_result_ambiguous: UNCONFIRMED,
  execution_interrupted_after_send: {
    en: `The request was interrupted after it was sent, so its result is not confirmed and it will not be sent again. ${CHECK_EN}`,
    ar: `انقطع الطلب بعد إرساله، فنتيجته غير مؤكدة ولن يُرسل مجددًا. ${CHECK_AR}`,
  },
  broker_result_mismatch: {
    en: `The broker's answer did not match this request, so its result is not confirmed and it will not be sent again. ${CHECK_EN}`,
    ar: `لم يطابق رد الوسيط هذا الطلب، فنتيجته غير مؤكدة ولن يُرسل مجددًا. ${CHECK_AR}`,
  },
  operation_in_progress: {
    en: "This request is still waiting for the broker's result. It will not be sent again.",
    ar: "ما زال هذا الطلب بانتظار نتيجة الوسيط. لن يُرسل مجددًا.",
  },
};

/**
 * The one reason line under a financial operation's status, identical on Web and Mobile:
 * an uncertain result says it will not be resent, a known not-sent cause says why, and
 * any other status needs no reason beyond its status line (null).
 */
export function financialResultReason(
  status: string,
  code: string | null | undefined,
  locale: string,
): string | null {
  if (status === "ambiguous") {
    const text = code && Object.hasOwn(uncertainMessages, code) ? uncertainMessages[code] : null;
    return (text ?? UNCONFIRMED)[language(locale)];
  }
  if (status === "failed") return financialBoundaryError(code, locale);
  return null;
}

export type OperationStatusKey =
  | "preparing"
  | "awaiting_broker"
  | "acknowledged_unverified"
  | "confirmed"
  | "not_sent"
  | "failed"
  | "uncertain"
  | "resolved_by_owner"
  | "resolved_position_closed"
  | "resolved_order_gone"
  | "resolved_target_changed"
  | "resolved_unconfirmed"
  | "awaiting_reconciliation";

function field(value: unknown, key: string): unknown {
  return value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined;
}

/**
 * The stage the server's evidence establishes for a durable financial operation. An
 * unverified or uncertain result is never "confirmed", and a broker-state resolution
 * says what was observed: a changed target is still live, never "gone".
 */
export function operationStatusKey(status: string, details?: unknown): OperationStatusKey {
  const verification = field(field(details, "verification"), "status");
  const resolution = field(details, "resolution");
  switch (status) {
    case "reserved":
      return "preparing";
    case "submitted":
      return "awaiting_broker";
    case "confirmed":
      if (verification === "pending") return "awaiting_broker";
      if (verification === "unverified") return "acknowledged_unverified";
      return "confirmed";
    case "failed":
      return field(details, "send_state") === "not_sent" ? "not_sent" : "failed";
    case "ambiguous":
      return "uncertain";
    case "resolved":
      if (field(resolution, "source") === "owner") return "resolved_by_owner";
      switch (field(resolution, "basis")) {
        case "target_closed":
          return "resolved_position_closed";
        case "target_no_longer_pending":
          return "resolved_order_gone";
        case "target_changed":
          return "resolved_target_changed";
        default:
          return "resolved_unconfirmed";
      }
    default:
      return "awaiting_reconciliation";
  }
}

const statusTexts: Readonly<Record<OperationStatusKey, Text>> = {
  preparing: { en: "Preparing — not sent", ar: "قيد التحضير — لم يُرسل" },
  awaiting_broker: { en: "Awaiting broker confirmation", ar: "بانتظار تأكيد الوسيط" },
  acknowledged_unverified: {
    en: "Broker acknowledged — resulting state unverified",
    ar: "أقرّ الوسيط بالطلب — الحالة الناتجة غير مُتحقق منها",
  },
  confirmed: { en: "Confirmed", ar: "مؤكد" },
  not_sent: { en: "Not sent", ar: "لم يُرسل" },
  failed: { en: "Failed", ar: "فشل" },
  uncertain: {
    en: "Outcome uncertain — it will not be sent again",
    ar: "نتيجة غير مؤكدة — لن تُرسل مجددًا",
  },
  resolved_by_owner: { en: "Resolved by owner", ar: "سوّاها المالك" },
  resolved_position_closed: {
    en: "Resolved — position no longer open",
    ar: "سُوّيت — لم يعد المركز مفتوحًا",
  },
  resolved_order_gone: {
    en: "Resolved — order no longer pending",
    ar: "سُوّيت — لم يعد الأمر معلقًا",
  },
  resolved_target_changed: {
    en: "Resolved — changed by another action; current state observed",
    ar: "سُوّيت — غيّره إجراء آخر؛ رُصدت الحالة الحالية",
  },
  resolved_unconfirmed: {
    en: "Resolved without broker confirmation",
    ar: "سُوّيت دون تأكيد من الوسيط",
  },
  awaiting_reconciliation: { en: "Awaiting reconciliation", ar: "بانتظار المطابقة" },
};

/** The status line for clients without their own message catalog (Mobile). */
export function operationStatusText(status: string, details: unknown, locale: string): string {
  return statusTexts[operationStatusKey(status, details)][language(locale)];
}

const approvalTexts: Readonly<Record<string, Text>> = {
  pending: { en: "Waiting for your approval", ar: "بانتظار موافقتك" },
  approved: { en: "Approved — awaiting broker result", ar: "تمت الموافقة — بانتظار نتيجة الوسيط" },
  rejected: { en: "Rejected", ar: "مرفوض" },
  cancelled: { en: "Cancelled", ar: "أُلغي" },
  expired: { en: "Expired", ar: "انتهت صلاحيته" },
  completed: { en: "Broker result", ar: "نتيجة الوسيط" },
};

/** One label per approval-card state, identical on Web and Mobile. */
export function approvalStatusText(status: string, locale: string): string {
  return (approvalTexts[status] ?? approvalTexts.completed)[language(locale)];
}

/** "Broker ticket" before a broker reference, so a bare number never stands alone. */
export function brokerTicketLabel(locale: string): string {
  return language(locale) === "ar" ? "تذكرة الوسيط" : "Broker ticket";
}

const runTexts: Readonly<Record<string, Text>> = {
  queued: { en: "Queued", ar: "في الانتظار" },
  leased: { en: "Starting", ar: "يبدأ العمل" },
  running: { en: "Working", ar: "يعمل" },
  waiting_input: { en: "Waiting for your reply", ar: "بانتظار ردك" },
  waiting_takeover: { en: "Waiting to resume", ar: "بانتظار الاستئناف" },
  completed: { en: "Completed", ar: "مكتمل" },
  failed: { en: "Failed", ar: "فشل" },
  cancelled: { en: "Cancelled", ar: "أُلغي" },
  paused: { en: "Paused", ar: "متوقف مؤقتًا" },
};

/** One label per run status, identical on Web and Mobile. */
export function runStatusText(status: string, locale: string): string {
  return (runTexts[status] ?? runTexts.queued)[language(locale)];
}
