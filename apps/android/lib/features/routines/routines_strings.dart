import '../../l10n/l10n.dart';

/// Android-only labels of the routines pages: the editor's fields and repeat options in Lonora's
/// own words; Lonora's catalog keys (`routines`, `routineTask`, `nextRun`, `history`, `once`, …)
/// are used wherever they exist.
void registerRoutinesStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('rt_when')) return;
  target.register(_routinesStrings);
}

const Map<String, List<String>> _routinesStrings = {
  'rt_when': ['متى', 'When'],
  'rt_agentWill': ['ما سيفعله الوكيل', 'Agent will'],
  'rt_advanced': ['إعدادات متقدمة', 'Advanced settings'],
  'rt_repeat': ['التكرار', 'Repeat'],
  'rt_noRepeat': ['لا تتكرر', 'Does not repeat'],
  'rt_daily': ['يوميًا', 'Daily'],
  'rt_weekly': ['أسبوعيًا', 'Weekly'],
  'rt_monthly': ['شهريًا', 'Monthly'],
  'rt_weekdays': ['أيام العمل', 'Weekdays'],
  'rt_weekend': ['عطلة نهاية الأسبوع', 'Weekend'],
  'rt_custom': ['مخصص', 'Custom'],
  'rt_date': ['التاريخ', 'Date'],
  'rt_time': ['الوقت', 'Time'],
  'rt_weekday': ['اليوم', 'Day'],
  'rt_dayOfMonth': ['يوم الشهر', 'Day of the month'],
  'rt_everyMinutes': ['كل (بالدقائق)', 'Every (minutes)'],
  'rt_cronHint': [
    'دقيقة ساعة يوم-الشهر شهر يوم-الأسبوع',
    'minute hour day-of-month month day-of-week',
  ],
  'rt_promptHint': [
    'مثال: لخّص أخبار السوق قبل الافتتاح',
    'e.g. Summarize the market news before the open',
  ],
  'rt_timezoneHint': [
    'تُقرأ أوقات الجدول بهذه المنطقة الزمنية.',
    'Schedule times are read in this time zone.',
  ],
  // Schedule lines.
  'rt_dailyAt': ['كل يوم الساعة {time}', 'Every day at {time}'],
  'rt_weekdaysAt': ['أيام العمل الساعة {time}', 'Weekdays at {time}'],
  'rt_weekendAt': ['عطلة نهاية الأسبوع الساعة {time}', 'Weekends at {time}'],
  'rt_weeklyAt': ['أسبوعيًا يوم {day} الساعة {time}', 'Every {day} at {time}'],
  'rt_monthlyAt': [
    'يوم {day} من كل شهر الساعة {time}',
    'Monthly on day {day} at {time}',
  ],
  'rt_onceAt': ['مرة واحدة · {date} الساعة {time}', 'Once · {date} at {time}'],
  'rt_everyHours': ['كل {n} ساعة', 'Every {n} h'],
  'rt_everyMinutesN': ['كل {n} دقيقة', 'Every {n} min'],
  // Detail and list.
  'rt_status': ['الحالة', 'Status'],
  'rt_lastRun': ['آخر تنفيذ', 'Last run'],
  'rt_agent': ['الوكيل', 'Agent'],
  'rt_editSchedule': ['تعديل الجدول', 'Edit schedule'],
  'rt_deleteSchedule': ['حذف الجدول', 'Delete schedule'],
  'rt_deleteQ': ['حذف هذا الجدول؟', 'Delete this schedule?'],
  'rt_deleteBody': [
    'يتوقف تنفيذه، ويبقى ما أنجزه من قبل.',
    'It stops running; what it already did stays.',
  ],
  'rt_saved': ['حُفظ الجدول', 'Schedule saved'],
  'rt_deleted': ['حُذف الجدول', 'Schedule deleted'],
  'rt_pausedToast': ['أُوقف الجدول مؤقتًا', 'Schedule paused'],
  'rt_resumedToast': ['استُؤنف الجدول', 'Schedule resumed'],
  'rt_scheduleAgain': ['جدولة من جديد', 'Schedule again'],
  'rt_rescheduleHint': [
    'نُفّذت هذه المهمة. اختر تاريخًا ووقتًا جديدين لجدولتها من جديد.',
    'This task already ran. Choose a new date and time to schedule it again.',
  ],
  'rt_chooseAgent': ['اختر الوكيل', 'Choose the agent'],
  'rt_invalidInterval': [
    'أدخل عددًا من الدقائق بين 1 و525600.',
    'Enter minutes between 1 and 525600.',
  ],
  'rt_invalidDay': ['أدخل يومًا بين 1 و31.', 'Enter a day between 1 and 31.'],
  'rt_invalidCron': [
    'أدخل تعبير Cron من خمسة أجزاء.',
    'Enter a five-part cron expression.',
  ],
  'rt_timePassed': [
    'هذا الوقت مضى. اختر وقتًا لم يأتِ بعد.',
    'That time has passed. Choose a time that has not passed.',
  ],
  // Server codes of a routine save (errorText falls back to the label of the code).
  'run_at_past': [
    'هذا الوقت مضى. اختر وقتًا جديدًا.',
    'That time has passed. Choose a new time.',
  ],
  'one_schedule_required': [
    'اختر طريقة واحدة للجدولة.',
    'Choose one way to schedule it.',
  ],
  'run_at_timezone_required': [
    'الوقت يحتاج إلى منطقة زمنية.',
    'The time needs a time zone.',
  ],
  'invalid_cron': ['تعبير Cron غير صالح.', 'The cron expression is invalid.'],
  'invalid_timezone': [
    'المنطقة الزمنية غير معروفة.',
    'The time zone is not known.',
  ],
  'routine_not_found': [
    'هذا الجدول لم يعد موجودًا.',
    'This schedule no longer exists.',
  ],
  // Conditional schedules: a price watch that wakes the agent (apps/web SchedulesPages.tsx).
  'rt_atTime': ['في وقت محدد', 'At a set time'],
  'rt_onCondition': ['عند تحقق شرط', 'When a condition is met'],
  // The editor's segment (the full words wrap in half a row).
  'rt_conditionTab': ['عند تحقق شرط', 'On a condition'],
  'rt_condition': [
    'الشرط — للتنبيه الشرطي',
    'Condition — for the conditional alert',
  ],
  'rt_conditionHint': [
    'مثل: تحت 2330 أو فوق 2350',
    'e.g. below 2330 or above 2350',
  ],
  'rt_conditionInvalid': ['اكتب شرط التنبيه.', 'Write the alert condition.'],
  'watch_price_required': [
    'أدخل مستوى سعر أكبر من صفر.',
    'Enter a price level above zero.',
  ],
};
