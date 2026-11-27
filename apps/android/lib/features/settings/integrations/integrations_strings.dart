import '../../../l10n/l10n.dart';

/// Android-only labels of the integrations pages (integrations, model providers, trading
/// accounts, MCP servers, news and channels). The Web's own wording and its ar catalog are
/// reused (apps/web IntegrationsPage.tsx, ConnectionPages.tsx, lib/user_error.ts); the few
/// labels the Web never needed (confirmations, the saved-secrets list) are marked «Android».
void registerIntegrationsStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('ix_intro')) return;
  target.register(_integrationsStrings);
}

const Map<String, List<String>> _integrationsStrings = {
  'ix_intro': [
    'الحسابات والمصادر التي يصل إليها وكلاؤك. أي مصدر خارج هذه القائمة يتطلّب موافقتك أولًا.',
    'The accounts and sources your agents can reach. Any source outside this list needs your approval first.',
  ],
  // Trading accounts.
  'ix_tradingAccounts': ['حسابات التداول', 'Trading accounts'],
  'ix_tradingAccount': ['حساب التداول', 'Trading account'],
  'ix_linkAccount': ['ربط حساب تداول', 'Link a trading account'],
  'ix_addAccount': ['إضافة حساب تداول', 'Add a trading account'],
  'ix_linkBroker': ['ربط الوسيط', 'Link the broker'],
  'ix_simulationSnapshot': [
    'محاكاة باستخدام بيانات مستوردة',
    'Simulation with an imported snapshot',
  ],
  'ix_simulation': ['محاكاة', 'Simulation'],
  'ix_simulationAgents': ['محاكاة · {0}', 'Simulation · {0}'],
  'ix_noAgents': ['دون وكلاء', 'No agents'],
  'ix_broker': ['الوسيط', 'Broker'],
  'ix_accountType': ['نوع الحساب', 'Account type'],
  'ix_accountNumber': ['رقم الحساب', 'Account number'],
  'ix_accountHint': ['مثل: 7310', 'e.g. 7310'],
  'ix_region': ['المنطقة', 'Region'],
  'ix_accessTokenField': [
    'رمز الوصول — يُحفظ مشفّرًا ولا يُعرض مرة أخرى',
    'Access token — stored encrypted, never shown again',
  ],
  'ix_enterAccount': ['أدخل رقم الحساب', 'Enter the account number'],
  'ix_enterToken': ['أدخل رمز الوصول', 'Enter the access token'],
  'ix_checkFields': ['فحص الحقول', 'Check the fields'],
  'ix_fieldsValid': [
    'الحقول صحيحة، وهذا الحساب غير مرتبط بعد.',
    'The fields are valid, and this account is not linked yet.',
  ],
  'ix_testConnection': ['اختبار الاتصال', 'Test the connection'],
  'ix_connectionWorks': ['الاتصال يعمل', 'The connection works'],
  'ix_connectionWorksWho': ['الاتصال يعمل · {0}', 'The connection works · {0}'],
  'ix_symbolsAfterLink': [
    'بعد الربط تُجلب رموز التداول المتاحة من الحساب تلقائيًا، وتظهر في قوائم اختيار الزوج.',
    "After linking, the account's trading symbols are fetched from the broker and appear in the pair pickers.",
  ],
  'ix_linkTheAccount': ['ربط الحساب', 'Link the account'],
  'ix_accountLinked': ['رُبط الحساب', 'The account is linked'],
  'ix_balance': ['الرصيد', 'Balance'],
  'ix_availableSymbols': ['الرموز المتاحة', 'Available symbols'],
  'ix_availableSymbolsN': ['الرموز المتاحة · {0}', 'Available symbols · {0}'],
  'ix_fetchingSymbols': [
    'جارٍ جلب الرموز من {0}…',
    'Fetching the symbols from {0}…',
  ],
  'ix_symbolsNote': [
    'تُجلب من حساب الوسيط تلقائيًا، وتظهر في قوائم اختيار الزوج عند إنشاء وكيل وفي التفويض.',
    'Fetched from the broker account, and shown in the pair pickers when creating an agent and in delegation.',
  ],
  'ix_refreshSymbols': ['تحديث الرموز', 'Refresh the symbols'],
  'ix_agentsOnAccount': ['الوكلاء على هذا الحساب', 'Agents on this account'],
  'ix_noAgentOnAccount': [
    'لا يعمل أي وكيل على هذا الحساب.',
    'No agent works on this account.',
  ],
  // Android: the Mandate lives with each agent; nothing here switches trading.
  'ix_mandateNote': [
    'يُضبط تفويض كل وكيل من إعداداته؛ لا يوجد مفتاح تداول عام.',
    "Each agent's Mandate is set in its own settings; there is no global trading switch.",
  ],
  'ix_unlinkAccount': ['فصل الحساب', 'Unlink the account'],
  'ix_unlinkBody': [
    'يُفصل الحساب {0} لدى {1}.',
    'The account {0} at {1} is unlinked.',
  ],
  'ix_unlinkBodyNoNumber': [
    'يُفصل هذا الحساب لدى {0}.',
    'This account at {0} is unlinked.',
  ],
  'ix_unlinkAgents': [
    'يُلغى أي تفويض موقَّع على هذا الحساب، ويعود {0} إلى «تنفيذ بموافقة» دون حساب حتى تختار حسابًا آخر.',
    'Any signed delegation on this account is revoked, and {0} go back to «Execute with approval» without an account until you choose another one.',
  ],
  'ix_accountUnlinkedN': ['فُصل الحساب {0}', 'Account {0} is unlinked'],
  'ix_accountUnlinked': ['فُصل الحساب', 'The account is unlinked'],
  'ix_noAccountLinked': [
    'لا يوجد حساب تداول مرتبط.',
    'No trading account is linked.',
  ],
  'ix_simulationIntro': [
    'تتداول المحاكاة على بيانات سوق تستوردها: الرصيد والرموز وأسعارها وشموعها. استورد ملف لقطة لاستخدامها.',
    'A simulation trades against market data you import: the balance, the symbols, their prices and candles. Import a snapshot file to use it.',
  ],
  'ix_importSimulation': [
    'استيراد بيانات المحاكاة',
    'Import the simulation data',
  ],
  'ix_simulationImported': [
    'استُوردت بيانات المحاكاة',
    'The simulation data is imported',
  ],
  'ix_notJson': ['الملف ليس JSON صالحًا.', 'The file is not valid JSON.'],
  // Artificial intelligence.
  'ix_ai': ['الذكاء الاصطناعي', 'Artificial intelligence'],
  'ix_modelProviders': ['مزوّدو النماذج', 'Model providers'],
  'ix_notAddedYet': ['لم يُضف بعد', 'Not added yet'],
  'ix_keySaved': [
    'المفتاح محفوظ · لا يُعرض مرة أخرى',
    'Key saved · never shown again',
  ],
  'ix_credentialConfigured': ['تم إعداد مفتاح الوصول', 'Credential configured'],
  'ix_addCredential': ['أضف مفتاح المزود', 'Add a provider credential'],
  'ix_apiKey': ['مفتاح API', 'API key'],
  'ix_showKey': ['إظهار المفتاح', 'Show the key'],
  'ix_hideKey': ['إخفاء المفتاح', 'Hide the key'],
  'ix_keyEncrypted': [
    'يُحفظ المفتاح مشفّرًا ولا يُعرض مرة أخرى.',
    'The key is stored encrypted and is never shown again.',
  ],
  'ix_enterKey': ['أدخل مفتاح API', 'Enter the API key'],
  'ix_saveKey': ['حفظ المفتاح', 'Save the key'],
  'ix_saved': ['تم الحفظ', 'Saved'],
  'ix_catalogNote': [
    'نماذج كل مزوّد هي قائمة لونورا نفسها، وتُحدَّث مع لونورا.',
    "Each provider's models are Lonora's own list, updated with Lonora.",
  ],
  // Android: Lonora has no route that removes a provider key.
  'ix_replaceKeyNote': [
    'لا يُقرأ المفتاح بعد حفظه؛ احفظ مفتاحًا جديدًا لاستبداله.',
    'A saved key is never read back; save a new one to replace it.',
  ],
  'ix_signOutChatGptQ': ['تسجيل الخروج من ChatGPT؟', 'Sign out of ChatGPT?'],
  // Servers and repositories.
  'ix_servers': ['الخوادم والمستودعات', 'Servers and repositories'],
  'ix_addedOn': ['أُضيف {0}', 'added {0}'],
  'ix_trusted': ['موثوق', 'Trusted'],
  'ix_reviewNeeded': ['مراجعة مطلوبة', 'Review needed'],
  'ix_notApproved': ['غير معتمد', 'Not approved'],
  'ix_unnamedServer': ['خادم بلا اسم', 'Unnamed server'],
  'ix_mcpServerLine': ['خادم MCP · {0}', 'MCP server · {0}'],
  'ix_noTools': ['دون أدوات', 'No tools'],
  // The Web's `levelText` plurals (its ar catalog).
  'ix_readTool1': ['أداة قراءة واحدة', 'one read tool'],
  'ix_readTool2': ['أداتا قراءة', 'two read tools'],
  'ix_readToolsFew': ['{0} أدوات قراءة', '{0} read tools'],
  'ix_readToolsMany': ['{0} أداة قراءة', '{0} read tools'],
  'ix_writeTool1': [
    'أداة كتابة غير مالية واحدة',
    'one non-financial write tool',
  ],
  'ix_writeTool2': ['أداتا كتابة غير مالية', 'two non-financial write tools'],
  'ix_writeToolsFew': [
    '{0} أدوات كتابة غير مالية',
    '{0} non-financial write tools',
  ],
  'ix_writeToolsMany': [
    '{0} أداة كتابة غير مالية',
    '{0} non-financial write tools',
  ],
  'ix_noToolsDot': ['لا أدوات.', 'No tools.'],
  'ix_addMcp': ['إضافة خادم MCP', 'Add an MCP server'],
  'ix_addMcpTitle': ['إضافة MCP', 'Add MCP'],
  'ix_schemaChanged': [
    'تغيّر مخطط الخادم. راجع الأدوات قبل اعتمادها.',
    "The server's schema changed. Review the tools before approving them.",
  ],
  'ix_toolsLevels': ['الأدوات ومستوياتها', 'Tools and their levels'],
  'ix_fetchTools': [
    'اجلب الأدوات لمراجعتها قبل اعتماد الخادم.',
    'Fetch the tools to review them before approving the server.',
  ],
  'ix_blockedTools': [
    'تُرفض الأدوات التي قد تحرّك المال: {0}',
    'Tools that could move money are refused: {0}',
  ],
  'ix_reviewTools': ['مراجعة الأدوات', 'Review the tools'],
  'ix_approveSchema': ['اعتماد المخطط الجديد', 'Approve the new schema'],
  'ix_approveServer': ['اعتماد الخادم', 'Approve the server'],
  'ix_approveWrites': [
    'اعتماد مع الكتابة غير المالية',
    'Approve with non-financial writes',
  ],
  'ix_stopServer': ['إيقاف الخادم', 'Stop the server'],
  'ix_stopServerQ': ['إيقاف الخادم؟', 'Stop the server?'],
  'ix_mcpNote': [
    'لا تُمنح خوادم MCP أي أداة مالية؛ ولا تعمل أدوات الكتابة فيها إلا إذا اعتمدت الكتابة غير المالية.',
    'MCP servers are never given a financial tool; their write tools run only if you approve non-financial writes.',
  ],
  'ix_read': ['قراءة', 'Read'],
  'ix_nonFinancialWrite': ['كتابة غير مالية', 'Non-financial write'],
  'ix_schemaApproved': ['اعتُمد المخطط الجديد', 'The new schema is approved'],
  'ix_serverApproved': ['اعتُمد الخادم', 'The server is approved'],
  'ix_serverStopped': ['أُوقف الخادم', 'The server is stopped'],
  'ix_serverName': ['اسم الخادم', 'Server name'],
  'ix_serverNameHint': ['أدوات الأبحاث', 'Research tools'],
  'ix_connectionType': ['نوع الاتصال', 'Connection type'],
  'ix_serverAddress': ['عنوان الخادم', 'Server address'],
  'ix_authentication': ['المصادقة', 'Authentication'],
  'ix_noAuth': ['بدون مصادقة', 'No authentication'],
  'ix_accessToken': ['رمز الوصول', 'Access token'],
  'ix_enterServerName': ['أدخل اسم الخادم', 'Enter the server name'],
  'ix_mcpWorks': [
    'الاتصال يعمل · {0} أداة',
    'The connection works · {0} tools',
  ],
  'ix_remoteOnly': [
    'خوادم بعيدة فقط. تراجع أدواته وتعتمدها قبل أن يستخدمها أي وكيل.',
    'Remote servers only. You review and approve its tools before any agent uses them.',
  ],
  'ix_addServer': ['إضافة الخادم', 'Add the server'],
  'ix_serverAdded': ['أُضيف الخادم', 'The server is added'],
  // News and channels.
  'ix_newsChannels': ['الأخبار والقنوات', 'News and channels'],
  'ix_newsDomains': ['نطاقات الأخبار', 'News domains'],
  'ix_domainsNote': [
    'يقرأ الوكلاء الأخبار من هذه النطاقات فقط، ويذكرون المصدر والوقت مع كل معلومة.',
    'Agents read news from these domains only, and name the source and the time with every piece of information.',
  ],
  'ix_newDomain': ['نطاق جديد', 'New domain'],
  'ix_add': ['إضافة', 'Add'],
  'ix_invalidDomain': [
    'أدخل نطاقًا صحيحًا مثل example.com',
    'Enter a valid domain like example.com',
  ],
  'ix_removeX': ['إزالة {0}', 'Remove {0}'],
  'ix_removeQ': ['إزالة {0}؟', 'Remove {0}?'],
  'ix_removedX': ['أُزيل {0}', 'Removed {0}'],
  // Android: the trusted sources list (the Expo app's remove / restore).
  'ix_restoreX': ['استعادة {0}', 'Restore {0}'],
  'ix_removedCount': ['المُزالة: {0}', 'Removed: {0}'],
  'ix_rssFeeds': ['خلاصات RSS', 'RSS feeds'],
  'ix_noFeeds': ['لا توجد خلاصات', 'No feeds'],
  'ix_noFeedsDot': ['لا توجد خلاصات.', 'No feeds.'],
  'ix_feedLink': ['رابط خلاصة', 'Feed link'],
  'ix_invalidLink': [
    'أدخل رابطًا يبدأ بـ https://',
    'Enter a link that starts with https://',
  ],
  'ix_telegramLinkedTo': [
    'مرتبط · تصل التنبيهات إلى محادثتك، ورسائلك تصل إلى {0}',
    'Linked · alerts reach your chat, your messages reach {0}',
  ],
  'ix_telegramLinked': [
    'مرتبط · تصل التنبيهات إلى محادثتك، ورسائلك تصل إلى وكيل',
    'Linked · alerts reach your chat, your messages reach an agent',
  ],
  'ix_telegramNotLinked': [
    'غير مرتبط · يمكن أن تصلك التنبيهات في Telegram',
    'Not linked · alerts can reach you in Telegram',
  ],
  'ix_linked': ['مرتبط', 'Linked'],
  'ix_link': ['ربط', 'Link'],
  'ix_linkTelegram': ['ربط Telegram', 'Link Telegram'],
  'ix_botToken': ['رمز البوت', 'Bot token'],
  'ix_pasteValue': ['الصق القيمة هنا', 'Paste the value here'],
  'ix_messagesReach': ['تصل الرسائل إلى', 'Messages reach'],
  'ix_valueEncrypted': [
    'تُرسَل القيمة مشفّرة ولا تُعرض بعد الحفظ.',
    'The value is sent encrypted and is not shown after saving.',
  ],
  'ix_savedNever': ['محفوظ · لا يُعرض مرة أخرى', 'Saved · never shown again'],
  'ix_unlink': ['فصل', 'Unlink'],
  'ix_unlinkTelegramQ': ['فصل Telegram؟', 'Unlink Telegram?'],
  'ix_telegramUnlinked': ['فُصل Telegram', 'Telegram is unlinked'],
  'ix_tooShort': ['القيمة قصيرة جدًا', 'The value is too short'],
  'ix_savedSecurely': ['حُفظت بأمان', 'Saved securely'],
  // Skills.
  'ix_skills': ['المهارات', 'Skills'],
  'ix_noSkills': ['لا توجد مهارات.', 'No skills.'],
  'ix_builtInSkill': ['مدمجة', 'Built-in'],
  'ix_owner': ['المالك', 'Owner'],
  'ix_version': ['الإصدار {0}', 'version {0}'],
  'ix_undoVersion': ['التراجع عن هذا الإصدار', 'Undo this version'],
  'ix_undoVersionQ': ['التراجع عن هذا الإصدار؟', 'Undo this version?'],
  'ix_versionUndone': ['أُلغي إصدار المهارة', 'The skill version is undone'],
  // Android: the saved workspace secrets (GET /secrets, DELETE /secrets/{id}).
  'ix_secrets': ['البيانات السرّية المحفوظة', 'Saved secrets'],
  'ix_secretsNote': [
    'أسماؤها فقط: لا تُعرض أي قيمة. لا يُحذف سرّ يستخدمه اتصال.',
    'Names only: no value is ever shown. A secret a connection uses cannot be deleted.',
  ],
  'ix_deleteSecret': ['حذف «{0}»', 'Delete «{0}»'],
  'ix_deleteSecretQ': ['حذف «{0}»؟', 'Delete «{0}»?'],
  'ix_deleteSecretBody': [
    'يُحذف هذا السرّ من خادمك نهائيًا، ويفقده كل وكيل يستخدمه في أوامر مساحة العمل.',
    'The secret is deleted from your server for good, and every agent that uses it in workspace commands loses it.',
  ],
  'ix_secretDeleted': ['حُذف «{0}»', '«{0}» deleted'],
  // Error codes the Android catalog did not have (apps/web lib/user_error.ts).
  'connection_test_timeout': [
    'لم يصل رد على الاختبار في الوقت المحدد. لم يُحفظ شيء.',
    'The test did not get an answer in time. Nothing was saved.',
  ],
  'broker_secret_required': ['أدخل رمز الوصول.', 'Enter the access token.'],
  // Android: the server refuses to delete a secret a connection uses.
  'secret_in_use': [
    'يستخدم اتصالٌ هذا السرّ، فلا يمكن حذفه.',
    'A connection uses this secret, so it cannot be deleted.',
  ],
  'simulation_snapshot_required': [
    'استورد بيانات السوق قبل استخدام المحاكاة.',
    'Import a market snapshot before using the simulation.',
  ],
  'broker_credentials_rejected': [
    'رفض الوسيط بيانات المصادقة.',
    'Broker authentication was rejected.',
  ],
  'broker_account_not_found': [
    'لم يتم العثور على حساب الوسيط.',
    'Broker account not found.',
  ],
  'broker_disabled': [
    'اتصال الوسيط هذا معطّل.',
    'This broker connection is disabled.',
  ],
  'broker_connection_unavailable': [
    'الاتصال بالوسيط غير متاح.',
    'The broker connection is unavailable.',
  ],
  'model_rate_limited': [
    'تم بلوغ حد طلبات مزود النماذج. أعد المحاولة بعد قليل.',
    'The model provider rate limit was reached. Try again shortly.',
  ],
  'model_request_rejected': [
    'رفض مزود النموذج هذا الطلب.',
    'The model provider rejected this request.',
  ],
  'model_response_invalid': [
    'أعاد مزود النموذج استجابة غير قابلة للقراءة. حاول مجددًا.',
    'The model provider returned an unreadable response. Try again.',
  ],
  'invalid_request': [
    'تحقق من الحقول المطلوبة وأعد المحاولة.',
    'Check the required fields and try again.',
  ],
};
