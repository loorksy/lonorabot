// The routine editor: «When» (repeat, date, time), «Agent will» (the task text),
// «Advanced settings»; repeat options Does not repeat · Daily · Weekly · Monthly · Weekdays ·
// Weekend · Custom, mapped onto Lonora's one schedule (routines_data.dart). Composed from the kit.
// Lonora's routine has no approvals or end date (`RoutineCreate`, lonora-api-contract §10), so
// Advanced holds what it has: the time zone and the on/off switch. Saves are
// `POST /routines/{agent}` and the partial `PUT /routines/{id}` (apps/mobile/app/routine.tsx,
// apps/web SchedulesPages.tsx). A new schedule of a trading agent with its account and symbol may
// instead be «عند تحقق شرط»: a price watch that wakes the agent with the task (`POST /watches`,
// apps/web SchedulesPages.tsx `NewSchedulePage`); a watch carries no trading authority.
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../agents/profile/agent_data.dart'
    show canWatchPrice, createPriceWatch, parsePriceCondition;
import '../agents/profile/agent_page.dart';
import '../settings/settings_common.dart';
import '../settings/settings_core_data.dart' show deviceTimeZone;
import 'routines_data.dart';

/// Opens the editor for [routine] (null: a new one, for [agentId] or a chosen agent). Completes
/// with true once a routine (or a conditional watch) is saved.
Future<bool?> showRoutineEditor(
  BuildContext context, {
  Routine? routine,
  String? agentId,
  required List<Agent> agents,
  bool reschedule = false,
}) => showLnSheet<bool>(
  context,
  maxHeightFraction: 0.94,
  title: context.t(
    routine == null
        ? 'createRoutine'
        : reschedule
        ? 'rt_scheduleAgain'
        : 'rt_editSchedule',
  ),
  builder: (_) => RoutineEditor(
    routine: routine,
    agentId: agentId,
    agents: agents,
    reschedule: reschedule,
  ),
);

class RoutineEditor extends StatefulWidget {
  const RoutineEditor({
    super.key,
    this.routine,
    this.agentId,
    required this.agents,
    this.reschedule = false,
    this.now,
  });

  final Routine? routine;
  final String? agentId;
  final List<Agent> agents;

  /// A fired one-shot gets a new date and time and is switched back on.
  final bool reschedule;

  /// The clock (tests pin it).
  final DateTime? now;

  @override
  State<RoutineEditor> createState() => _RoutineEditorState();
}

class _RoutineEditorState extends State<RoutineEditor> {
  late final DateTime _now = widget.now ?? DateTime.now();
  late RoutineSchedule _schedule;
  late final RoutineSchedule? _stored;
  late String? _agent;
  late bool _enabled = widget.reschedule || (widget.routine?.enabled ?? true);
  late final _prompt = TextEditingController(
    text: widget.routine?.prompt ?? '',
  );
  late final _zone = TextEditingController(
    text: widget.routine?.timezone ?? 'UTC',
  );
  final _minutes = TextEditingController();
  final _cron = TextEditingController();
  final _day = TextEditingController();
  final _level = TextEditingController();

  /// «عند تحقق شرط» chosen instead of a time (new schedules of a watch-capable agent only).
  bool _onCondition = false;
  bool _busy = false;
  bool _tried = false;

  @override
  void initState() {
    super.initState();
    final routine = widget.routine;
    _stored = routine == null ? null : RoutineSchedule.of(routine, _now);
    var schedule = _stored ?? RoutineSchedule.initial(_now);
    if (widget.reschedule) {
      final tomorrow = _now.add(const Duration(days: 1));
      schedule = schedule.copyWith(
        repeat: RepeatKind.once,
        date: DateTime(tomorrow.year, tomorrow.month, tomorrow.day),
      );
    }
    _schedule = schedule;
    _minutes.text = '${schedule.intervalMinutes}';
    _cron.text = schedule.cron;
    _day.text = '${schedule.dayOfMonth}';
    _agent =
        routine?.agentId ??
        widget.agentId ??
        (widget.agents.isEmpty ? null : widget.agents.first.id);
    for (final c in [_prompt, _zone, _minutes, _cron, _day, _level]) {
      c.addListener(() => setState(() {}));
    }
    if (routine == null) {
      deviceTimeZone().then((zone) {
        if (zone != null && mounted && _zone.text == 'UTC') _zone.text = zone;
      });
    }
  }

  @override
  void dispose() {
    for (final c in [_prompt, _zone, _minutes, _cron, _day, _level]) {
      c.dispose();
    }
    super.dispose();
  }

  RoutineSchedule get _draft => _schedule.copyWith(
    intervalMinutes: int.tryParse(_minutes.text.trim()) ?? 0,
    cron: _cron.text,
    dayOfMonth: int.tryParse(_day.text.trim()) ?? 0,
  );

  /// Whether the schedule differs from the stored one (an unchanged one is not sent, so a fired
  /// one-shot keeps its time).
  bool get _scheduleChanged {
    final stored = _stored;
    if (stored == null || widget.reschedule) return true;
    return !_sameInput(stored.toInput(), _draft.toInput());
  }

  static bool _sameInput(Map<String, Object?> a, Map<String, Object?> b) =>
      a.length == b.length && a.entries.every((e) => b[e.key] == e.value);

  String? get _problem {
    if (_prompt.text.trim().isEmpty) return null;
    return _scheduleChanged ? _draft.problem(_now) : null;
  }

  Future<void> _pickRepeat() async {
    final l10n = context.l10n;
    final chosen = await showLnSheet<RepeatKind>(
      context,
      title: l10n.t('rt_repeat'),
      builder: (sheet) => SingleChildScrollView(
        child: LnSection(
          padding: EdgeInsets.zero,
          children: [
            for (final MapEntry(:key, :value) in repeatLabels.entries)
              ChoiceTile(
                title: l10n.t(value),
                selected: _schedule.repeat == key,
                onSelect: () => Navigator.of(sheet).pop(key),
              ),
          ],
        ),
      ),
    );
    if (chosen != null) {
      setState(() => _schedule = _schedule.copyWith(repeat: chosen));
    }
  }

  Future<void> _pickTime() async {
    final l10n = context.l10n;
    final controller = FTimePickerController(
      initial: FTime(_schedule.hour, _schedule.minute),
    );
    final time = await showLnSheet<FTime>(
      context,
      title: l10n.t('rt_time'),
      builder: (sheet) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: 200,
            // Clock digits read left to right in both languages.
            child: Directionality(
              textDirection: TextDirection.ltr,
              child: FTimePicker(
                controller: controller,
                hour24: true,
                onChange: (_) => HapticFeedback.selectionClick(),
              ),
            ),
          ),
          const SizedBox(height: LnSpace.md),
          BlockButton(
            label: l10n.t('avatarDone'),
            onPressed: () => Navigator.of(sheet).pop(controller.value),
          ),
        ],
      ),
    );
    controller.dispose();
    if (time != null) {
      setState(
        () => _schedule = _schedule.copyWith(
          hour: time.hour,
          minute: time.minute,
        ),
      );
    }
  }

  Future<void> _pickDate() async {
    final l10n = context.l10n;
    final today = DateTime(_now.year, _now.month, _now.day);
    final controller = FCalendarController.date(
      initialSelection: _schedule.date,
      toggleable: false,
    );
    final date = await showLnSheet<DateTime>(
      context,
      title: l10n.t('rt_date'),
      builder: (sheet) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          FCalendar(
            controller: controller,
            start: today,
            today: today,
            initialMonth: _schedule.date ?? today,
            onPress: (d) => Navigator.of(sheet).pop(d),
          ),
        ],
      ),
    );
    controller.dispose();
    if (date != null) {
      setState(
        () => _schedule = _schedule.copyWith(
          date: DateTime(date.year, date.month, date.day),
        ),
      );
    }
  }

  Future<void> _pickWeekday() async {
    final l10n = context.l10n;
    final day = await showLnSheet<int>(
      context,
      title: l10n.t('rt_weekday'),
      builder: (sheet) => SingleChildScrollView(
        child: LnSection(
          padding: EdgeInsets.zero,
          children: [
            // Saturday first in Arabic, as the region's week starts; Monday first in English.
            for (final d
                in l10n.lang == 'ar'
                    ? const [6, 0, 1, 2, 3, 4, 5]
                    : const [1, 2, 3, 4, 5, 6, 0])
              ChoiceTile(
                title: weekdayName(d, l10n.lang),
                selected: _schedule.weekday == d,
                onSelect: () => Navigator.of(sheet).pop(d),
              ),
          ],
        ),
      ),
    );
    if (day != null) {
      setState(() => _schedule = _schedule.copyWith(weekday: day));
    }
  }

  Future<void> _pickAgent() async {
    final l10n = context.l10n;
    final id = await showLnSheet<String>(
      context,
      title: l10n.t('rt_chooseAgent'),
      builder: (sheet) => SingleChildScrollView(
        child: LnSection(
          padding: EdgeInsets.zero,
          children: [
            for (final a in widget.agents)
              ChoiceTile(
                title: isolate(a.name),
                selected: _agent == a.id,
                onSelect: () => Navigator.of(sheet).pop(a.id),
              ),
          ],
        ),
      ),
    );
    if (id != null) setState(() => _agent = id);
  }

  Agent? get _agentRow =>
      widget.agents.where((a) => a.id == _agent).firstOrNull;

  /// Whether this new schedule may be a price condition of the chosen agent.
  bool get _canCondition {
    final agent = _agentRow;
    return widget.routine == null && agent != null && canWatchPrice(agent);
  }

  bool get _condition => _onCondition && _canCondition;

  /// The typed condition with a level above zero, or null.
  ({String level, bool below})? get _parsedCondition {
    final parsed = parsePriceCondition(_level.text);
    return parsed != null && (double.tryParse(parsed.level) ?? 0) > 0
        ? parsed
        : null;
  }

  Future<void> _saveCondition() async {
    final agent = _agentRow;
    final condition = _parsedCondition;
    final text = _prompt.text.trim();
    if (_busy || agent == null || condition == null || text.isEmpty) return;
    setState(() => _busy = true);
    try {
      await createPriceWatch(
        agent,
        level: condition.level,
        below: condition.below,
        prompt: text,
      );
      if (!mounted) return;
      LnToast.show(context, context.t('rt_saved'), kind: LnToastKind.positive);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  Future<void> _save() async {
    setState(() => _tried = true);
    if (_condition) return _saveCondition();
    final agent = _agent;
    final text = _prompt.text.trim();
    if (_busy || agent == null || text.isEmpty || _problem != null) return;
    final routine = widget.routine;
    final input = <String, Object?>{
      ...routineTitleInput(routine, text),
      if (routine == null || text != routine.prompt.trim()) 'prompt': text,
      if (_scheduleChanged) ..._draft.toInput(),
      if (routine == null || _zone.text.trim() != routine.timezone)
        'timezone': _zone.text.trim().isEmpty ? 'UTC' : _zone.text.trim(),
      if (!(routine?.fired ?? false) || widget.reschedule)
        if (routine == null || _enabled != routine.enabled || widget.reschedule)
          'enabled': _enabled,
    };
    setState(() => _busy = true);
    try {
      if (routine == null) {
        await createRoutine(agent, input);
      } else {
        await updateRoutine(routine.id, input);
      }
      if (!mounted) return;
      LnToast.show(context, context.t('rt_saved'), kind: LnToastKind.positive);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final c = context.ln.colors;
    final schedule = _schedule;
    final fired = widget.routine?.fired ?? false;
    final agent = _agentRow;
    final condition = _condition;
    final problem = !condition && (_tried || _prompt.text.isNotEmpty)
        ? _problem
        : null;
    Widget value(String text) =>
        Text(text, style: context.ln.text.body.copyWith(color: c.fgMuted));
    const tight = EdgeInsets.only(top: LnSpace.sm);

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.reschedule)
            Padding(
              padding: const EdgeInsets.only(bottom: LnSpace.sm),
              child: Text(
                l10n.t('rt_rescheduleHint'),
                style: context.ln.text.caption.copyWith(color: c.fgMuted),
              ),
            ),
          if (widget.routine == null && widget.agentId == null)
            LnSection(
              padding: const EdgeInsets.only(bottom: LnSpace.md),
              children: [
                WrapTile(
                  icon: FIcons.bot,
                  title: l10n.t('rt_agent'),
                  subtitle: agent == null ? null : isolate(agent.name),
                  trailing: const TileChevron(),
                  enabled: !_busy && widget.agents.isNotEmpty,
                  onTap: _pickAgent,
                ),
              ],
            ),
          if (_canCondition) ...[
            LnSegmented<bool>(
              segments: [
                LnSegment(value: false, label: l10n.t('rt_atTime')),
                LnSegment(value: true, label: l10n.t('rt_conditionTab')),
              ],
              selected: _onCondition,
              onChanged: _busy
                  ? (_) {}
                  : (v) => setState(() => _onCondition = v),
            ),
            const SizedBox(height: LnSpace.md),
          ],
          if (condition) ...[
            LnSection(
              title: l10n.t('rt_when'),
              padding: EdgeInsets.zero,
              children: [
                WrapTile(
                  icon: FIcons.chartCandlestick,
                  title: l10n.t('symbol'),
                  trailing: value(ltr(agent?.tradingSymbol ?? '')),
                ),
              ],
            ),
            ContentField(
              controller: _level,
              label: l10n.t('rt_condition'),
              hint: l10n.t('rt_conditionHint'),
              maxLength: 60,
              enabled: !_busy,
              padding: tight,
              error: _tried && _parsedCondition == null
                  ? l10n.t('rt_conditionInvalid')
                  : null,
            ),
          ] else ...[
            LnSection(
              title: l10n.t('rt_when'),
              padding: EdgeInsets.zero,
              children: [
                if (!widget.reschedule)
                  WrapTile(
                    icon: FIcons.repeat,
                    title: l10n.t('rt_repeat'),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        value(l10n.t(repeatLabels[schedule.repeat]!)),
                        const TileChevron(),
                      ],
                    ),
                    enabled: !_busy,
                    onTap: _pickRepeat,
                  ),
                if (schedule.repeat == RepeatKind.once)
                  WrapTile(
                    icon: FIcons.calendar,
                    title: l10n.t('rt_date'),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        value(
                          schedule.date == null
                              ? '—'
                              : formatDate(
                                  'd MMM y',
                                  l10n.lang,
                                  schedule.date!,
                                ),
                        ),
                        const TileChevron(),
                      ],
                    ),
                    enabled: !_busy,
                    onTap: _pickDate,
                  ),
                if (schedule.repeat == RepeatKind.weekly)
                  WrapTile(
                    icon: FIcons.calendarDays,
                    title: l10n.t('rt_weekday'),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        value(weekdayName(schedule.weekday, l10n.lang)),
                        const TileChevron(),
                      ],
                    ),
                    enabled: !_busy,
                    onTap: _pickWeekday,
                  ),
                if (schedule.repeat != RepeatKind.custom)
                  WrapTile(
                    icon: FIcons.clock,
                    title: l10n.t('rt_time'),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        value(clock(schedule.hour, schedule.minute)),
                        const TileChevron(),
                      ],
                    ),
                    enabled: !_busy,
                    onTap: _pickTime,
                  ),
              ],
            ),
            if (schedule.repeat == RepeatKind.monthly)
              ContentField(
                controller: _day,
                label: l10n.t('rt_dayOfMonth'),
                ltrOnly: true,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                maxLength: 2,
                enabled: !_busy,
                padding: tight,
              ),
            if (schedule.repeat == RepeatKind.custom) ...[
              const SizedBox(height: LnSpace.sm),
              LnSegmented<bool>(
                segments: [
                  LnSegment(value: false, label: l10n.t('interval')),
                  LnSegment(value: true, label: l10n.t('cron')),
                ],
                selected: schedule.customCron,
                onChanged: (v) => setState(
                  () => _schedule = _schedule.copyWith(customCron: v),
                ),
              ),
              if (schedule.customCron)
                ContentField(
                  controller: _cron,
                  label: l10n.t('cron'),
                  helper: l10n.t('rt_cronHint'),
                  ltrOnly: true,
                  maxLength: 120,
                  enabled: !_busy,
                  padding: tight,
                )
              else
                ContentField(
                  controller: _minutes,
                  label: l10n.t('rt_everyMinutes'),
                  ltrOnly: true,
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  maxLength: 6,
                  enabled: !_busy,
                  padding: tight,
                ),
            ],
            if (problem != null)
              Padding(
                padding: tight,
                child: Text(
                  l10n.t(problem),
                  style: context.ln.text.footnote.copyWith(color: c.error),
                ),
              ),
          ],
          const SizedBox(height: LnSpace.md),
          ContentField(
            controller: _prompt,
            label: l10n.t('rt_agentWill'),
            hint: l10n.t('rt_promptHint'),
            minLines: 3,
            maxLines: 8,
            maxLength: 8000,
            enabled: !_busy,
            padding: EdgeInsets.zero,
            error: _tried && _prompt.text.trim().isEmpty
                ? l10n.t('ag_contentRequired')
                : null,
          ),
          if (!condition) ...[
            const SizedBox(height: LnSpace.md),
            PageSectionTitle(l10n.t('rt_advanced'), padding: EdgeInsets.zero),
            ContentField(
              controller: _zone,
              label: l10n.t('timezone'),
              helper: l10n.t('rt_timezoneHint'),
              ltrOnly: true,
              maxLength: 64,
              enabled: !_busy,
              padding: tight,
            ),
            if (!fired || widget.reschedule) ...[
              const SizedBox(height: LnSpace.sm),
              LnSection(
                padding: EdgeInsets.zero,
                children: [
                  SwitchTile(
                    icon: FIcons.power,
                    title: l10n.t('enabled'),
                    value: _enabled,
                    onChanged: _busy || widget.reschedule
                        ? null
                        : (v) => setState(() => _enabled = v),
                  ),
                ],
              ),
            ],
          ],
          const SizedBox(height: LnSpace.lg),
          BlockButton(
            label: l10n.t(widget.reschedule ? 'rt_scheduleAgain' : 'save'),
            loading: _busy,
            onPressed: _agent == null ? null : _save,
          ),
        ],
      ),
    );
  }
}
