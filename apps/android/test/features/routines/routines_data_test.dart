// The routine schedule model: the editor's repeat options onto Lonora's one schedule, the
// schedule lines, the draft checks, the title rule and where a run is read.
import 'package:flutter/widgets.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/features/agents/profile/agent_data.dart'
    show Watch, parsePriceCondition;
import 'package:lonora/features/routines/routine_board.dart' show routineWhen;
import 'package:lonora/features/routines/routines_data.dart';
import 'package:lonora/features/routines/routines_strings.dart';
import 'package:lonora/l10n/l10n.dart';

Routine routine({
  String? cron,
  int? interval,
  String? runAt,
  String? lastRunAt,
  bool enabled = true,
  String? title,
  String prompt = 'Summarize the gold market.',
}) => Routine.fromJson({
  'id': 'r',
  'agent_id': 'a',
  'prompt': prompt,
  'title': title,
  'cron': cron,
  'interval_seconds': interval,
  'run_at': runAt,
  'last_run_at': lastRunAt,
  'enabled': enabled,
  'timezone': 'Asia/Riyadh',
  'next_run_at': '2026-11-30T04:30:00+00:00',
});

extension on Routine {
  String schedule(L10n l10n) => routineScheduleLine(this, l10n);
}

void main() {
  final now = DateTime(2026, 11, 27, 10);
  late L10n l10n;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    l10n = await L10n.load();
    registerRoutinesStrings(l10n);
  });

  test('a price condition reads its side and level', () {
    expect(parsePriceCondition('below 2330'), (level: '2330', below: true));
    expect(parsePriceCondition('تحت ٢٣٣٠٫٥'), (level: '2330.5', below: true));
    expect(parsePriceCondition('فوق 2350'), (level: '2350', below: false));
    expect(parsePriceCondition('2350,25'), (level: '2350.25', below: false));
    expect(parsePriceCondition('< 1.05'), (level: '1.05', below: true));
    expect(parsePriceCondition('when it breaks out'), isNull);
  });

  test('a conditional schedule is listed until it is stopped or expires', () {
    Watch watch(Map<String, Object?> payload, [Map<String, Object?>? state]) =>
        Watch.fromJson({
          'id': 'w',
          'payload': {'kind': 'price', 'prompt': 'Wake me.', ...payload},
          'state': state ?? {'code': 'watch_active'},
          'version': 1,
        });
    expect(watch({}).listed(now), isTrue);
    expect(watch({'prompt': ''}).listed(now), isFalse);
    expect(watch({}, {'code': 'watch_cancelled'}).listed(now), isFalse);
    expect(watch({}, {'lifecycle': 'expired'}).listed(now), isFalse);
    expect(watch({'expires_at': '2026-11-26T10:00:00Z'}).listed(now), isFalse);
    expect(watch({}, {'code': 'watch_paused'}).on, isFalse);
    expect(watch({}, {'code': 'watch_paused'}).listed(now), isTrue);
  });

  test('the When line names a zone other than the device one', () {
    final r = routine(cron: '30 7 * * 1-5');
    expect(routineWhen(r, l10n, 'Asia/Riyadh'), r.schedule(l10n));
    expect(routineWhen(r, l10n, null), r.schedule(l10n));
    expect(
      routineWhen(r, l10n, 'UTC'),
      '${r.schedule(l10n)} · ${ltr('Asia/Riyadh')}',
    );
    // A one-shot reads in the device's time already; an interval has no clock.
    final once = routine(runAt: '2026-11-30T09:00:00Z');
    expect(routineWhen(once, l10n, 'UTC'), once.schedule(l10n));
    final every = routine(interval: 900);
    expect(routineWhen(every, l10n, 'UTC'), every.schedule(l10n));
  });

  test('cron routines map back to the repeat options', () {
    RepeatKind kind(String cron) =>
        RoutineSchedule.of(routine(cron: cron), now).repeat;
    expect(kind('30 7 * * *'), RepeatKind.daily);
    expect(kind('30 7 * * 1-5'), RepeatKind.weekdays);
    expect(kind('0 10 * * 0,6'), RepeatKind.weekend);
    expect(kind('0 10 * * 6,0'), RepeatKind.weekend);
    expect(kind('0 18 * * 5'), RepeatKind.weekly);
    expect(kind('0 18 * * 7'), RepeatKind.weekly);
    expect(kind('15 9 1 * *'), RepeatKind.monthly);
    expect(kind('*/15 * * * *'), RepeatKind.custom);
    expect(kind('0 9 * * 1,3'), RepeatKind.custom);
    expect(kind('0 9 01 * *'), RepeatKind.custom);
    expect(kind('61 9 * * *'), RepeatKind.custom);
    final weekly = RoutineSchedule.of(routine(cron: '0 18 * * 7'), now);
    expect(weekly.weekday, 0);
    expect((weekly.hour, weekly.minute), (18, 0));
  });

  test('intervals and one-shots map to custom and once', () {
    final every = RoutineSchedule.of(routine(interval: 7200), now);
    expect(every.repeat, RepeatKind.custom);
    expect(every.customCron, isFalse);
    expect(every.intervalMinutes, 120);
    final once = RoutineSchedule.of(
      routine(runAt: '2026-12-01T06:00:00Z'),
      now,
    );
    expect(once.repeat, RepeatKind.once);
    expect(once.onceAt, DateTime.parse('2026-12-01T06:00:00Z').toLocal());
  });

  test('every option sends exactly one Lonora schedule', () {
    final base = RoutineSchedule.initial(now).copyWith(hour: 7, minute: 30);
    Map<String, Object?> input(RepeatKind k) =>
        base.copyWith(repeat: k).toInput();
    expect(input(RepeatKind.daily), {'cron': '30 7 * * *'});
    expect(input(RepeatKind.weekdays), {'cron': '30 7 * * 1-5'});
    expect(input(RepeatKind.weekend), {'cron': '30 7 * * 0,6'});
    expect(base.copyWith(repeat: RepeatKind.weekly, weekday: 3).toInput(), {
      'cron': '30 7 * * 3',
    });
    expect(
      base.copyWith(repeat: RepeatKind.monthly, dayOfMonth: 15).toInput(),
      {'cron': '30 7 15 * *'},
    );
    expect(
      base.copyWith(repeat: RepeatKind.custom, intervalMinutes: 45).toInput(),
      {'interval_seconds': 2700},
    );
    expect(
      base
          .copyWith(
            repeat: RepeatKind.custom,
            customCron: true,
            cron: ' */10   9-17 * * 1-5 ',
          )
          .toInput(),
      {'cron': '*/10 9-17 * * 1-5'},
    );
    final once = base.copyWith(
      repeat: RepeatKind.once,
      date: DateTime(2026, 12, 1),
    );
    final runAt = once.toInput()['run_at']! as String;
    expect(runAt.endsWith('Z'), isTrue, reason: 'tz-aware for the server');
    expect(DateTime.parse(runAt).toLocal(), DateTime(2026, 12, 1, 7, 30));
  });

  test('round trip: what is sent reads back as the same option', () {
    for (final k in RepeatKind.values) {
      if (k == RepeatKind.once) continue;
      final draft = RoutineSchedule.initial(now)
          .copyWith(repeat: k, hour: 21, minute: 5, weekday: 2, dayOfMonth: 28);
      final input = draft.toInput();
      final back = RoutineSchedule.of(
        routine(
          cron: input['cron'] as String?,
          interval: input['interval_seconds'] as int?,
        ),
        now,
      );
      expect(back.repeat, k, reason: '$k → $input');
    }
  });

  test('draft checks', () {
    final base = RoutineSchedule.initial(now);
    expect(base.problem(now), isNull);
    expect(
      base
          .copyWith(repeat: RepeatKind.once, date: DateTime(2026, 11, 27))
          .copyWith(hour: 9)
          .problem(now),
      'rt_timePassed',
    );
    expect(
      base
          .copyWith(repeat: RepeatKind.once, date: DateTime(2026, 11, 28))
          .problem(now),
      isNull,
    );
    expect(
      base.copyWith(repeat: RepeatKind.monthly, dayOfMonth: 32).problem(now),
      'rt_invalidDay',
    );
    expect(
      base.copyWith(repeat: RepeatKind.custom, intervalMinutes: 0).problem(now),
      'rt_invalidInterval',
    );
    expect(
      base
          .copyWith(repeat: RepeatKind.custom, customCron: true, cron: '0 9 *')
          .problem(now),
      'rt_invalidCron',
    );
  });

  test('schedule lines in both languages', () {
    l10n.setLocale(const Locale('en'));
    expect(
      routineScheduleLine(routine(cron: '30 7 * * 1-5'), l10n),
      'Weekdays at 07:30',
    );
    expect(
      routineScheduleLine(routine(cron: '0 18 * * 5'), l10n),
      'Every Friday at 18:00',
    );
    expect(
      routineScheduleLine(routine(cron: '0 9 15 * *'), l10n),
      'Monthly on day 15 at 09:00',
    );
    expect(routineScheduleLine(routine(interval: 7200), l10n), 'Every 2 h');
    expect(routineScheduleLine(routine(interval: 1800), l10n), 'Every 30 min');
    l10n.setLocale(const Locale('ar'));
    expect(
      routineScheduleLine(routine(cron: '0 9 * * *'), l10n),
      'كل يوم الساعة 09:00',
    );
    expect(
      routineScheduleLine(routine(cron: '0 18 * * 5'), l10n),
      'أسبوعيًا يوم الجمعة الساعة 18:00',
    );
  });

  test('a fired one-shot is done', () {
    expect(
      routine(
        runAt: '2026-11-20T06:00:00Z',
        lastRunAt: '2026-11-20T06:00:03Z',
        enabled: false,
      ).fired,
      isTrue,
    );
    expect(routine(runAt: '2026-12-20T06:00:00Z').fired, isFalse);
  });

  test('the title follows the task text unless it is its own', () {
    expect(routineTitleInput(null, 'Brief'), {'title': 'Brief'});
    final copied = routine(title: 'Old text', prompt: 'Old text');
    expect(routineTitleInput(copied, 'New text'), {'title': 'New text'});
    expect(routineTitleInput(copied, 'Old text'), isEmpty);
    final own = routine(title: 'Morning brief', prompt: 'Old text');
    expect(routineTitleInput(own, 'New text'), isEmpty);
    final long = 'x' * 200;
    expect((routineTitleInput(null, long)['title']! as String).length, 160);
  });

  test('a run opens the conversation it reports to', () {
    Run run(Map<String, Object?> extra) => Run.fromJson({
      'id': 'run',
      'thread_id': 'work',
      'agent_id': 'a',
      'status': 'completed',
      ...extra,
    });
    expect(reportThread(run({})), 'work');
    expect(
      reportThread(
        run({
          'model_metadata': {'origin_thread_id': 'chat'},
        }),
      ),
      'chat',
    );
    expect(
      reportThread(
        run({
          'status': 'waiting_input',
          'model_metadata': {'origin_thread_id': 'chat'},
          'input_request': {'status': 'pending', 'thread_id': 'question'},
        }),
      ),
      'question',
    );
  });
}
