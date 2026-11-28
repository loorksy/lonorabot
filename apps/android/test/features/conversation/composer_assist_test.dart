// The composer's @mentions and «/» commands as pure rules, with the vectors of Lonora's own
// tests (tests/web/composer-commands.test.ts, composer-mentions.test.ts,
// tests/mobile/mention-session.test.ts, commands.test.ts).
import 'package:flutter/widgets.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/features/conversation/composer_assist.dart';
import 'package:lonora/features/rich/rich_parts.dart';
import 'package:lonora/features/skills/skills_data.dart';
import 'package:lonora/l10n/l10n.dart';

CommandOption builtin(
  String command,
  String name, {
  bool argument = false,
  String sub = '',
}) => CommandOption(
  id: command,
  command: command,
  name: name,
  alias: commandAlias[command],
  sub: sub,
  argument: argument,
);

final options = [
  builtin(
    'task',
    'مهمة',
    argument: true,
    sub: 'حوّل طلبك إلى مهمة يتابعها الوكيل',
  ),
  builtin(
    'search',
    'بحث',
    argument: true,
    sub: 'ابحث في الويب ثم أجب مع المصادر',
  ),
  builtin('summary', 'ملخص', sub: 'لخّص هذه المحادثة'),
  builtin('call', 'اتصال'),
  builtin('clear', 'مسح'),
  const CommandOption(
    id: 's1',
    command: 'skill',
    name: 'موجز الأخبار',
    sub: 'تلخيص الأخبار',
    argument: true,
  ),
  const CommandOption(
    id: 's2',
    command: 'skill',
    name: 'بحث متقدم',
    argument: true,
  ),
];

List<String>? names(List<CommandOption>? rows) =>
    rows?.map((r) => r.name).toList();

MentionRange range(String token, int start, {String? agentId}) => MentionRange(
  agentId: agentId ?? token,
  token: token,
  start: start,
  end: start + token.length,
);

Agent agent(String id, {bool paused = false, String? name}) =>
    Agent.fromJson({'id': id, 'name': name ?? id, 'paused': paused});

/// A [MentionAddress] as a list (records with lists compare by identity).
List<Object?> addr(MentionAddress a) => [a.agentIds, a.all, a.sessionId];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  group('commands (composer-commands.test.ts)', () {
    test('a «/» opens the list only as the first thing in the message', () {
      expect(commandQuery('/'), '');
      expect(commandQuery('\u200f/مل'), 'مل');
      expect(commandQuery('hi /x'), isNull);
      expect(commandQuery('/بحث '), isNull);
      expect(commandQuery('//'), isNull);
      expect(commandQuery(''), isNull);
    });

    test('a chat offers the commands that work in it, in order', () {
      expect(availableCommands(group: false, chart: true, call: true), [
        'task',
        'search',
        'summary',
        'chart',
        'call',
        'clear',
      ]);
      expect(availableCommands(group: true, chart: true, call: true), [
        'search',
        'summary',
        'chart',
        'clear',
      ]);
      expect(availableCommands(group: false, chart: false, call: false), [
        'task',
        'search',
        'summary',
        'clear',
      ]);
    });

    test('the list keeps what the query matches: commands first, the better '
        'match first', () {
      expect(names(rankCommands(options, '')), names(options));
      expect(names(rankCommands(options, 'مل')), ['ملخص']);
      expect(names(rankCommands(options, 'sea')), ['بحث']);
      expect(names(rankCommands(options, 'اتصا')), ['اتصال']);
      expect(names(rankCommands(options, 'مهمه')), ['مهمة']);
      expect(names(rankCommands(options, 'بح')), ['بحث', 'بحث متقدم']);
      expect(names(rankCommands(options, 'الاخبار')), ['موجز الأخبار']);
      expect(names(rankCommands(options, 'المصادر')), ['بحث']);
      expect(rankCommands(options, 'zz'), isEmpty);
      expect(rankCommands(options, 'بحثعن'), isNull);
      expect(rankCommands(options, 'searching'), isNull);
    });

    test('a message is a command by its name or its English name, the longest '
        'first', () {
      final search = parseCommand('/بحث أسعار الذهب', options);
      expect(search?.option.command, 'search');
      expect(search?.argument, 'أسعار الذهب');
      expect([search?.start, search?.end], [0, 4]);
      expect(parseCommand('/search gold', options)?.option.command, 'search');
      expect(parseCommand('/SEARCH gold', options)?.argument, 'gold');
      final marked = parseCommand('\u200f /بَحث الذهب', options);
      expect(
        [marked?.option.command, marked?.start, marked?.end],
        ['search', 2, 7],
      );
      expect(parseCommand('/بحثعن', options), isNull);
      expect(parseCommand('بحث /بحث', options), isNull);
      expect(parseCommand('/foo bar', options), isNull);
      expect(parseCommand('/مهمة', options)?.argument, '');
      expect(parseCommand('/ملخص ', options)?.option.command, 'summary');
      expect(parseCommand('/ملخص لهذا الأسبوع', options), isNull);
      expect(parseCommand('/clear now', options), isNull);
      final skill = parseCommand('/موجز الأخبار اليوم', options);
      expect(
        [skill?.option.id, skill?.argument, skill?.end],
        ['s1', 'اليوم', 13],
      );
      expect(parseCommand('/بحث متقدم x', options)?.option.id, 's2');
    });

    test('a sending bubble draws the chip from its body', () {
      final rich = pendingCommandRich({
        'command': {'name': 'task', 'argument': 'راقب الذهب'},
      });
      final part = validateRichContent(rich)?.whereType<CommandPart>().single;
      expect(part?.name, 'task');
      expect(part?.argument, 'راقب الذهب');
      expect(pendingCommandRich({'content': 'plain'}), isNull);
      final skill = validateRichContent(
        pendingCommandRich({
          'command': {'name': 'skill', 'argument': '', 'skill_id': 's1'},
        }),
      )?.whereType<CommandPart>().single;
      expect(skill?.skillId, 's1');
      expect(skill?.skillName, isNull);
    });
  });

  group('command rows (tests/mobile/commands.test.ts)', () {
    late L10n l10n;
    setUpAll(() async {
      l10n = await L10n.load();
      l10n.setLocale(const Locale('ar'));
    });

    final skills = [
      SkillResource.fromJson({
        'id': 's1',
        'payload': {
          'name': 'تحليل الذهب',
          'manifest': {'description': 'Read gold'},
        },
      }),
      SkillResource.fromJson({
        'id': 's2',
        'payload': {'name': 'off', 'enabled': false},
      }),
      SkillResource.fromJson({
        'id': 's3',
        'payload': {'name': 'مهمة'},
      }),
      SkillResource.fromJson({
        'id': 's4',
        'payload': {'name': 'search'},
      }),
    ];

    List<CommandOption> rows({
      bool group = false,
      String? symbol = 'XAUUSD',
      bool trading = true,
      bool callable = true,
      List<SkillResource>? with_,
    }) => commandRows(
      l10n,
      group: group,
      symbol: symbol,
      trading: trading,
      name: 'وكيل الذهب',
      callable: callable,
      skills: with_ ?? skills,
    );

    test('a direct chat offers the six commands, then its enabled skills not '
        'named like a command', () {
      final all = rows();
      expect(all.map((r) => r.command), [
        'task',
        'search',
        'summary',
        'chart',
        'call',
        'clear',
        'skill',
      ]);
      expect(all[0].name, 'مهمة');
      expect(all[0].hint, 'عنوان المهمة');
      expect(all[3].sub, 'افتح شارت XAUUSD');
      expect(all[4].sub, 'ابدأ مكالمة صوتية مع وكيل الذهب');
      expect(all[6].id, 's1');
      expect(all[6].sub, 'Read gold');
      expect(all[6].hint, 'على ماذا أطبّقها؟ (اختياري)');
    });

    test(
      'a group has no task and no call; no symbol and no trading, no chart',
      () {
        expect(rows(group: true, with_: const []).map((r) => r.command), [
          'search',
          'summary',
          'chart',
          'clear',
        ]);
        expect(rows(group: true, with_: const [])[1].sub, 'لخّص هذه المحادثة');
        expect(
          rows(
            symbol: null,
            trading: false,
            callable: false,
            with_: const [],
          ).map((r) => r.command),
          ['task', 'search', 'summary', 'clear'],
        );
        // A group's chart is the market's.
        expect(rows(group: true, with_: const [])[2].sub, 'افتح شارت السوق');
      },
    );

    test('typed in Arabic or by its English alias; a send carries what was '
        'asked', () {
      final all = rows();
      expect(rankCommands(all, 'مه')?.first.command, 'task');
      expect(rankCommands(all, 'sea')?.first.command, 'search');
      final task = parseCommand('/مهمة راقب 2,425', all)!;
      expect(sentCommand(task.option, task.argument), {
        'name': 'task',
        'argument': 'راقب 2,425',
      });
      final skill = parseCommand('/تحليل الذهب اليوم', all)!;
      expect(sentCommand(skill.option, skill.argument), {
        'name': 'skill',
        'argument': 'اليوم',
        'skill_id': 's1',
      });
      final chart = parseCommand('/شارت', all)!;
      expect(sentCommand(chart.option, ''), isNull);
      expect(parseCommand('/شارت الذهب', all), isNull);
    });

    test('English names in English', () {
      l10n.setLocale(const Locale('en'));
      addTearDown(() => l10n.setLocale(const Locale('ar')));
      final all = rows(with_: const []);
      expect(all.map((r) => r.name), [
        'task',
        'search',
        'summary',
        'chart',
        'call',
        'clear',
      ]);
      expect(parseCommand('/task watch gold', all)?.argument, 'watch gold');
    });
  });

  group('mentions (composer-mentions.test.ts)', () {
    test(
      'the marking cuts each committed token and keeps the rest as text',
      () {
        const text = 'مرحبا @رفيق و @Lonora كيف';
        expect(
          mentionSegments(text, [range('@Lonora', 14), range('@رفيق', 6)]),
          [
            (text: 'مرحبا ', mark: false),
            (text: '@رفيق', mark: true),
            (text: ' و ', mark: false),
            (text: '@Lonora', mark: true),
            (text: ' كيف', mark: false),
          ],
        );
      },
    );

    test('an edited token is no longer marked', () {
      expect(mentionSegments('@Lonoa hi', [range('@Lonora', 0)]), [
        (text: '@Lonoa hi', mark: false),
      ]);
      expect(mentionSegments('', const []), isEmpty);
    });

    test('@all in a group names every member; in a direct chat it stays the '
        "session's", () {
      const all = MentionRange(agentId: null, token: '@الكل', start: 0, end: 5);
      expect(addr(mentionAddress('@الكل hi', [all], everyone: ['a', 'b'])), [
        ['a', 'b'],
        false,
        null,
      ]);
      final named = range('@a', 6, agentId: 'a');
      expect(
        mentionAddress('@الكل @a', [all, named], everyone: ['a', 'b']).agentIds,
        ['a', 'b'],
      );
      const session = MentionRange(
        agentId: null,
        sessionId: 's1',
        token: '@الكل',
        start: 0,
        end: 5,
      );
      expect(addr(mentionAddress('@الكل hi', [session])), [
        <String>[],
        true,
        's1',
      ]);
      expect(
        mentionAddress('@الك hi', [all], everyone: ['a', 'b']).agentIds,
        isEmpty,
      );
    });

    test('@all is found by the start of any of its names', () {
      for (final q in ['', 'ال', 'الك', 'al', 'ALL', 'Every', 'الجم']) {
        expect(matchesEveryone(q), isTrue, reason: q);
      }
      for (final q in ['x', 'ل', 'allx', 'كل']) {
        expect(matchesEveryone(q), isFalse, reason: q);
      }
    });

    test('the query is what follows the «@» before the caret', () {
      expect(mentionQuery('@'), '');
      expect(mentionQuery('hi @At'), 'At');
      expect(mentionQuery('mail@x'), isNull);
      expect(mentionQuery('@At las'), isNull);
      expect(mentionQuery('no mention'), isNull);
    });

    test('candidates hold the query, never a paused agent', () {
      final pool = [
        agent('a', name: 'Atlas'),
        agent('b', name: 'Nova'),
        agent('c', name: 'atlas2', paused: true),
      ];
      expect(mentionCandidates(pool, 'atl').map((a) => a.id), ['a']);
      expect(mentionCandidates(pool, '').map((a) => a.id), ['a', 'b']);
    });
  });

  group('mention sessions (tests/mobile/mention-session.test.ts)', () {
    test('a committed all keeps its original session', () {
      const r = MentionRange(
        agentId: null,
        sessionId: 'original-session',
        token: '@all',
        start: 0,
        end: 4,
      );
      final next = rebaseMentions('@all', '@all inspect evidence', [r]);
      expect(addr(mentionAddress('@all inspect evidence', next)), [
        <String>[],
        true,
        'original-session',
      ]);
    });

    test('editing a committed token removes its identity', () {
      final ranges = rebaseMentions('@all', '@alex', const [
        MentionRange(
          agentId: null,
          sessionId: 'original',
          token: '@all',
          start: 0,
          end: 4,
        ),
      ]);
      expect(mentionAddress('@alex', ranges).all, isFalse);
      expect(mentionAddress('@alex', ranges).sessionId, isNull);
    });

    test('text typed before a token moves it', () {
      final r = range('@a', 3, agentId: 'a');
      final next = rebaseMentions('hi @a', 'oh hi @a', [r]);
      expect(next.single.start, 6);
      expect(mentionAddress('oh hi @a', next).agentIds, ['a']);
    });

    test(
      'a direct chat offers every other agent as a guest, never its own',
      () {
        final pool = [agent('own'), agent('a'), agent('b'), agent('c')];
        expect(
          guestCandidates(pool, direct: true, self: 'own').map((a) => a.id),
          ['a', 'b', 'c'],
        );
        expect(guestCandidates(pool, direct: false).length, 4);
      },
    );

    test('every named agent is addressed: no cap', () {
      final ids = [for (var i = 0; i < 20; i++) 'agent-$i'];
      var text = '';
      final ranges = <MentionRange>[];
      for (final id in ids) {
        final token = '@$id';
        ranges.add(
          MentionRange(
            agentId: id,
            token: token,
            start: text.length,
            end: text.length + token.length,
          ),
        );
        text += '$token ';
      }
      expect(mentionAddress(text, ranges).agentIds, ids);
    });

    test('a range survives its JSON and a malformed one is refused', () {
      const r = MentionRange(
        agentId: null,
        sessionId: 's1',
        token: '@الكل',
        start: 2,
        end: 7,
      );
      expect(MentionRange.fromJson(r.toJson()), r);
      expect(
        MentionRange.fromJson({'token': '@a', 'start': 0, 'end': 5}),
        isNull,
      );
      expect(
        MentionRange.fromJson({
          'agent_id': 3,
          'token': '@a',
          'start': 0,
          'end': 2,
        }),
        isNull,
      );
      expect(MentionRange.fromJson('x'), isNull);
    });
  });

  group('message marking (apps/web Markdown.tsx mentionPattern)', () {
    test('the known names, longest first, and @all; an LRM may lead', () {
      final p = mentionPattern(['Atlas', 'Atlas Pro', 'نوفا']);
      List<String> found(String text) => [
        for (final m in p.allMatches(text)) m[1]!,
      ];
      expect(found('hi @Atlas Pro and @Atlas.'), ['Atlas Pro', 'Atlas']);
      expect(found('مرحبا @نوفا، و\u200e@الكل'), ['نوفا', 'الكل']);
      expect(found('@all'), ['all']);
      // Not a known name, or glued to more letters.
      expect(found('@Atlasx @Zed mail@Atlas'), ['Atlas']);
      expect(found('@atlas'), isEmpty);
    });

    test('a group marks its members; a direct chat every agent', () {
      final agents = {
        'a': agent('a', name: 'Atlas'),
        'b': agent('b', name: 'Nova'),
      };
      final g = Group.fromJson({
        'id': 'g',
        'payload': {
          'name': 'Desk',
          'member_ids': ['b'],
        },
      });
      expect(mentionNamesKey(agents, g), 'Nova');
      expect(mentionNamesKey(agents, null), 'Atlas\nNova');
    });
  });

  test('the @all line counts the agents it alerts', () {
    expect(alertsText('ar', 1), 'تنبيه وكيل واحد');
    expect(alertsText('ar', 2), 'تنبيه وكيلين');
    expect(alertsText('ar', 3), 'تنبيه 3 وكلاء');
    expect(alertsText('ar', 11), 'تنبيه 11 وكيلًا');
    expect(alertsText('ar', 100), 'تنبيه 100 وكيل');
    // CLDR, as Web's ICU plural: 0 and 100–102 are other, the rest by the last two digits.
    expect(alertsText('ar', 0), 'تنبيه 0 وكيل');
    expect(alertsText('ar', 10), 'تنبيه 10 وكلاء');
    expect(alertsText('ar', 99), 'تنبيه 99 وكيلًا');
    expect(alertsText('ar', 102), 'تنبيه 102 وكيل');
    expect(alertsText('ar', 103), 'تنبيه 103 وكلاء');
    expect(alertsText('ar', 111), 'تنبيه 111 وكيلًا');
    expect(alertsText('en', 1), 'Alerts one agent');
    expect(alertsText('en', 2), 'Alerts two agents');
    expect(alertsText('en', 5), 'Alerts 5 agents');
  });
}
