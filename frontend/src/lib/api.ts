export type ExecutionStatus =
  | "pending"
  | "running"
  | "waiting_for_approval"
  | "completed"
  | "failed"
  | "rolled_back";

export type ToolCallStatus =
  | "pending"
  | "success"
  | "failed"
  | "approved"
  | "rejected";

export type Execution = {
  id: string;
  workflow_id: string;
  status: ExecutionStatus;
  current_step_index: number;
  checkpoint_data: unknown;
  user_input: string;
  final_output: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  eval_score: number | null;
  eval_details: {
    accuracy?: number;
    completeness?: number;
    logic?: number;
    comment?: string;
  } | null;
  feedback: string | null;
};

export type ToolCall = {
  id: string;
  execution_id: string;
  tool_name: string;
  input_params: unknown;
  output_result: unknown;
  status: ToolCallStatus;
  requires_approval: boolean;
  approved_by: string | null;
  started_at: string | null;
  completed_at: string | null;
};

export type ExecutionDetail = Execution & { tool_calls: ToolCall[] };

export type Trace = {
  current_step_index: number;
  status: ExecutionStatus;
  tool_calls: ToolCall[];
};

export type Workflow = {
  id: string;
  name: string;
  description: string;
  agent_chain: unknown[];
  dag_definition: unknown | null;
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type AlertEvent = {
  id: string;
  rule_id: string;
  severity: string;
  message: string;
  status: string;
  triggered_at: string;
  resolved_at: string | null;
};

export type Intervention = {
  id: string;
  operator: string;
  action: string;
  modified_plan: string | null;
  created_at: string;
};

const BASE = "/api";
const ADMIN_API_KEY = import.meta.env.VITE_ADMIN_API_KEY as string | undefined;
const TOKEN_KEY = "agenthub.access_token";

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAccessToken();
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(ADMIN_API_KEY ? { "X-API-Key": ADMIN_API_KEY } : {}),
    },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listExecutions: (status?: ExecutionStatus) =>
    request<Execution[]>(
      `/executions?limit=100${status ? `&status=${status}` : ""}`,
    ),
  getExecution: (id: string) => request<ExecutionDetail>(`/executions/${id}`),
  getTrace: (id: string) => request<Trace>(`/executions/${id}/trace`),
  listWorkflows: () => request<Workflow[]>("/workflows"),
  createExecution: (workflow_id: string, user_input: string) =>
    request<{ execution_id: string; status: ExecutionStatus }>("/executions", {
      method: "POST",
      body: JSON.stringify({ workflow_id, user_input }),
    }),
  cancelExecution: (id: string) =>
    request<Execution>(`/executions/${id}/cancel`, { method: "POST" }),
  resumeExecution: (id: string, approved: boolean) =>
    request<{ execution_id: string; status: ExecutionStatus }>(
      `/executions/${id}/resume`,
      { method: "POST", body: JSON.stringify({ approved }) },
    ),
  approveToolCall: (id: string) =>
    request<ToolCall>(`/tool_calls/${id}/approve`, { method: "POST" }),
  rejectToolCall: (id: string) =>
    request<ToolCall>(`/tool_calls/${id}/reject`, { method: "POST" }),
  sendFeedback: (id: string, feedback: string) =>
    request<Execution>(`/executions/${id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),
  saveWorkflow: (payload: {
    name: string;
    description: string;
    agent_chain: unknown[];
    dag_definition?: unknown;
  }) =>
    request<Workflow>("/workflows", {
      method: "POST",
      body: JSON.stringify({ ...payload, created_by: "admin" }),
    }),
  listAlerts: (status?: string) =>
    request<AlertEvent[]>(`/alerts${status ? `?status=${status}` : ""}`),
  alertStats: () =>
    request<{ total: number; active: number; resolved: number }>("/alerts/stats"),
  resolveAlert: (id: string) =>
    request<AlertEvent>(`/alerts/${id}/resolve`, { method: "PUT" }),
  listInterventions: (id: string) =>
    request<Intervention[]>(`/executions/${id}/interventions`),
  intervene: (
    id: string,
    payload: { operator: string; action: string; modified_plan?: string | null },
  ) =>
    request<{ status: string }>(`/executions/${id}/intervene`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  request: <T,>(path: string, init?: RequestInit) => request<T>(path, init),
};

export const auth = {
  sendCode: (payload: { email: string }) =>
    request<{ status: string }>("/auth/send-code", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  register: (payload: { email: string; password: string; full_name: string; code: string }) =>
    request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  login: (payload: { email: string; password: string; code: string }) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  me: () => request<AuthUser>("/auth/me"),
};

export type AuthUser = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  organization_id: string | null;
};

export type AuthResponse = {
  user: AuthUser;
  organization: { id: string; name: string; slug: string; settings: unknown };
  access_token: string;
  refresh_token: string;
};
