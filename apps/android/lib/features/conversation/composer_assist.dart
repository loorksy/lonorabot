// The composer's @mentions and «/» commands, ported from Lonora's shared rules
// (packages/core/src/composer-mentions.ts, composer-commands.ts, message-parts.ts
// `pendingVoiceRich`) and the command rows of apps/mobile/lib/commands.ts and
// apps/web/src/conversation/commands.tsx. Pure Dart: the list widget is assist_list.dart.
// Offsets are UTF-16 code units, as in the TypeScript and in TextEditingController.
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../l10n/l10n.dart';
import '../chats/chat_text.dart' show foldSearch;
import '../skills/skills_data.dart' show SkillResource;

// ---------------------------------------------------------------- mentions

final RegExp _mentionQuery = RegExp(r'(?:^|\s)@([^\s@]*)$');

/// What follows the «@» being typed just before the caret, else null.
String? mentionQuery(String textBeforeCaret) =>
    _mentionQuery.firstMatch(textBeforeCaret)?.group(1);

/// The agents whose name holds [query] (not folded), paused agents left out.
List<Agent> mentionCandidates(Iterable<Agent> members, String query) {
  final needle = query.toLowerCase();
  return [
    for (final a in members)
      if (!a.paused && a.name.toLowerCase().contains(needle)) a,
  ];
}

/// A direct chat offers every other agent as a guest, never its own agent [self]; a group
/// offers every member. No cap on how many are named.
List<Agent> guestCandidates(
  List<Agent> candidates, {
  required bool direct,
  String? self,
}) => direct
    ? [
        for (final a in candidates)
          if (a.id != self) a,
      ]
    : candidates;

/// One committed «@name» in the field: [agentId] null is «@الكل» (with the collaboration
/// [sessionId] it addresses in a direct chat).
class MentionRange {
  const MentionRange({
    required this.agentId,
    required this.token,
    required this.start,
    required this.end,
    this.sessionId,
  });

  final String? agentId;
  final String? sessionId;
  final String token;
  final int start;
  final int end;

  MentionRange shifted(int delta) => MentionRange(
    agentId: agentId,
    sessionId: sessionId,
    token: token,
    start: start + delta,
    end: end + delta,
  );

  Json toJson() => {
    'agent_id': agentId,
    'session_id': ?sessionId,
    'token': token,
    'start': start,
    'end': end,
  };

  /// A saved range, or null when it is malformed.
  static MentionRange? fromJson(Object? value) {
    if (value is! Map) return null;
    final j = asJson(value);
    final agent = j['agent_id'];
    final session = j['session_id'];
    final token = j['token'];
    final start = j['start'];
    final end = j['end'];
    if ((agent != null && agent is! String) ||
        (session != null && session is! String) ||
        token is! String ||
        start is! int ||
        end is! int ||
        start < 0 ||
        end != start + token.length) {
      return null;
    }
    return MentionRange(
      agentId: agent as String?,
      sessionId: session as String?,
      token: token,
      start: start,
      end: end,
    );
  }

  @override
  bool operator ==(Object other) =>
      other is MentionRange &&
      other.agentId == agentId &&
      other.sessionId == sessionId &&
      other.token == token &&
      other.start == start &&
      other.end == end;

  @override
  int get hashCode => Object.hash(agentId, sessionId, token, start, end);

  @override
  String toString() => 'MentionRange($agentId, $token, $start-$end)';
}

/// Who a message addresses (`mention_agent_ids`, `mention_all`, `collaboration_session_id`).
typedef MentionAddress = ({List<String> agentIds, bool all, String? sessionId});

/// Rebases committed ranges through one edit from [before] to [after]: a range the edit
/// touches is uncommitted.
List<MentionRange> rebaseMentions(
  String before,
  String after,
  List<MentionRange> ranges,
) {
  var start = 0;
  while (start < before.length &&
      start < after.length &&
      before.codeUnitAt(start) == after.codeUnitAt(start)) {
    start++;
  }
  var end = before.length;
  var nextEnd = after.length;
  while (end > start &&
      nextEnd > start &&
      before.codeUnitAt(end - 1) == after.codeUnitAt(nextEnd - 1)) {
    end--;
    nextEnd--;
  }
  final delta = after.length - before.length;
  return [
    for (final r in ranges)
      if (r.end <= start) r else if (r.start >= end) r.shifted(delta),
  ];
}

/// Whether what follows «@» starts «الكل» or one of its other names.
bool matchesEveryone(String query) {
  final wanted = foldSearch(query);
  return const [
    'الكل',
    'all',
    'everyone',
    'الجميع',
  ].any((name) => foldSearch(name).startsWith(wanted));
}

bool _holds(String text, MentionRange r) =>
    r.start >= 0 &&
    r.end <= text.length &&
    text.substring(r.start, r.end) == r.token;

/// Who [text] addresses. In a group «@الكل» names every member ([everyone]; the server
/// skips a paused one); in a direct chat it addresses the open collaboration session.
MentionAddress mentionAddress(
  String text,
  List<MentionRange> ranges, {
  List<String>? everyone,
}) {
  final valid = [
    for (final r in ranges)
      if (_holds(text, r)) r,
  ];
  final all = valid.any((r) => r.agentId == null);
  final named = [for (final r in valid) ?r.agentId];
  if (all && everyone != null) {
    return (
      agentIds: {...named, ...everyone}.toList(),
      all: false,
      sessionId: null,
    );
  }
  return (
    agentIds: named.toSet().toList(),
    all: all,
    sessionId: valid.where((r) => r.agentId == null).firstOrNull?.sessionId,
  );
}

/// [text] cut at its committed tokens ([mark] true), for the field's marking.
List<({String text, bool mark})> mentionSegments(
  String text,
  List<MentionRange> ranges,
) {
  final valid = [
    for (final r in ranges)
      if (_holds(text, r)) r,
  ]..sort((a, b) => a.start.compareTo(b.start));
  final out = <({String text, bool mark})>[];
  var at = 0;
  for (final r in valid) {
    if (r.start < at) continue;
    if (r.start > at) out.add((text: text.substring(at, r.start), mark: false));
    out.add((text: r.token, mark: true));
    at = r.end;
  }
  if (at < text.length) out.add((text: text.substring(at), mark: false));
  return out;
}

String _escape(String value) =>
    value.replaceAllMapped(RegExp(r'[.*+?^${}()|[\]\\]'), (m) => '\\${m[0]}');

final Map<String, RegExp> _patterns = {};

/// «@name» for the conversation's agent [names] (longest first) and «@الكل»; an LRM may
/// precede it (apps/web/src/conversation/Markdown.tsx `mentionPattern`). Group 1 is the name.
RegExp mentionPattern(List<String> names) {
  final key = names.join('\n');
  final cached = _patterns[key];
  if (cached != null) return cached;
  final all = [...names.where((n) => n.isNotEmpty), 'الكل', 'all']
    ..sort((a, b) => b.length.compareTo(a.length));
  if (_patterns.length > 32) _patterns.clear();
  return _patterns[key] = RegExp(
    '\u200e?@(${all.map(_escape).join('|')})(?=\$|[\\s.,،!?؟:؛)\\]])',
  );
}

/// The names a conversation's messages mark as mentions: the group's members in a group, every
/// agent in a direct chat (apps/web/src/shell/pages.tsx), as one string (selectors compare it).
String mentionNamesKey(Map<String, Agent> agents, Group? group) {
  final names = group == null
      ? [for (final a in agents.values) a.name]
      : [for (final id in group.memberIds) ?agents[id]?.name];
  return names.where((n) => n.isNotEmpty).join('\n');
}

// ---------------------------------------------------------------- commands

/// The built-in commands, in the order a chat offers them.
const commandIds = ['task', 'search', 'summary', 'chart', 'call', 'clear'];

/// The English name of each command, typed in any language (COMMAND_ALIAS).
const commandAlias = {
  'task': 'task',
  'search': 'search',
  'summary': 'summary',
  'chart': 'chart',
  'call': 'call',
  'clear': 'clear',
};

const _commandNames = {
  'task': 'cmdTask',
  'search': 'cmdSearch',
  'summary': 'cmdSummary',
  'chart': 'cmdChart',
  'call': 'cmdCall',
  'clear': 'cmdClear',
};

/// One row of the «/» list: a built-in command ([command] is its id) or a skill ([command]
/// `skill`, [id] the skill's resource id).
class CommandOption {
  const CommandOption({
    required this.id,
    required this.command,
    required this.name,
    this.alias,
    this.sub,
    this.hint,
    this.argument = false,
  });

  final String id;
  final String command;

  /// The name the list shows and the owner types after «/».
  final String name;
  final String? alias;
  final String? sub;

  /// What to write after the command (task title, search, what a skill applies to).
  final String? hint;

  /// Whether text follows the command.
  final bool argument;

  bool get skill => command == 'skill';

  @override
  String toString() => 'CommandOption($command, $name)';
}

const _marks = '\u200e\u200f';
final RegExp _commandQuery = RegExp('^[$_marks]*/([^\\s/]*)\$');

/// The query after a «/» that starts the message (bidi marks allowed), else null.
String? commandQuery(String beforeCaret) =>
    _commandQuery.firstMatch(beforeCaret)?.group(1);

/// The built-in commands a chat offers, in order. A task and a call are one agent's.
List<String> availableCommands({
  required bool group,
  required bool chart,
  required bool call,
}) => [
  if (!group) 'task',
  'search',
  'summary',
  if (chart) 'chart',
  if (!group && call) 'call',
  'clear',
];

/// The rows of a chat: its built-in commands, then the agent's enabled skills not named like a
/// command (a skill named like one would be sent as that command).
List<CommandOption> commandRows(
  L10n l10n, {
  required bool group,
  String? symbol,
  required bool trading,
  required String name,
  required bool callable,
  List<SkillResource> skills = const [],
}) {
  final subs = {
    'task': l10n.t('cmdTaskSub'),
    'search': l10n.t('cmdSearchSub'),
    'summary': l10n.t('cmdSummarySub'),
    'chart': !group && symbol != null && symbol.isNotEmpty
        ? l10n.t('cmdChartSymbolSub', [symbol])
        : l10n.t('cmdChartSub'),
    'call': l10n.t('cmdCallSub', [name]),
    'clear': l10n.t('cmdClearSub'),
  };
  final hints = {
    'task': l10n.t('cmdTaskHint'),
    'search': l10n.t('cmdSearchHint'),
  };
  final taken = {
    for (final id in commandIds) ...[
      foldSearch(l10n.t(_commandNames[id]!)),
      commandAlias[id]!,
    ],
  };
  return [
    for (final id in availableCommands(
      group: group,
      chart: group || (symbol ?? '').isNotEmpty || trading,
      call: callable,
    ))
      CommandOption(
        id: id,
        command: id,
        name: l10n.t(_commandNames[id]!),
        alias: commandAlias[id],
        sub: subs[id],
        hint: hints[id],
        argument: hints.containsKey(id),
      ),
    for (final s in skills)
      if (s.enabled && s.name.isNotEmpty && !taken.contains(foldSearch(s.name)))
        CommandOption(
          id: s.id,
          command: 'skill',
          name: s.name,
          sub: asString(s.manifest?['description']),
          hint: l10n.t('cmdSkillHint'),
          argument: true,
        ),
  ];
}

double? _score(CommandOption option, String query) {
  final name = foldSearch(option.name);
  if (name.startsWith(query)) return 1;
  if (foldSearch(option.alias ?? '')
      .split(' ')
      .any((w) => w.startsWith(query))) {
    return 1.5;
  }
  if (name.split(' ').any((w) => w.startsWith(query))) return 2;
  if (name.contains(query)) return 3;
  return foldSearch(option.sub ?? '').contains(query) ? 4 : null;
}

/// The options [query] matches: commands before skills, then the better match, then the given
/// order. Null when the query has run past a whole name with nothing left to match (the list
/// closes).
List<CommandOption>? rankCommands(List<CommandOption> options, String query) {
  final wanted = foldSearch(query);
  if (wanted.isEmpty) return options;
  final scored =
      [
        for (final (index, option) in options.indexed)
          if (_score(option, wanted) case final score?) (option, index, score),
      ]..sort((a, b) {
        final skill = (a.$1.skill ? 1 : 0) - (b.$1.skill ? 1 : 0);
        if (skill != 0) return skill;
        final by = a.$3.compareTo(b.$3);
        return by != 0 ? by : a.$2.compareTo(b.$2);
      });
  final ranked = [for (final row in scored) row.$1];
  final finished = options.any(
    (o) => [o.name, o.alias ?? ''].any((label) {
      final full = foldSearch(label);
      return full.isNotEmpty &&
          wanted.length > full.length &&
          wanted.startsWith(full);
    }),
  );
  return ranked.isEmpty && finished ? null : ranked;
}

/// How much of [body] spells [label], ending at a space or the end; null when it does not.
int? _typed(String body, String label) {
  final full = foldSearch(label);
  if (full.isEmpty) return null;
  for (var end = 1; end <= body.length; end++) {
    final folded = foldSearch(body.substring(0, end));
    if (folded.length > full.length) return null;
    if (folded == full &&
        (end == body.length || RegExp(r'\s').hasMatch(body[end]))) {
      return end;
    }
  }
  return null;
}

/// A typed command: its option, the text after it, and where the command spans in the text.
typedef TypedCommand = ({
  CommandOption option,
  String argument,
  int start,
  int end,
});

/// The command [text] is, else null. The longest name or alias wins; bidi marks and spaces may
/// come first. A command that takes no text is no command when text follows it, so nothing the
/// owner typed is dropped.
TypedCommand? parseCommand(String text, List<CommandOption> options) {
  final start =
      RegExp('^[$_marks\\s]*').firstMatch(text)?.group(0)?.length ?? 0;
  if (start >= text.length || text[start] != '/') return null;
  final body = text.substring(start + 1);
  final labels = [
    for (final o in options) ...[(o, o.name), (o, o.alias ?? '')],
  ]..sort((a, b) => foldSearch(b.$2).length.compareTo(foldSearch(a.$2).length));
  for (final (option, label) in labels) {
    final length = _typed(body, label);
    if (length == null) continue;
    final argument = body.substring(length).trim();
    if (argument.isNotEmpty && !option.argument) return null;
    return (
      option: option,
      argument: argument,
      start: start,
      end: start + 1 + length,
    );
  }
  return null;
}

/// The `command` a send carries for [option], or null for a command run here (chart, call,
/// clear).
Json? sentCommand(CommandOption option, String argument) =>
    const {'task', 'search', 'summary', 'skill'}.contains(option.command)
    ? {
        'name': option.command,
        'argument': argument,
        if (option.skill) 'skill_id': option.id,
      }
    : null;

/// The rich content a sending (or failed) owner message draws from its body's `command`, so
/// its chip shows before the server's copy arrives (message-parts.ts `pendingVoiceRich`). A
/// skill's name arrives with the server's copy.
Json? pendingCommandRich(Json body) {
  final command = body['command'];
  if (command is! Map) return null;
  final c = asJson(command);
  return {
    'version': 1,
    'parts': [
      {
        'type': 'command',
        'name': c['name'],
        'argument': c['argument'] is String ? c['argument'] : '',
        'skill_id': c['skill_id'],
      },
    ],
  };
}

// ---------------------------------------------------------------- words

/// «تنبيه وكيل واحد» … the @all row's subtitle in a group, over its non-paused members
/// (apps/web/src/conversation/Composer.tsx `alertText`). Arabic takes Web's ICU plural forms by
/// the CLDR rules: few is 3–10 of each hundred, many 11–99, and 0 or 100–102 are other.
String alertsText(String lang, int count) {
  if (lang == 'en') {
    return count == 1
        ? 'Alerts one agent'
        : count == 2
        ? 'Alerts two agents'
        : 'Alerts $count agents';
  }
  if (count == 1) return 'تنبيه وكيل واحد';
  if (count == 2) return 'تنبيه وكيلين';
  final rest = count % 100;
  return rest >= 3 && rest <= 10
      ? 'تنبيه $count وكلاء'
      : rest >= 11
      ? 'تنبيه $count وكيلًا'
      : 'تنبيه $count وكيل';
}
