/// What one attention item says (apps/mobile/lib/attention-labels.ts): each attention code's
/// label is in the catalog as `attention.<code>`, a refused model's family line as
/// `attention.model.<reason>` (filled with its `{provider}`).
library;

import 'l10n.dart';

/// The title of an attention item, as the web's useAttentionTitle: a refused model names its
/// provider and the failure family, never the provider's message (attention-labels.ts:44-54).
/// [reason] and [providerName] are the item's `details.reason` / `details.provider_name`.
///
/// A code this app version does not know yet reads as `attentionUpdated` («تم تحديث النشاط»)
/// instead of a raw key (the TS has no such case: its codes are a closed union).
String attentionTitle(
  L10n l10n,
  String code, {
  String? reason,
  String? providerName,
}) {
  final family =
      code == 'model_access_failed' && reason != null && reason.isNotEmpty
      ? 'attention.model.$reason'
      : null;
  if (family == null || !l10n.has(family)) {
    final key = 'attention.$code';
    return l10n.t(l10n.has(key) ? key : 'attentionUpdated');
  }
  final provider = providerName != null && providerName.isNotEmpty
      ? providerName
      : l10n.t('attentionModelEndpoint');
  return l10n.t(family, const [], {'provider': provider});
}
