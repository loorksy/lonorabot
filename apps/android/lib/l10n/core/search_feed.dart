/// The unified search's tabs (packages/core/src/search-feed.ts) and the labels the Expo app
/// gives them (apps/mobile/components/shell/unified-search.tsx:286-293).
library;

/// The tabs in order; «الكل» shows a few of each (search-feed.ts:7-8).
const List<String> searchTabs = [
  'all',
  'chats',
  'messages',
  'tasks',
  'files',
  'other',
];

/// One tab pages by this many results (search-feed.ts:14).
const int searchPage = 32;

/// The engine's categories behind each tab but «all» (search-feed.ts:15-21).
const Map<String, List<String>> searchSources = {
  'chats': ['chats'],
  'messages': ['messages'],
  'tasks': ['tasks'],
  'files': ['files'],
  'other': ['knowledge', 'skills'],
};

/// The catalog key of a tab's chip label (unified-search.tsx:286-293).
String searchTabLabelKey(String tab) => switch (tab) {
  'all' => 'sh_sAll',
  'chats' => 'sh_sChats',
  'messages' => 'sh_sMessages',
  'tasks' => 'sh_sTasks',
  'files' => 'sh_sFiles',
  _ => 'sh_sOther',
};
