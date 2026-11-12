const messages = {
  analysis: {
    en: "This agent can analyze and monitor but cannot trade. Choose a broader permission to allow trading.",
    ar: "يمكن لهذا الوكيل التحليل والمتابعة، لكن لا يمكنه التداول. غيّر صلاحياته للسماح بالتداول.",
  },
  approval: {
    en: "Your approval is required for this specific financial action.",
    ar: "هذه العملية المالية المحددة تحتاج إلى موافقتك.",
  },
  authorization: {
    en: "The trading authorization is no longer valid. Review the current scope and authorize it again.",
    ar: "تفويض التداول لم يعد صالحًا. راجع النطاق الحالي ووقّع تفويضًا جديدًا.",
  },
  scope: {
    en: "This action is outside the signed trading scope. Review the account, markets and permitted actions.",
    ar: "هذه العملية خارج نطاق التفويض الموقّع. راجع الحساب والأسواق والعمليات المسموح بها.",
  },
  limits: {
    en: "A limit in the signed authorization prevents this action. Review its configured limits.",
    ar: "أحد حدود التفويض الموقّع يمنع هذه العملية. راجع الحدود التي حددتها.",
  },
  state: {
    en: "The current permissions could not be verified. Reload them before making changes.",
    ar: "تعذّر التحقق من الصلاحيات الحالية. أعد تحميلها قبل إجراء تغييرات.",
  },
} as const;

const categories: Readonly<Record<string, keyof typeof messages>> = {
  agent_analysis_only: "analysis",
  trade_approval_required: "approval",
  account_authority_required: "authorization",
  account_authority_unavailable: "authorization",
  account_authority_changed: "authorization",
  account_authority_expired_or_used: "authorization",
  account_authority_activation_unconfirmed: "authorization",
  account_authority_scope_changed: "scope",
  account_authority_scope_mismatch: "scope",
  account_authority_action_forbidden: "scope",
  account_authority_manual_permission_required: "scope",
  account_authority_volume_limit: "limits",
  account_authority_symbol_volume_limit: "limits",
  account_authority_position_limit: "limits",
  account_authority_pending_limit: "limits",
  account_authority_action_limit: "limits",
  account_authority_equity_floor: "limits",
  agent_permission_state_invalid: "state",
  agent_permission_scope_mismatch: "state",
};

/** Shared human explanations; callers keep their normal handling of other errors. */
export function agentPermissionError(code: string, locale: string): string | null {
  const category = Object.hasOwn(categories, code) ? categories[code] : undefined;
  return category ? messages[category][locale.startsWith("ar") ? "ar" : "en"] : null;
}
