export type Agent = {
  id: string;
  name: string;
  instructions: string;
  created_at: string;
};

export type Thread = {
  id: string;
  agent_id: string;
  title: string;
  created_at: string;
};

export type Message = {
  id: string;
  seq: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export type Run = {
  id: string;
  thread_id: string;
  status: "queued" | "leased" | "running" | "completed" | "failed" | "cancelled";
  error_code: string | null;
};

export type Routine = {
  id: string;
  thread_id: string;
  prompt: string;
  interval_seconds: number;
  next_run_at: string;
  enabled: boolean;
};

export type Health = {
  status: string;
  model_configured: boolean;
  worker: string;
};

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
  ) {
    super(code);
  }
}

const apiPrefix = import.meta.env.DEV ? "/api" : "";
const tokenStorageKey = "lonora.access-token";
let token = sessionStorage.getItem(tokenStorageKey);

export function getToken(): string | null {
  return token;
}

export function saveToken(value: string | null): void {
  token = value;
  if (value) sessionStorage.setItem(tokenStorageKey, value);
  else sessionStorage.removeItem(tokenStorageKey);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${apiPrefix}${path}`, { ...init, headers });
  if (!response.ok) {
    let code = "request_failed";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") code = body.detail;
    } catch {
      code = "request_failed";
    }
    if (response.status === 401 && path !== "/auth/login") {
      saveToken(null);
      window.dispatchEvent(new Event("lonora:unauthorized"));
    }
    throw new ApiError(code, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string; expires_in: number }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ id: string; email: string }>("/auth/me"),
  health: () => request<Health>("/health"),
  agents: () => request<Agent[]>("/agents"),
  createAgent: (name: string, instructions: string) =>
    request<Agent>("/agents", {
      method: "POST",
      body: JSON.stringify({ name, instructions }),
    }),
  threads: (agentId: string) => request<Thread[]>(`/agents/${agentId}/threads`),
  createThread: (agentId: string, title: string) =>
    request<Thread>(`/agents/${agentId}/threads`, {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  thread: (threadId: string) =>
    request<{ thread: Thread; messages: Message[] }>(`/threads/${threadId}`),
  send: (threadId: string, content: string) =>
    request<{ message_id: string; run_id: string; status: string }>(
      `/threads/${threadId}/messages`,
      { method: "POST", body: JSON.stringify({ content }) },
    ),
  run: (runId: string) => request<Run>(`/runs/${runId}`),
  memory: (agentId: string) =>
    request<{ agent_id: string; content: string }>(`/agents/${agentId}/memory`),
  saveMemory: (agentId: string, content: string) =>
    request<{ agent_id: string; content: string }>(`/agents/${agentId}/memory`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  routines: (agentId: string) => request<Routine[]>(`/agents/${agentId}/routines`),
  createRoutine: (agentId: string, prompt: string, interval_seconds: number) =>
    request<Routine>(`/agents/${agentId}/routines`, {
      method: "POST",
      body: JSON.stringify({ prompt, interval_seconds }),
    }),
};
