// Realistic server answers for the WP-A2 pages, shaped as the local Lonora server sends them
// (verified with curl and the backend test). No real credential appears anywhere.
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';

import 'ext_harness.dart';

final agents = [
  Agent.fromJson({
    'id': 'a-lonora',
    'name': 'Lonora',
    'role': 'personal',
    'avatar': 'orb',
  }),
  Agent.fromJson({
    'id': 'a-gold',
    'name': 'متداول الذهب',
    'title': 'Gold desk',
    'avatar': 'face-smile',
    'color': '#E5A100',
    'trading_account_id': 'c-exness',
    'trading_symbol': 'XAUUSD',
    'trades_on_its_own': true,
  }),
  Agent.fromJson({
    'id': 'a-research',
    'name': 'Research Desk',
    'avatar': 'face-thoughtful',
    'color': '#429DFA',
  }),
];

final providersJson = [
  {'id': 'openai', 'configured': true},
  {
    'id': 'openai_chatgpt',
    'configured': true,
    'sign_in': {
      'email': 'owner@example.com',
      'plan': true,
      'sign_in_again': false,
      'signed_in': true,
    },
  },
  {'id': 'anthropic', 'configured': true},
  {'id': 'deepseek', 'configured': false},
  {'id': 'zai', 'configured': false},
  {'id': 'openrouter', 'configured': false},
];

final connectionsJson = [
  {
    'id': 'c-exness',
    'agent_id': null,
    'thread_id': null,
    'payload': {
      'provider': 'metaapi',
      'account_id': '7d1c2a40-5f2e-4c6b-9a77-0b1e2f3a4b5c',
      'region': 'london',
      'secret_id': 'sec-broker',
      'enabled': true,
    },
    'state': {
      'broker_identity': {
        'broker': 'Exness',
        'login': '7310455',
        'server': 'Exness-MT5Real8',
        'connection_version': 1,
      },
    },
    'version': 1,
    'created_at': '2026-11-02T08:00:00+00:00',
    'updated_at': '2026-11-02T08:00:00+00:00',
  },
  {
    'id': 'c-sim',
    'agent_id': null,
    'thread_id': null,
    'payload': {
      'provider': 'simulation',
      'account_id': 'paper-01',
      'region': null,
      'secret_id': null,
      'enabled': true,
    },
    'state': {},
    'version': 1,
    'created_at': '2026-11-20T08:00:00+00:00',
    'updated_at': '2026-11-20T08:00:00+00:00',
  },
];

final capabilitiesJson = {
  'trusted_sources': [
    {
      'id': 's-github',
      'kind': 'github',
      'identifier': 'github.com',
      'label': 'github.com',
      'effect_tier': 'read',
      'tools': [],
      'write_tools': [],
      'blocked_tools': [],
      'needs_review': false,
      'added_via': 'default',
      'active': true,
      'created_at': '2026-11-27T05:43:56+00:00',
    },
    {
      'id': 's-reuters',
      'kind': 'feed_domain',
      'identifier': 'reuters.com',
      'label': 'reuters.com',
      'needs_review': false,
      'added_via': 'owner_ui',
      'active': true,
      'created_at': '2026-11-03T10:00:00+00:00',
    },
    {
      'id': 's-ft',
      'kind': 'feed_domain',
      'identifier': 'ft.com',
      'label': 'ft.com',
      'needs_review': false,
      'added_via': 'owner_ui',
      'active': true,
      'created_at': '2026-11-03T10:00:00+00:00',
    },
    {
      'id': 's-old',
      'kind': 'feed_domain',
      'identifier': 'old.example.com',
      'label': 'old.example.com',
      'needs_review': false,
      'added_via': 'owner_ui',
      'active': false,
      'created_at': '2026-11-01T10:00:00+00:00',
    },
    {
      'id': 's-mcp',
      'kind': 'mcp_server',
      'identifier': 'm-research',
      'label': 'Research tools',
      'effect_tier': 'read',
      'tools': ['search', 'fetch_page', 'save_note'],
      'write_tools': ['save_note'],
      'blocked_tools': [],
      'needs_review': false,
      'added_via': 'owner_ui',
      'active': true,
      'created_at': '2026-11-10T10:00:00+00:00',
    },
  ],
  'skills': [
    {
      'resource_id': 'sk-risk',
      'skill_id': 'risk-check',
      'title': 'Risk check',
      'version': '3',
      'agent_id': 'a-gold',
      'agent_name': 'متداول الذهب',
      'provenance': 'external',
      'repository': 'acme/trading-skills',
      'enabled': true,
      'undone': false,
      'can_undo': true,
    },
    {
      'resource_id': 'sk-charts',
      'skill_id': 'chart-reading',
      'title': 'Chart reading',
      'version': null,
      'agent_id': null,
      'agent_name': null,
      'provenance': 'bundled',
      'enabled': true,
      'undone': false,
      'can_undo': false,
    },
  ],
  'mcp_servers': [
    {
      'connection_id': 'm-research',
      'name': 'Research tools',
      'enabled': true,
      'trusted_tier': 'read',
      'trusted_tools': ['search', 'fetch_page', 'save_note'],
      'write_tools': ['save_note'],
      'blocked_tools': [],
      'tool_titles': {'search': 'Search the web', 'fetch_page': 'Read a page'},
      'tool_titles_kept': true,
      'trust_source_id': 's-mcp',
      'operator_declared': false,
      'last_used_at': null,
    },
    {
      'connection_id': 'm-calendar',
      'name': 'Calendar',
      'enabled': true,
      'trusted_tier': null,
      'trusted_tools': [],
      'write_tools': [],
      'blocked_tools': [],
      'tool_titles': {},
      'tool_titles_kept': false,
      'trust_source_id': null,
      'operator_declared': false,
      'last_used_at': null,
    },
  ],
  'integrations': [
    {
      'id': 'i-feed',
      'type': 'news_feed',
      'name': 'feeds.reuters.com',
      'domain': 'feeds.reuters.com',
      'enabled': true,
    },
    {
      'id': 'i-telegram',
      'type': 'telegram',
      'name': 'Telegram',
      'enabled': true,
      'deliver_to_agent_name': 'Lonora',
    },
    {
      'id': 'i-calendar',
      'type': 'economic_calendar',
      'name': 'Forex calendar',
      'enabled': true,
    },
  ],
  'built_in': [
    {'capability': 'web_search', 'state': 'ready', 'via': 'searxng'},
    {'capability': 'web_fetch', 'state': 'ready', 'via': null},
    {'capability': 'news_feeds', 'state': 'ready', 'via': 'public_urls'},
    {'capability': 'economic_calendar', 'state': 'not_connected', 'via': null},
    {'capability': 'workspace_execution', 'state': 'ready', 'via': null},
  ],
  'authority': 'presentation_only; no capability carries money authority',
};

final secretsJson = [
  {
    'id': 'sec-gh',
    'name': 'GITHUB_TOKEN',
    'updated_at': '2026-11-12T09:00:00+00:00',
  },
];

final routingJson = {
  'mode': 'unified',
  'unified': {'provider': 'openai', 'model': 'gpt-5'},
  'routes': {
    'realtime_voice': {'provider': 'openai', 'model': 'gpt-live-1'},
  },
};

List<Json> openAiModels = [
  {
    'id': 'gpt-5',
    'provider': 'openai',
    'name': 'GPT-5',
    'capabilities': ['text', 'tools', 'vision', 'reasoning'],
    'verified': true,
  },
  {
    'id': 'gpt-5-mini',
    'provider': 'openai',
    'name': 'GPT-5 mini',
    'capabilities': ['text', 'tools', 'vision', 'reasoning'],
    'verified': true,
  },
  {
    'id': 'gpt-4',
    'provider': 'openai',
    'name': 'GPT-4',
    'capabilities': ['text', 'tools'],
    'verified': true,
  },
];

List<Json> anthropicModels = [
  {
    'id': 'claude-opus-5',
    'provider': 'anthropic',
    'name': 'Claude Opus 5',
    'capabilities': ['text', 'tools', 'vision', 'reasoning'],
    'verified': true,
  },
  {
    'id': 'claude-experimental',
    'provider': 'anthropic',
    'name': 'Claude Experimental',
    'capabilities': [],
    'verified': false,
  },
];

Json agentSummary(String model, String name, String chosenBy) => {
  'record': {
    'revision': 2,
    'preference': {
      'primary': {'provider': 'openai', 'model': model},
      'fallbacks': [],
    },
    'chosen_by': chosenBy,
  },
  'current': {'provider': 'openai', 'model': model, 'name': name},
};

/// A 30-day series with a realistic shape (weekday peaks), in Asia/Riyadh.
Json seriesJson({String period = 'month', double scale = 1}) {
  final hourly = period == 'day';
  final count = hourly ? 24 : (period == 'week' ? 7 : 30);
  final points = <Json>[];
  for (var i = 0; i < count; i++) {
    final future = hourly && i > 14;
    final cost = future ? null : (0.05 + ((i * 37) % 11) * 0.09) * scale;
    final start = hourly
        ? '2026-11-27T${i.toString().padLeft(2, '0')}:00:00+03:00'
        : '2026-${_day(count - 1 - i)}T00:00:00+03:00';
    points.add({
      'start': start,
      'cost_usd': cost,
      'input_tokens': future ? null : 42000 + i * 900,
      'output_tokens': future ? null : 6100 + i * 120,
      'cached_tokens': future ? null : 18000 + i * 400,
      'tokens': future ? null : 48100 + i * 1020,
      'requests': future ? null : 31 + i,
      'unpriced_requests': future ? null : 0,
    });
  }
  return {
    'period': period,
    'bucket': hourly ? 'hour' : 'day',
    'timezone': 'Asia/Riyadh',
    'agent_id': null,
    'prices_as_of': 'pi-ai@1.6.0',
    'window': {
      'start': '2026-10-29T00:00:00+03:00',
      'end': '2026-11-27T14:30:00+03:00',
    },
    'previous': {
      'cost_usd': 9.82 * scale,
      'input_tokens': 1100000,
      'output_tokens': 160000,
      'cached_tokens': 400000,
      'tokens': 1260000,
      'requests': 980,
      'unpriced_requests': 0,
      'start': '2026-09-29T00:00:00+03:00',
      'end': '2026-10-28T14:30:00+03:00',
    },
    'points': points,
    'totals': {
      'cost_usd': 12.47 * scale,
      'input_tokens': 1640000,
      'output_tokens': 230000,
      'cached_tokens': 610000,
      'tokens': 1870000,
      'requests': 1320,
      'unpriced_requests': 12,
    },
    'month': {
      'start': '2026-11-01T00:00:00+03:00',
      'spent_usd': 11.9 * scale,
      'projected_usd': 13.22 * scale,
      'days_in_month': 30,
      'day_of_month': 27,
      'unpriced_requests': 12,
    },
  };
}

/// «11-27» minus [back] days, as MM-DD.
String _day(int back) {
  final d = DateTime.utc(2026, 11, 27).subtract(Duration(days: back));
  return '${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}

final rankJson = {
  'period': 'month',
  'timezone': 'Asia/Riyadh',
  'agent_id': null,
  'prices_as_of': 'pi-ai@1.6.0',
  'window': {
    'start': '2026-10-29T00:00:00+03:00',
    'end': '2026-11-27T14:30:00+03:00',
  },
  'totals': {
    'cost_usd': 12.47,
    'input_tokens': 1640000,
    'output_tokens': 230000,
    'cached_tokens': 610000,
    'tokens': 1870000,
    'requests': 1320,
    'unpriced_requests': 12,
  },
  'agents': [
    {
      'agent_id': 'a-gold',
      'agent_name': 'متداول الذهب',
      'cost_usd': 7.9,
      'tokens': 1100000,
      'requests': 800,
      'unpriced_requests': 0,
    },
    {
      'agent_id': 'a-lonora',
      'agent_name': 'Lonora',
      'cost_usd': 4.2,
      'tokens': 700000,
      'requests': 480,
      'unpriced_requests': 12,
    },
    {
      'agent_id': null,
      'agent_name': null,
      'cost_usd': 0.37,
      'tokens': 70000,
      'requests': 40,
      'unpriced_requests': 0,
    },
  ],
  'models': [
    {
      'provider': 'openai',
      'model': 'gpt-5',
      'cost_usd': 9.1,
      'tokens': 1300000,
      'requests': 900,
      'unpriced_requests': 0,
    },
    {
      'provider': 'anthropic',
      'model': 'claude-opus-5',
      'cost_usd': 3.37,
      'tokens': 500000,
      'requests': 408,
      'unpriced_requests': 0,
    },
    {
      'provider': 'openai',
      'model': 'scripted-local-fixture',
      'cost_usd': null,
      'tokens': 70000,
      'requests': 12,
      'unpriced_requests': 12,
    },
  ],
};

final summaryJson = {
  'input_tokens': 18400000,
  'output_tokens': 2300000,
  'cached_tokens': 7100000,
};

/// An instant on today's local date at a fixed local time. The running page reads its times
/// against the real clock (the time alone today, the date with it on another day), so its
/// fixtures follow the date and its goldens hold on any day.
String todayAt(int hour, int minute, {int second = 0}) {
  final now = DateTime.now();
  return DateTime(
    now.year,
    now.month,
    now.day,
    hour,
    minute,
    second,
  ).toUtc().toIso8601String();
}

final runningJson = {
  'listed_at': todayAt(11, 29, second: 50),
  'stale': false,
  'stopping_all': false,
  'processes': [
    {
      'pid': 4121,
      'agent_id': 'a-gold',
      'agent_name': 'متداول الذهب',
      'command': 'python backtest.py --symbol XAUUSD --days 90',
      'started_at': todayAt(11, 2),
      'stopping': false,
    },
    {
      'pid': 4188,
      'agent_id': 'a-gold',
      'agent_name': 'متداول الذهب',
      'command': 'tail -f logs/feed.log',
      'started_at': todayAt(9, 40),
      'stopping': true,
    },
    {
      'pid': 512,
      'agent_id': 'a-research',
      'agent_name': 'Research Desk',
      'command': 'node scrape.js https://example.com/report',
      // Another day, of a past year: its label («May 2, 2025 6:15 PM») is the same
      // whatever day the goldens run.
      'started_at': DateTime(2025, 5, 2, 18, 15).toUtc().toIso8601String(),
      'stopping': false,
    },
  ],
};

List<Run> activeRuns() => [
  Run.fromJson({
    'id': 'r-1',
    'thread_id': 't-gold',
    'agent_id': 'a-gold',
    'status': 'running',
    'trigger': 'routine',
    'background': true,
    'model_metadata': {
      'activity': {'kind': 'tool.started', 'name': 'market_quote'},
    },
    'created_at': todayAt(11, 20),
  }),
  Run.fromJson({
    'id': 'r-2',
    'thread_id': 't-lonora',
    'agent_id': 'a-lonora',
    'status': 'waiting_input',
    'trigger': 'user',
    'created_at': todayAt(10, 5),
  }),
  Run.fromJson({
    'id': 'r-2-child',
    'thread_id': 't-lonora',
    'agent_id': 'a-lonora',
    'parent_run_id': 'r-2',
    'status': 'queued',
    'created_at': todayAt(10, 6),
  }),
  Run.fromJson({
    'id': 'r-done',
    'thread_id': 't-research',
    'agent_id': 'a-research',
    'status': 'completed',
    'created_at': todayAt(9, 0),
  }),
];

/// Every answer the integrations page reads.
void integrationsRoutes(ScriptedApi api) {
  api
    ..on('GET /capabilities', (_) => capabilitiesJson)
    ..on('GET /trading/connections', (_) => connectionsJson)
    ..on('GET /providers', (_) => providersJson)
    ..on('GET /secrets', (_) => secretsJson);
}

void modelsRoutes(ScriptedApi api) {
  api
    ..on('GET /settings/models', (_) => routingJson)
    ..on('GET /providers', (_) => providersJson)
    ..on('GET /providers/openai/models', (_) => openAiModels)
    ..on('GET /providers/anthropic/models', (_) => anthropicModels)
    ..on('GET /providers/openai_chatgpt/models', (_) => <Json>[])
    ..on(
      'GET /agents/a-lonora/model/summary',
      (_) => agentSummary('gpt-5', 'GPT-5', 'inherited'),
    )
    ..on(
      'GET /agents/a-gold/model/summary',
      (_) => agentSummary('gpt-5-mini', 'GPT-5 mini', 'owner'),
    )
    ..on(
      'GET /agents/a-research/model/summary',
      (_) => {
        'record': {'revision': 0, 'chosen_by': null},
        'current': {'provider': null, 'model': null, 'name': null},
      },
    );
}

void usageRoutes(ScriptedApi api) {
  api
    ..on('GET /usage/series', (_) => seriesJson())
    ..on('GET /usage/rank', (_) => rankJson)
    ..on('GET /usage/summary', (_) => summaryJson);
}
