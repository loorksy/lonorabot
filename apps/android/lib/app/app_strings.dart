import '../features/agents/profile/agent_strings.dart';
import '../features/attention/attention_strings.dart';
import '../features/auth/auth_strings.dart';
import '../features/cards/cards_strings.dart';
import '../features/charts/charts_strings.dart';
import '../features/chats/chats_strings.dart';
import '../features/conversation/conversation_strings.dart';
import '../features/files/files_strings.dart';
import '../features/market/market_strings.dart';
import '../features/me/me_strings.dart';
import '../features/rich/rich_strings.dart';
import '../features/routines/routines_strings.dart';
import '../features/settings/integrations/integrations_strings.dart';
import '../features/settings/models/models_strings.dart';
import '../features/settings/running/running_strings.dart';
import '../features/settings/settings_core_strings.dart';
import '../features/settings/usage/usage_strings.dart';
import '../features/skills/skills_strings.dart';
import '../features/tasks/tasks_strings.dart';
import '../features/voice/voice_strings.dart';
import '../l10n/l10n.dart';
import '../platform/platform_strings.dart';

/// Android-only shell labels (tab destinations). Everything else uses Lonora's own catalog.
void registerAppStrings() => L10n.instance.register({
  'android_market': ['السوق', 'Market'],
  'android_me': ['أنا', 'Me'],
  'android_attention': ['يحتاج انتباهك', 'Needs your attention'],
});

/// Every feature's Android-only labels, registered once at startup. Screens also register their own
/// table on first build (idempotent), so this only makes the catalog complete up front.
void registerAllStrings() {
  final l10n = L10n.instance;
  registerAppStrings();
  registerAuthStrings(l10n);
  registerMeStrings(l10n);
  registerSettingsCoreStrings(l10n);
  registerIntegrationsStrings(l10n);
  registerModelsStrings(l10n);
  registerUsageStrings(l10n);
  registerRunningStrings(l10n);
  registerChatsStrings();
  registerConversationStrings(l10n);
  registerRichStrings(l10n);
  registerCardsStrings(l10n);
  registerAgentStrings(l10n);
  registerSkillsStrings(l10n);
  registerRoutinesStrings(l10n);
  registerTasksStrings(l10n);
  registerAttentionStrings(l10n);
  registerMarketStrings(l10n);
  registerChartsStrings(l10n);
  registerFilesStrings(l10n);
  registerVoiceStrings(l10n);
  registerPlatformStrings(l10n);
}
