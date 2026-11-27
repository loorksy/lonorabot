// The unified search's paging (packages/core/src/search-feed.ts): one engine, `GET /search`
// (owner-wide, never an agent's), the tabs mapped onto its categories; «الكل» shows a few of
// each, a tab pages by 32. An empty query browses what is recent.
import '../../core/json.dart';
import '../../l10n/core/search_feed.dart';

export '../../l10n/core/search_feed.dart'
    show searchTabs, searchPage, searchSources, searchTabLabelKey;

/// One hit (`SearchResult`, packages/contracts/src/search.ts).
class SearchHit {
  const SearchHit({
    required this.category,
    required this.id,
    this.title = '',
    this.snippet = '',
    this.kind,
    this.agentId,
    this.groupId,
    this.threadId,
    this.threadAgentId,
    this.seq,
    this.role,
    this.createdAt,
  });

  final String category;
  final String id;
  final String title;
  final String snippet;
  final String? kind;
  final String? agentId;
  final String? groupId;
  final String? threadId;
  final String? threadAgentId;
  final int? seq;
  final String? role;
  final DateTime? createdAt;

  static SearchHit fromJson(Json j) => SearchHit(
    category: asStr(j['category']),
    id: asStr(j['id']),
    title: asStr(j['title']),
    snippet: asStr(j['snippet']),
    kind: asString(j['kind']),
    agentId: asString(j['agent_id']),
    groupId: asString(j['group_id']),
    threadId: asString(j['thread_id']),
    threadAgentId: asString(j['thread_agent_id']),
    seq: asInt(j['seq']),
    role: asString(j['role']),
    createdAt: asDate(j['created_at']),
  );
}

/// One section of results: a tab other than «all», its hits so far and its total.
class SearchSection {
  const SearchSection({
    required this.tab,
    required this.items,
    required this.count,
  });

  final String tab;
  final List<SearchHit> items;
  final int count;
}

/// One page of one category (null: every category).
typedef SearchFetch = Future<Json> Function(
  String q,
  String? category,
  int limit,
  int offset,
);

({Map<String, int> counts, Map<String, List<SearchHit>> results}) _read(
  Json response,
) => (
  counts: {
    for (final e in asJson(response['counts']).entries)
      e.key: asInt(e.value) ?? 0,
  },
  results: {
    for (final e in asJson(response['results']).entries)
      e.key: asJsonList(e.value).map(SearchHit.fromJson).toList(),
  },
);

/// The first screen of a tab for a query (search-feed.ts:47-79).
Future<List<SearchSection>> firstSearchPage(
  String q,
  String tab,
  SearchFetch fetch,
) async {
  if (tab == 'all') {
    final page = _read(await fetch(q, null, q.isNotEmpty ? 3 : 4, 0));
    return [
      for (final MapEntry(key: name, value: sources) in searchSources.entries)
        SearchSection(
          tab: name,
          items: [for (final c in sources) ...?page.results[c]],
          count: sources.fold(0, (sum, c) => sum + (page.counts[c] ?? 0)),
        ),
    ];
  }
  final sources = searchSources[tab] ?? const <String>[];
  final pages = [
    for (final c in sources) _read(await fetch(q, c, searchPage, 0)),
  ];
  return [
    SearchSection(
      tab: tab,
      items: [
        for (var i = 0; i < sources.length; i++)
          ...?pages[i].results[sources[i]],
      ],
      count: [
        for (var i = 0; i < sources.length; i++)
          pages[i].counts[sources[i]] ?? 0,
      ].fold(0, (a, b) => a + b),
    ),
  ];
}

/// The next 32 of one section, appended after what it already shows (search-feed.ts:82-101).
Future<SearchSection> moreSearchItems(
  String q,
  SearchSection section,
  SearchFetch fetch,
) async {
  final sources = searchSources[section.tab] ?? const <String>[];
  final pages = [
    for (final c in sources)
      _read(
        await fetch(
          q,
          c,
          searchPage,
          section.items.where((item) => item.category == c).length,
        ),
      ),
  ];
  return SearchSection(
    tab: section.tab,
    items: [
      ...section.items,
      for (var i = 0; i < sources.length; i++) ...?pages[i].results[sources[i]],
    ],
    count: section.count,
  );
}

/// The `GET /search` query of one page (search-feed.ts:31-41).
Map<String, Object?> searchQuery(
  String q,
  String? category,
  int limit,
  int offset,
) => {'q': q, 'limit': limit, 'offset': offset, 'category': ?category};
