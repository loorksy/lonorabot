// Lonora routines (`/routines`, lonora-api-contract §10) and the editor's schedule model.
//
// A routine has exactly one schedule: `run_at` (once), `cron` or `interval_seconds`. The editor's
// repeat options (Does not repeat · Daily · Weekly · Monthly · Weekdays · Weekend · Custom) map
// onto it:
//
// | Repeat | Lonora schedule |
// |---|---|
// | Does not repeat | `run_at` (a tz-aware instant) |
// | Daily | `cron` `m h * * *` |
// | Weekly | `cron` `m h * * d` (d 0–6, Sunday 0) |
// | Monthly | `cron` `m h D * *` |
// | Weekdays | `cron` `m h * * 1-5` |
// | Weekend | `cron` `m h * * 0,6` |
// | Custom | `interval_seconds` (minutes × 60) or any other `cron` |
//
// Cron times are read in the routine's own `timezone` (server `lonora_core.cron`).
import 'package:flutter/foundation.dart';

import '../../app/services.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../l10n/l10n.dart';

@immutable
class Routine {
  const Routine({
    required this.id,
    required this.agentId,
    required this.prompt,
    this.title,
    this.threadId,
    this.intervalSeconds,
    this.cron,
    this.runAt,
    this.timezone = 'UTC',
    this.enabled = true,
    this.nextRunAt,
    this.lastRunAt,
    this.raw = const {},
  });

  factory Routine.fromJson(Json j) => Routine(
    id: asStr(j['id']),
    agentId: asStr(j['agent_id']),
    prompt: asStr(j['prompt']),
    title: asString(j['title']),
    threadId: asString(j['thread_id']),
    intervalSeconds: asInt(j['interval_seconds']),
    cron: asString(j['cron']),
    runAt: asDate(j['run_at']),
    timezone: asStr(j['timezone'], 'UTC'),
    enabled: asBool(j['enabled'], true),
    nextRunAt: asDate(j['next_run_at']),
    lastRunAt: asDate(j['last_run_at']),
    raw: j,
  );

  final String id;
  final String agentId;
  final String prompt;
  final String? title;
  final String? threadId;
  final int? intervalSeconds;
  final String? cron;
  final DateTime? runAt;
  final String timezone;
  final bool enabled;
  final DateTime? nextRunAt;
  final DateTime? lastRunAt;
  final Json raw;

  /// A one-shot that already ran («نُفّذت»): it has no switch, only «جدولة من جديد».
  bool get fired => runAt != null && lastRunAt != null && !enabled;

  /// The routine's title, or the start of its task text (apps/web `routineTitle`).
  String get displayTitle {
    final own = title?.trim() ?? '';
    if (own.isNotEmpty) return own;
    final text = prompt.trim();
    final runes = text.runes.toList();
    return runes.length <= 80 ? text : String.fromCharCodes(runes.take(80));
  }

  Routine copyWith({bool? enabled}) =>
      Routine.fromJson({...raw, 'enabled': ?enabled});
}

/// The cut counts code points, so an emoji is never split (apps/mobile/lib/routine-title.ts).
String _cut(String text) => String.fromCharCodes(text.runes.take(160));

/// The title a save sends (apps/mobile/lib/routine-title.ts `titleInput`): a new routine is
/// named after its task text, and so is one whose text the owner edits while it has no title
/// of its own. A title set apart from the text is kept.
Json routineTitleInput(Routine? routine, String text) {
  if (routine == null) return {'title': _cut(text)};
  final stored = routine.prompt.trim();
  if (text.trim() == stored) return {};
  final title = routine.title;
  final own = title != null && title.isNotEmpty && title.trim() != _cut(stored);
  return own ? {} : {'title': _cut(text)};
}

enum RepeatKind { once, daily, weekly, monthly, weekdays, weekend, custom }

/// The label key of each repeat option, in the editor's order.
const repeatLabels = {
  RepeatKind.once: 'rt_noRepeat',
  RepeatKind.daily: 'rt_daily',
  RepeatKind.weekly: 'rt_weekly',
  RepeatKind.monthly: 'rt_monthly',
  RepeatKind.weekdays: 'rt_weekdays',
  RepeatKind.weekend: 'rt_weekend',
  RepeatKind.custom: 'rt_custom',
};

/// The editor's draft of a schedule.
@immutable
class RoutineSchedule {
  const RoutineSchedule({
    required this.repeat,
    this.hour = 9,
    this.minute = 0,
    this.date,
    this.weekday = 1,
    this.dayOfMonth = 1,
    this.customCron = false,
    this.intervalMinutes = 60,
    this.cron = '0 9 * * 1-5',
  });

  final RepeatKind repeat;
  final int hour;
  final int minute;

  /// The local day of a one-shot.
  final DateTime? date;

  /// Cron day of week, 0 (Sunday) to 6.
  final int weekday;
  final int dayOfMonth;

  /// Custom: a cron expression (true) or an interval (false).
  final bool customCron;
  final int intervalMinutes;
  final String cron;

  static final _cronTimes = RegExp(r'^(\d{1,2}) (\d{1,2}) (\S+) \* (\S+)$');

  /// A new routine: every day at 09:00 (the web form's default time).
  factory RoutineSchedule.initial(DateTime now) => RoutineSchedule(
    repeat: RepeatKind.daily,
    date: DateTime(now.year, now.month, now.day),
    weekday: now.weekday % 7,
    dayOfMonth: now.day,
  );

  /// The schedule a stored routine has.
  factory RoutineSchedule.of(Routine routine, DateTime now) {
    final base = RoutineSchedule.initial(now);
    final at = routine.runAt;
    if (at != null) {
      return base.copyWith(
        repeat: RepeatKind.once,
        hour: at.hour,
        minute: at.minute,
        date: DateTime(at.year, at.month, at.day),
      );
    }
    final cron = routine.cron?.trim();
    if (cron != null && cron.isNotEmpty) {
      final m = _cronTimes.firstMatch(cron);
      final minute = int.tryParse(m?[1] ?? '');
      final hour = int.tryParse(m?[2] ?? '');
      if (m != null &&
          minute != null &&
          hour != null &&
          minute < 60 &&
          hour < 24) {
        final dom = m[3]!;
        final dow = m[4]!;
        final timed = base.copyWith(hour: hour, minute: minute);
        if (dom == '*') {
          if (dow == '*') return timed.copyWith(repeat: RepeatKind.daily);
          if (dow == '1-5') return timed.copyWith(repeat: RepeatKind.weekdays);
          if (dow == '0,6' || dow == '6,0') {
            return timed.copyWith(repeat: RepeatKind.weekend);
          }
          final day = int.tryParse(dow);
          if (day != null && day >= 0 && day <= 7 && dow.length == 1) {
            return timed.copyWith(repeat: RepeatKind.weekly, weekday: day % 7);
          }
        } else if (dow == '*') {
          final day = int.tryParse(dom);
          if (day != null && day >= 1 && day <= 31 && '$day' == dom) {
            return timed.copyWith(repeat: RepeatKind.monthly, dayOfMonth: day);
          }
        }
      }
      return base.copyWith(
        repeat: RepeatKind.custom,
        customCron: true,
        cron: cron,
      );
    }
    final seconds = routine.intervalSeconds ?? 3600;
    return base.copyWith(
      repeat: RepeatKind.custom,
      customCron: false,
      intervalMinutes: (seconds / 60).round().clamp(1, 525600),
    );
  }

  RoutineSchedule copyWith({
    RepeatKind? repeat,
    int? hour,
    int? minute,
    DateTime? date,
    int? weekday,
    int? dayOfMonth,
    bool? customCron,
    int? intervalMinutes,
    String? cron,
  }) => RoutineSchedule(
    repeat: repeat ?? this.repeat,
    hour: hour ?? this.hour,
    minute: minute ?? this.minute,
    date: date ?? this.date,
    weekday: weekday ?? this.weekday,
    dayOfMonth: dayOfMonth ?? this.dayOfMonth,
    customCron: customCron ?? this.customCron,
    intervalMinutes: intervalMinutes ?? this.intervalMinutes,
    cron: cron ?? this.cron,
  );

  /// The one-shot's local instant.
  DateTime? get onceAt {
    final d = date;
    return d == null ? null : DateTime(d.year, d.month, d.day, hour, minute);
  }

  /// The schedule fields a save sends: exactly one of run_at, cron, interval_seconds (the
  /// server replaces the other two).
  Json toInput() => switch (repeat) {
    RepeatKind.once => {'run_at': onceAt?.toUtc().toIso8601String()},
    RepeatKind.daily => {'cron': '$minute $hour * * *'},
    RepeatKind.weekdays => {'cron': '$minute $hour * * 1-5'},
    RepeatKind.weekend => {'cron': '$minute $hour * * 0,6'},
    RepeatKind.weekly => {'cron': '$minute $hour * * $weekday'},
    RepeatKind.monthly => {'cron': '$minute $hour $dayOfMonth * *'},
    RepeatKind.custom =>
      customCron
          ? {'cron': cron.trim().replaceAll(RegExp(r'\s+'), ' ')}
          : {'interval_seconds': intervalMinutes * 60},
  };

  /// The label key of what is wrong with the draft, or null when it can be saved. A one-shot
  /// must lie ahead of [now] (the server's own check is `run_at_past`).
  String? problem(DateTime now) {
    switch (repeat) {
      case RepeatKind.once:
        final at = onceAt;
        if (at == null || !at.isAfter(now)) return 'rt_timePassed';
      case RepeatKind.monthly:
        if (dayOfMonth < 1 || dayOfMonth > 31) return 'rt_invalidDay';
      case RepeatKind.custom:
        if (customCron) {
          if (cron.trim().split(RegExp(r'\s+')).length != 5) {
            return 'rt_invalidCron';
          }
        } else if (intervalMinutes < 1 || intervalMinutes > 525600) {
          return 'rt_invalidInterval';
        }
      default:
        break;
    }
    return null;
  }

  /// One line for the schedule, e.g. «كل يوم الساعة 09:00» / "Every Monday at 09:00".
  String describe(L10n l10n) {
    final time = clock(hour, minute);
    return switch (repeat) {
      RepeatKind.once => l10n.t('rt_onceAt', const [], {
        'date': date == null ? '' : formatDate('d MMM y', l10n.lang, date!),
        'time': time,
      }),
      RepeatKind.daily => l10n.t('rt_dailyAt', const [], {'time': time}),
      RepeatKind.weekdays => l10n.t('rt_weekdaysAt', const [], {'time': time}),
      RepeatKind.weekend => l10n.t('rt_weekendAt', const [], {'time': time}),
      RepeatKind.weekly => l10n.t('rt_weeklyAt', const [], {
        'day': weekdayName(weekday, l10n.lang),
        'time': time,
      }),
      RepeatKind.monthly => l10n.t('rt_monthlyAt', const [], {
        'day': '$dayOfMonth',
        'time': time,
      }),
      RepeatKind.custom =>
        customCron
            ? ltr(cron.trim())
            : intervalMinutes % 60 == 0
            ? l10n.t('rt_everyHours', const [], {'n': intervalMinutes ~/ 60})
            : l10n.t('rt_everyMinutesN', const [], {'n': intervalMinutes}),
    };
  }
}

/// HH:mm with Latin digits, as Lonora prints clock times.
String clock(int hour, int minute) =>
    '${hour.toString().padLeft(2, '0')}:${minute.toString().padLeft(2, '0')}';

/// The name of cron day [day] (0 Sunday … 6 Saturday) in [lang].
String weekdayName(int day, String lang) =>
    formatDate('EEEE', lang, DateTime(2024, 1, 7 + day % 7));

/// What one routine's schedule says («كل يوم الساعة 09:00»).
String routineScheduleLine(Routine routine, L10n l10n, {DateTime? now}) =>
    RoutineSchedule.of(routine, now ?? DateTime.now()).describe(l10n);

/// Where the owner reads a run (apps/mobile/lib/run-thread.ts `reportThread`): a run waiting
/// on its question opens the thread holding it; otherwise the origin conversation it reports
/// to, else its own thread.
String reportThread(Run run) {
  final question = asJson(run.raw['input_request']);
  if (run.status == 'waiting_input' && question['status'] == 'pending') {
    return asString(question['thread_id']) ?? run.threadId;
  }
  final origin = asString(run.modelMetadata['origin_thread_id']);
  return origin != null && origin.isNotEmpty ? origin : run.threadId;
}

String _enc(String value) => Uri.encodeComponent(value);

/// `GET /routines[?agent_id=]`, ordered by next run.
Future<List<Routine>> fetchRoutines({String? agentId}) async =>
    asJsonList(await api.get('/routines', query: {'agent_id': ?agentId}))
        .map(Routine.fromJson)
        .toList();

/// `POST /routines/{agent_id}` (`RoutineCreate`).
Future<Routine> createRoutine(String agentId, Json input) async =>
    Routine.fromJson(
      asJson(await api.post('/routines/${_enc(agentId)}', input)),
    );

/// `PUT /routines/{id}`: a partial edit; fields left out keep their stored value.
Future<Routine> updateRoutine(String id, Json input) async =>
    Routine.fromJson(asJson(await api.put('/routines/${_enc(id)}', input)));

Future<void> deleteRoutine(String id) => api.delete('/routines/${_enc(id)}');

/// `GET /routines/{id}/history`: its runs, newest first.
Future<List<Run>> fetchRoutineHistory(String id) async =>
    asJsonList(await api.get('/routines/${_enc(id)}/history'))
        .map(Run.fromJson)
        .toList();
