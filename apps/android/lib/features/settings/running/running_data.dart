// «What is running»: the workspace processes (lonora-api-contract §13, §11.3; apps/mobile
// app/(settings)/running.tsx, apps/web RunningPage.tsx) and the agents' runs in progress, which
// stop with the same `POST /runs/{id}/cancel` the conversation's Stop uses. Runs are never
// created here.
import 'package:flutter/foundation.dart';

import '../../../app/services.dart';
import '../../../core/api/api_error.dart';
import '../../../core/json.dart';
import '../../../core/models/models.dart';
import '../../../state/actions/base.dart';
import '../../../state/app_state.dart';

/// One workspace process and the agent that started it.
@immutable
class WorkspaceProcess {
  const WorkspaceProcess({
    required this.pid,
    required this.agentId,
    required this.agentName,
    required this.command,
    this.startedAt,
    this.stopping = false,
  });

  factory WorkspaceProcess.fromJson(Json j) => WorkspaceProcess(
    pid: asInt(j['pid']) ?? 0,
    agentId: asStr(j['agent_id']),
    agentName: asStr(j['agent_name']),
    command: asStr(j['command']),
    startedAt: asDate(j['started_at']),
    stopping: asBool(j['stopping']),
  );

  final int pid;
  final String agentId;
  final String agentName;
  final String command;
  final DateTime? startedAt;
  final bool stopping;

  /// The tap mark of a stop not yet seen in a server answer.
  String get key => '$agentId:$pid';
}

/// `GET /workspace/running`: null [listedAt] means the workspace has not answered yet; a
/// [stale] list (no answer for a minute) takes no stop.
@immutable
class WorkspaceRunning {
  const WorkspaceRunning({
    this.listedAt,
    this.stale = false,
    this.processes = const [],
    this.stoppingAll = false,
  });

  factory WorkspaceRunning.fromJson(Json j) => WorkspaceRunning(
    listedAt: asDate(j['listed_at']),
    stale: asBool(j['stale']),
    processes: asJsonList(j['processes'])
        .map(WorkspaceProcess.fromJson)
        .toList(),
    stoppingAll: asBool(j['stopping_all']),
  );

  final DateTime? listedAt;
  final bool stale;
  final List<WorkspaceProcess> processes;
  final bool stoppingAll;

  /// The processes grouped by agent, in the order the server listed them.
  Map<String, List<WorkspaceProcess>> get byAgent {
    final groups = <String, List<WorkspaceProcess>>{};
    for (final p in processes) {
      (groups[p.agentId] ??= []).add(p);
    }
    return groups;
  }
}

Future<WorkspaceRunning> fetchWorkspaceRunning() async =>
    WorkspaceRunning.fromJson(asJson(await api.get('/workspace/running')));

/// `POST /workspace/running/stop {pid, agent_id}` (202; the Gateway stops it within ~2 s).
Future<void> stopProcess(WorkspaceProcess p) async {
  await api.post('/workspace/running/stop', {
    'pid': p.pid,
    'agent_id': p.agentId,
  });
}

/// `POST /workspace/running/stop-all` (202).
Future<void> stopAllProcesses() async {
  await api.post('/workspace/running/stop-all');
}

/// The agents' work in progress among the owner's latest runs, newest first: every run that
/// is not finished, except a child whose parent is listed (stopping the parent stops it).
List<Run> runsInProgress(List<Run> runs) {
  final open = [
    for (final r in runs)
      if (!r.isTerminal) r,
  ];
  final ids = {for (final r in open) r.id};
  final top = [
    for (final r in open)
      if (r.parentRunId == null || !ids.contains(r.parentRunId)) r,
  ];
  top.sort((a, b) {
    final x = a.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    final y = b.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    return y.compareTo(x);
  });
  return top;
}

/// Puts [runs] into the owner-wide list (and into a loaded conversation's runs).
AppState _mergeRuns(AppState state, Iterable<Run> runs) {
  final list = [...state.shell.runs];
  var next = state;
  for (final run in runs) {
    final i = list.indexWhere((r) => r.id == run.id);
    if (i >= 0) {
      list[i] = run;
    } else {
      list.insert(0, run);
    }
    final t = next.threads[run.threadId];
    if (t != null) {
      next = next.withThread(t.copyWith(runs: {...t.runs, run.id: run}));
    }
  }
  return next.copyWith(shell: next.shell.copyWith(runs: list));
}

/// Re-reads the owner's latest runs (`GET /runs`) into the shell, after a run event the
/// realtime patch could not place (its conversation is not loaded). A failed read keeps the
/// last list.
class RefreshOwnerRunsAction extends AppAction {
  @override
  Future<AppState?> reduce() async {
    if (!signedIn) return null;
    try {
      final runs = asJsonList(await apiClient.get('/runs')).map(Run.fromJson);
      return state.copyWith(shell: state.shell.copyWith(runs: runs.toList()));
    } on ApiError {
      return null;
    } on SessionRequestCancelled {
      return null;
    }
  }
}

/// Stops one run of an agent: `POST /runs/{id}/cancel` (the run and its unfinished children).
/// A refusal is kept in [error] (never thrown) for the screen to show.
class StopRunAction extends AppAction {
  StopRunAction(this.runId);

  final String runId;

  /// The server's (or the network's) refusal; null on success or a cancelled session.
  ApiError? error;

  @override
  Future<AppState?> reduce() async {
    try {
      final data = asJson(
        await apiClient.post('/runs/${Uri.encodeComponent(runId)}/cancel'),
      );
      if (data.isEmpty) return null;
      return _mergeRuns(state, [Run.fromJson(data)]);
    } on ApiError catch (e) {
      error = e;
      return null;
    } on SessionRequestCancelled {
      return null;
    }
  }
}
