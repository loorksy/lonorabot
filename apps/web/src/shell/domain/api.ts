import type {
  ActivityPage,
  AgentGoal,
  AgentSkill,
  KnowledgeItem,
  KnowledgeLink,
  Resource,
  Routine,
  RoutineInput,
  SkillVersionEntry,
} from "@lonora/contracts";
import { api, request } from "../../lib/api";

/** A Task as `GET /api/tasks` projects it (the ticket's `state.task` plus run facts). */
export type TaskView = {
  id: string;
  agent_id: string;
  title: string;
  description: string;
  version: number;
  status: "queued" | "running" | "waiting" | "paused" | "completed" | "failed" | "cancelled";
  origin_thread_id: string;
  work_thread_id: string;
  due_at: string | null;
  completion_criteria: string;
  control_requested: "pause" | "cancel" | "complete" | null;
  can_pause: boolean;
  can_resume: boolean;
  can_cancel: boolean;
};
export type TaskInput = {
  title: string;
  description: string;
  due_at?: string | null;
  completion_criteria?: string;
};
/** A trading goal (a plan under the agent's grant), as much of it as «الأهداف» lists. */
export type TradingGoalView = {
  id: string;
  agent_id: string;
  thread_id: string | null;
  title: string;
  objective?: string;
  status: string;
  symbol?: string;
};
export type ArtifactPayload = { name: string; size: number; media_type: string; key?: string };

const body = (agentId: string, payload: unknown) => ({ agent_id: agentId, payload });

/* The domain pages' server calls (WP-H and the Task fields). Every route is owner-only. */
export const domainApi = {
  tasks: () => api.get<TaskView[]>("/tasks"),
  task: (id: string) => api.get<TaskView>(`/tasks/${id}`),
  createTask: (agentId: string, threadId: string, input: TaskInput) =>
    api.post<TaskView>(
      `/tasks?agent_id=${encodeURIComponent(agentId)}&thread_id=${encodeURIComponent(threadId)}`,
      input,
    ),
  controlTask: (task: TaskView, action: "pause" | "resume" | "cancel") =>
    api.post<TaskView>("/tasks/control", {
      task_id: task.id,
      action,
      expected_version: task.version,
    }),
  /** «تحديد كمكتملة»: the work stops; nothing is approved or executed. */
  completeTask: (task: TaskView) =>
    api.post<TaskView>(`/tasks/${task.id}/complete`, { expected_version: task.version }),

  routines: (agentId?: string) =>
    api.get<Routine[]>(agentId ? `/routines?agent_id=${encodeURIComponent(agentId)}` : "/routines"),
  createRoutine: (agentId: string, input: RoutineInput) =>
    api.post<Routine>(`/routines/${agentId}`, input),
  saveRoutine: (id: string, input: RoutineInput) => api.put<Routine>(`/routines/${id}`, input),
  deleteRoutine: (id: string) => api.delete<{ deleted: boolean }>(`/routines/${id}`),
  /** «عند تحقق شرط»: a market watch that wakes the agent with the prompt (no authority). */
  createWatch: (agentId: string, payload: Record<string, unknown>) =>
    api.post<Resource>("/watches", body(agentId, payload)),

  goals: (agentId: string) =>
    api.get<Resource<AgentGoal>[]>(`/agent-goals?agent_id=${encodeURIComponent(agentId)}`),
  createGoal: (agentId: string, goal: AgentGoal) =>
    api.post<Resource<AgentGoal>>("/agent-goals", body(agentId, goal)),
  saveGoal: (row: Resource<AgentGoal>, goal: AgentGoal) =>
    api.put<Resource<AgentGoal>>(`/agent-goals/${row.id}`, { version: row.version, payload: goal }),
  tradingGoals: (agentId: string) =>
    api.get<TradingGoalView[]>(`/trading/goals?agent_id=${encodeURIComponent(agentId)}`),

  knowledge: (agentId: string) => api.get<KnowledgeItem[]>(`/agents/${agentId}/knowledge`),
  addNote: (agentId: string, title: string, content: string) =>
    api.post<{ id: string }>(`/agents/${agentId}/knowledge/notes`, { title, content }),
  saveNote: (agentId: string, id: string, title: string, content: string) =>
    api.put<{ id: string }>(`/agents/${agentId}/knowledge/notes/${id}`, { title, content }),
  addLink: (agentId: string, link: KnowledgeLink) =>
    api.post<Resource<KnowledgeLink>>("/knowledge-links", body(agentId, link)),
  saveLink: (id: string, version: number, link: KnowledgeLink) =>
    api.put<Resource<KnowledgeLink>>(`/knowledge-links/${id}`, { version, payload: link }),

  skills: (agentId: string) =>
    api.get<Resource<AgentSkill>[]>(`/skills?agent_id=${encodeURIComponent(agentId)}`),
  skill: (id: string) => api.get<Resource<AgentSkill>>(`/skills/${id}`),
  createSkill: (agentId: string, skill: AgentSkill) =>
    api.post<Resource<AgentSkill>>("/skills", body(agentId, skill)),
  saveSkill: (row: Resource<AgentSkill>, skill: AgentSkill) =>
    api.put<Resource<AgentSkill>>(`/skills/${row.id}`, { version: row.version, payload: skill }),
  /** «سجل الإصدارات», newest first. */
  skillVersions: (id: string) => api.get<SkillVersionEntry[]>(`/skills/${id}/versions`),
  /** «الرجوع إلى الإصدار N»: a new version with that payload; undo restores the one left. */
  restoreSkill: (id: string, version: number, expectedVersion: number) =>
    api.post<Resource<AgentSkill>>(`/skills/${id}/restore`, {
      version,
      expected_version: expectedVersion,
    }),

  files: (agentId?: string) =>
    api.get<Resource<ArtifactPayload>[]>(
      agentId ? `/artifacts?agent_id=${encodeURIComponent(agentId)}` : "/artifacts",
    ),
  fileText: async (id: string) => {
    const response = await fetch(`/api/artifacts/${id}/file`, { credentials: "include" });
    if (!response.ok) throw new Error("artifact_file_missing");
    return response.text();
  },
  /** «رفع ملف» / «ملف نصي جديد»: stored as an artifact of the agent (none = workspace). */
  uploadFile: (file: File, agentId?: string) => {
    const data = new FormData();
    data.append("file", file);
    if (agentId) data.append("agent_id", agentId);
    return request<Resource<ArtifactPayload>>("/artifacts/upload", { method: "POST", body: data });
  },
  /** «تحرير الملف» for a text file (Q36). */
  saveText: (id: string, name: string, content: string) =>
    api.put<Resource<ArtifactPayload>>(`/artifacts/${id}/text`, { name, content }),
  deleteFile: (id: string) => api.delete<{ deleted: boolean }>(`/artifacts/${id}`),

  activity: (before?: number) =>
    api.get<ActivityPage>(before ? `/activity?limit=50&before=${before}` : "/activity?limit=50"),
  seenAll: () => api.post<{ seen: number }>("/attention/seen-all", {}),
};
