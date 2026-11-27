import '../../l10n/l10n.dart';

/// Android-only labels of the chats, search, agents list, groups and share picker screens.
/// Everything else uses Lonora's own catalog. Idempotent: the screens call it on first build;
/// the app may also call it at startup.
void registerChatsStrings() {
  final l10n = L10n.instance;
  if (l10n.has('chats_select')) return;
  l10n.register({
    // Row menu («Agent profile») and the selection entry.
    'chats_agentProfile': ['ملف الوكيل', 'Agent profile'],
    'chats_select': ['تحديد', 'Select'],
    // «وكيل جديد» opens Lonora's conversation: Lonora creates agents from chat.
    'chats_newAgentHint': [
      'اطلب من Lonora إنشاء الوكيل الذي تحتاجه',
      'Ask Lonora to create the agent you need',
    ],
    // Share target picker.
    'share_title': ['إرسال إلى…', 'Send to…'],
    // Groups (wording of Lonora Web's group page, apps/web/src/shell/agent/GroupPage.tsx).
    'groups_coordinator': ['المنسق', 'Coordinator'],
    'groups_addAgent': ['إضافة وكيل', 'Add an agent'],
    'groups_add': ['إضافة', 'Add'],
    'groups_openChat': ['فتح محادثة المجموعة', 'Open the group chat'],
    'groups_note': [
      'يحتفظ كل عضو بصلاحياته. ليست للمجموعة صلاحية مالية مشتركة.',
      'Each member keeps its own permissions. The group has no shared financial authority.',
    ],
    'groups_limit': [
      'يمكنك إضافة {0} وكيلًا على الأكثر إلى المجموعة.',
      'You can add up to {0} agents to a group.',
    ],
    'groups_remove': ['إزالة من المجموعة', 'Remove from the group'],
    // Leaving a group form with unsaved edits (Lonora Web, shell/navigation.tsx:95-135).
    'groups_leaveQ': ['مغادرة التعديلات؟', 'Leave the edits?'],
    'groups_leaveBody': [
      'ستفقد التعديلات غير المحفوظة.',
      'You will lose the unsaved edits.',
    ],
    'groups_keepEditing': ['متابعة التعديل', 'Keep editing'],
    'groups_discard': ['تجاهل', 'Discard'],
  });
}
