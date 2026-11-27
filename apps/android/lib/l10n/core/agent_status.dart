/// Port of packages/core/src/agent-status.ts: an agent's one status line and its watch list,
/// built only from the server's live state (AgentLiveState JSON).
library;

import '../bidi.dart' show dotSeparator;
import 'core_tables.g.dart';
import 'text.dart';
import 'trading_readiness.dart';
import 'values.dart';

/// The status labels in [locale]'s language (agent-status.ts:98-100).
AgentStatusText agentStatusText(String locale) =>
    agentStatusLabels[language(locale)]!;

String? _metricLabel(Object? metric, AgentStatusText text) =>
    agentStatusMetrics.contains(metric) ? text[metric as String] : null;

String _join(List<String?> parts) =>
    parts.where((part) => part != null && part.isNotEmpty).join(' ');

/// What one watch waits for, e.g. "XAUUSD above 2100" or "RSI 1h XAUUSD crosses above 70";
/// [watch] is an AgentWatchSummary JSON (agent-status.ts:109-141).
String watchCondition(Map<String, Object?> watch, String locale) {
  final text = agentStatusText(locale);
  final conditionKey = str(watch['condition']);
  final condition = truthy(conditionKey) ? text[conditionKey!] ?? '' : '';
  final levelValue = watch['level'];
  final level = levelValue != null && levelValue != '0'
      ? isolate(jsString(levelValue))
      : '';
  final symbolValue = str(watch['symbol']);
  final symbol = truthy(symbolValue) ? isolate(symbolValue!) : '';
  switch (watch['kind']) {
    case 'calendar':
      return '${text.calendar}$dotSeparator${text.due}';
    case 'account':
      return _join([
        text.account,
        _metricLabel(watch['metric'], text),
        condition,
        level,
      ]);
    case 'position':
      return _join([
        text.position,
        symbol,
        _metricLabel(watch['metric'], text),
        condition,
        level,
      ]);
    case 'indicator':
      final indicator = str(watch['indicator']);
      final timeframe = str(watch['timeframe']);
      return _join([
        truthy(indicator) ? isolate(indicator!.toUpperCase()) : '',
        truthy(timeframe) ? isolate(timeframe!) : '',
        symbol,
        condition,
        level,
      ]);
    case 'dynamic':
      return _join([symbol, text.pattern]);
    default:
      return _join([symbol, condition, level]);
  }
}

/// "until 17:00", with the date when it is not today; "until cancelled" without expiry
/// (agent-status.ts:143-153).
String watchUntil(Map<String, Object?> watch, String locale, DateTime now) {
  final text = agentStatusText(locale);
  final expires = watch['expires_at'];
  return truthy(expires)
      ? '${text.until} ${readinessTime(expires!, locale, now)}'
      : text.noExpiry;
}

/// «عملية غير مؤكَّدة», or «3 عمليات غير مؤكَّدة» for several (11+: «عملية»), as the capsule
/// (agent-status.ts:155-161).
String uncertainLine(num count, String locale) {
  final text = agentStatusText(locale);
  if (count <= 1) return text.uncertain;
  final n = isolate(jsString(count));
  if (language(locale) == 'en') return '$n ${text.uncertainMany}';
  return '$n ${count <= 10 ? 'عمليات' : 'عملية'} ${text.uncertainMany}';
}

/// The agent's one status line, most urgent first: paused → an unconfirmed operation → a
/// decision waiting for the owner → an order at the broker → explicit work → an active watch
/// → «نشط» (agent-status.ts:163-204).
String agentStatusLine(
  Map<String, Object?> state,
  String locale,
  DateTime now,
) {
  final text = agentStatusText(locale);
  final work = state['current_work'] is Map ? obj(state['current_work']) : null;
  if (state['state'] == 'paused') return text.paused;
  if (state['phase'] == 'uncertain') {
    final readiness = obj(state['trading_readiness']);
    return uncertainLine(
      readiness['state'] == 'uncertain'
          ? number(obj(readiness['params'])['count']) ?? 1
          : 1,
      locale,
    );
  }
  if (truthy(state['pending_card_id']) ||
      work?['kind'] == 'waiting_owner' ||
      (number(state['pending_approval_count']) ?? 0) > 0 ||
      (number(state['pending_authorization_count']) ?? 0) > 0) {
    return text.action_required;
  }
  if (state['phase'] == 'awaiting_broker' || work?['kind'] == 'broker') {
    return text.awaiting_broker;
  }
  if (work?['kind'] == 'analysing') return text.analysing;
  if (work?['kind'] == 'searching') return text.searching;
  if (state['state'] == 'action_required') return text.action_required;
  final watches = list(state['watches']);
  final stateName = str(state['state']) ?? '';
  if (state['phase'] != 'monitoring' || watches.isEmpty) {
    return text[stateName] ?? '';
  }
  if (watches.first == null) return text.monitoring;
  final first = obj(watches.first);
  final firstSymbol = str(first['symbol']);
  final subject = truthy(firstSymbol)
      ? isolate(firstSymbol!)
      : watchCondition(first, locale);
  final until = truthy(first['expires_at'])
      ? ' ${watchUntil(first, locale, now)}'
      : '';
  final rest = (number(state['watch_count']) ?? 0) - 1;
  final more = rest > 0
      ? '$dotSeparator${isolate(jsString(rest))} ${text.more}'
      : '';
  return '${text.monitoring} $subject$until$more';
}

/// The avatar between runs follows the server's phase (agent-status.ts:206-217); one of the
/// avatar's state ids.
String liveAvatarState(Map<String, Object?>? state) {
  if (state == null) return 'waiting';
  final name = state['state'];
  if (name == 'paused') return 'sleeping';
  if (name == 'degraded' || name == 'action_required') return 'warning';
  if (name == 'working') return 'working';
  if (state['phase'] == 'monitoring') return 'inspecting';
  return 'waiting';
}
