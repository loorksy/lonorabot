// Lonora's Task system (lonora-api-contract §10; apps/web/src/shell/domain/TasksPages.tsx and
// api.ts `TaskView`): the owner's latest tasks, their controls and their creation.
import 'package:flutter/foundation.dart';

import '../../app/services.dart';
import '../../core/json.dart';

String _enc(String value) => Uri.encodeComponent(value);

/// A task as `GET /tasks` projects it (the ticket's task state plus run facts).
@immutable
class TaskView {
  const TaskView({
    required this.id,
    required this.agentId,
    required this.title,
    required this.status,
    required this.version,
    this.description = '',
    this.originThreadId,
    this.workThreadId,
    this.dueAt,
    this.completionCriteria = '',
    this.controlRequested,
    this.canPause = false,
    this.canResume = false,
    this.canCancel = false,
    this.raw = const {},
  });

  factory TaskView.fromJson(Json j) => TaskView(
    id: asStr(j['id']),
    agentId: asStr(j['agent_id']),
    title: asStr(j['title']),
    status: asStr(j['status'], 'queued'),
    version: asInt(j['version']) ?? 1,
    description: asStr(j['description']),
    originThreadId: asString(j['origin_thread_id']),
    workThreadId: asString(j['work_thread_id']),
    dueAt: asDate(j['due_at']),
    completionCriteria: asStr(j['completion_criteria']),
    controlRequested: asString(j['control_requested']),
    canPause: asBool(j['can_pause']),
    canResume: asBool(j['can_resume']),
    canCancel: asBool(j['can_cancel']),
    raw: j,
  );

  final String id;
  final String agentId;
  final String title;

  /// queued · running · waiting · paused · completed · failed · cancelled.
  final String status;
  final int version;
  final String description;
  final String? originThreadId;
  final String? workThreadId;
  final DateTime? dueAt;
  final String completionCriteria;
  final String? controlRequested;
  final bool canPause;
  final bool canResume;
  final bool canCancel;
  final Json raw;

  static const _terminal = {'completed', 'cancelled', 'failed'};

  /// Completed or cancelled: the «مكتملة» tab.
  bool get done => status == 'completed' || status == 'cancelled';
  bool get terminal => _terminal.contains(status);

  /// The conversation the task reports to.
  String? get thread => originThreadId ?? workThreadId;
}

/// TasksPages.tsx's four task words for the server's statuses (`taskStatus`).
String taskStatusKey(String status) => switch (status) {
  'completed' => 'tk_completed',
  'cancelled' => 'tk_cancelled',
  'paused' => 'tk_paused',
  'failed' || 'waiting' => 'tk_awaitingReview',
  _ => 'tk_inProgress',
};

/// «موعد الإنجاز» is a time of day: today at that time, or tomorrow once it has passed
/// (TasksPages.tsx `dueFromTime`).
DateTime dueFromTime(int hour, int minute, DateTime now) {
  var due = DateTime(now.year, now.month, now.day, hour, minute);
  if (!due.isAfter(now)) due = due.add(const Duration(days: 1));
  return due;
}

Future<List<TaskView>> fetchTasks() async =>
    asJsonList(await api.get('/tasks')).map(TaskView.fromJson).toList();

Future<TaskView> fetchTask(String id) async =>
    TaskView.fromJson(asJson(await api.get('/tasks/${_enc(id)}')));

/// `POST /tasks/control {task_id, action: pause|resume|cancel, expected_version}`.
Future<TaskView> controlTask(TaskView task, String action) async =>
    TaskView.fromJson(
      asJson(
        await api.post('/tasks/control', {
          'task_id': task.id,
          'action': action,
          'expected_version': task.version,
        }),
      ),
    );

/// «تحديد كمكتملة»: the work stops; nothing is approved or executed.
Future<TaskView> completeTask(TaskView task) async => TaskView.fromJson(
  asJson(
    await api.post('/tasks/${_enc(task.id)}/complete', {
      'expected_version': task.version,
    }),
  ),
);

/// A finished task's record (the web's delete: `DELETE /tickets/{id}`).
Future<void> deleteTask(String id) => api.delete('/tickets/${_enc(id)}');

/// A new task in [agentId]'s own conversation (`POST /agents/{id}/conversation`, then
/// `POST /tasks?agent_id=&thread_id=`).
Future<TaskView> createTask(
  String agentId, {
  required String title,
  required String description,
  required DateTime? dueAt,
  required String criteria,
}) async {
  final thread = asJson(
    await api.post('/agents/${_enc(agentId)}/conversation'),
  );
  return TaskView.fromJson(
    asJson(
      await api.post(
        '/tasks?agent_id=${_enc(agentId)}&thread_id=${_enc(asStr(thread['id']))}',
        {
          'title': title,
          'description': description,
          'due_at': dueAt?.toUtc().toIso8601String(),
          'completion_criteria': criteria,
        },
      ),
    ),
  );
}
