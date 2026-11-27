import '../../l10n/l10n.dart';

/// Android-only labels of the tasks page: the Web's words for the Task system
/// (apps/web/src/shell/domain/TasksPages.tsx: tabs, the four status words, details, create),
/// which the Expo catalog lacks.
void registerTasksStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('tk_active')) return;
  target.register(_tasksStrings);
}

const Map<String, List<String>> _tasksStrings = {
  'tk_active': ['نشطة', 'Active'],
  'tk_scheduled': ['مجدولة', 'Scheduled'],
  'tk_done': ['مكتملة', 'Completed'],
  'tk_runs': ['التشغيلات الأخيرة', 'Recent runs'],
  'tk_inProgress': ['قيد التنفيذ', 'In progress'],
  'tk_awaitingReview': ['بانتظار المراجعة', 'Awaiting review'],
  'tk_paused': ['متوقفة مؤقتًا', 'Paused'],
  'tk_completed': ['مكتملة', 'Completed'],
  'tk_cancelled': ['ملغاة', 'Cancelled'],
  'tk_none': ['لا توجد مهام.', 'No tasks.'],
  'tk_searchPh': ['البحث في المهام', 'Search tasks'],
  'tk_details': ['تفاصيل المهمة', 'Task details'],
  'tk_due': ['موعد الإنجاز', 'Due'],
  'tk_notSet': ['غير محدد', 'Not set'],
  'tk_criterion': ['معيار الإنجاز', 'Completion criterion'],
  'tk_criterionDefault': ['إنجاز العمل المطلوب', 'The requested work is done'],
  'tk_viewConversation': ['عرض المحادثة', 'View conversation'],
  'tk_markDone': ['تحديد كمكتملة', 'Mark as completed'],
  'tk_markDoneHint': [
    'يتوقف العمل عليها؛ لا يُعتمد أو يُنفَّذ أي شيء.',
    'The work stops; nothing is approved or executed.',
  ],
  'tk_cancelTask': ['إلغاء المهمة', 'Cancel task'],
  'tk_cancelQ': ['إلغاء هذه المهمة؟', 'Cancel this task?'],
  'tk_keep': ['إبقاء', 'Keep'],
  'tk_cancelBody': [
    'يتوقف العمل عليها ولا تُستأنف. لا يُعتمد أو يُنفَّذ أي شيء.',
    'Work on it stops and does not resume. Nothing is approved or executed.',
  ],
  'tk_deleteQ': ['حذف هذه المهمة؟', 'Delete this task?'],
  'tk_deleted': ['حُذفت المهمة', 'Task deleted'],
  'tk_paused_toast': ['أُوقفت المهمة مؤقتًا', 'Task paused'],
  'tk_resumed': ['استُؤنفت المهمة', 'Task resumed'],
  'tk_cancelledToast': ['أُلغيت المهمة', 'Task cancelled'],
  'tk_responsible': ['الوكيل المسؤول', 'Responsible agent'],
  'tk_needed': ['المطلوب', 'What is needed'],
  'tk_dueTime': ['وقت الإنجاز', 'Due time'],
  'tk_dueHint': [
    'اليوم في هذا الوقت، أو غدًا إن كان قد مضى. موعد مستهدف، لا يبدأ العمل به.',
    'Today at this time, or tomorrow once it has passed. A target, not a trigger.',
  ],
  'task_not_found': ['هذه المهمة لم تعد موجودة.', 'The task no longer exists.'],
  'task_use_control': [
    'تُدار هذه المهمة من أزرارها: إيقاف أو استئناف أو إنهاء.',
    'This task is managed with its own buttons: pause, resume or finish.',
  ],
};
