export type ExecutionStatus =
  | "pending"
  | "running"
  | "waiting_for_approval"
  | "completed"
  | "failed"
  | "rolled_back";

export type ToolCallStatus =
  "pending" | "success" | "failed" | "approved" | "rejected";

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
  steps: Array<{
    role?: string;
    name?: string;
    agent_id?: string | null;
    task_id?: string;
    capability_id?: string;
  }> | null;
  token_usage: Record<string, { input_tokens: number; output_tokens: number }> | null;
  model_used: string[] | null;
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
  cost?: number | null;
  token_usage?: Record<string, { input_tokens: number; output_tokens: number }> | null;
  model_used?: string[] | null;
  verify_status?: string | null;
  approval_mismatch_count?: number;
  side_effect_proposals?: Array<{
    step_id?: string;
    capability?: string;
    tool?: string;
    params?: Record<string, unknown>;
    params_canonical?: string;
  }> | null;
  spans?: Array<{
    span: string;
    status: string;
    latency_ms?: number | null;
    model?: string | null;
    tokens?: number | null;
    cost?: number | null;
    error?: string | null;
    recorded_at?: string | null;
  }>;
};

export type BenchmarkReport = {
  experiment?: string;
  contract?: string;
  generated_at?: string;
  runs?: number;
  metrics_per_arm?: Record<
    string,
    {
      ssr_bcr?: number;
      ssr_bcr_ci95?: [number, number] | null;
      sor?: number;
      user?: number;
      gcr?: number | null;
      tool_accuracy?: number | null;
      param_accuracy?: number | null;
      cost_per_safe_success?: number | null;
      p95_latency_ms?: number | null;
    }
  >;
  evidence_chain?: Record<string, Record<string, number>>;
  tiers?: {
    r2_hard?: Record<string, Record<string, Record<string, number | null>>>;
  };
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

export type ModelConfig = {
  id: string;
  name: string;
  provider: string;
  base_url: string;
  model: string;
  max_tokens: number;
  cost_per_1k_tokens: number;
  priority: number;
  timeout: number;
  max_retries: number;
  enabled: boolean;
  is_active: boolean;
  is_default: boolean;
};

export type UserApiKey = {
  id: string;
  provider: string;
  model: string;
  base_url: string;
  api_key_masked: string;
  is_active: boolean;
  created_at: string;
};

export type Skill = {
  id: string;
  name: string;
  description: string;
  goal: Record<string, unknown>;
  plan_template: Record<string, unknown>;
  icon: string;
  organization_id: string | null;
  created_by: string | null;
  created_at: string;
};

export type ToolSpec = {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  timeout: number;
  requires_approval: boolean;
};

export type QuotaSummary = {
  organization_id: string | null;
  monthly_token_used: number;
  monthly_token_budget: number;
  monthly_cost_used_cny: number | null;
  monthly_cost_budget_cny: number;
  concurrent_llm_calls: number;
  concurrent_llm_limit: number;
  month: string;
};

export type ExecutionFeedback = {
  id: string;
  execution_id: string;
  user_id: string;
  rating: number;
  comment: string | null;
  created_at: string;
};

export type DocumentItem = {
  id: string;
  name: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type NotificationItem = {
  id: string;
  channel: string;
  template: string;
  params: Record<string, unknown>;
  status: string;
  error: string;
  created_at: string;
};

export type UsageSummary = {
  total_executions: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost: number;
  today_tokens: number;
  today_cost: number;
};

export type EvalDataset = {
  id: string;
  name: string;
  description: string;
  items: Array<{ input?: string; expected?: string }>;
  created_at: string;
};

export type EvalRun = {
  id: string;
  dataset_id: string;
  status: string;
  score: number | null;
  report: Record<string, unknown>;
  created_at: string;
  completed_at: string | null;
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
const ACCESS_TOKEN_KEY = "agenthub.access_token";
const REFRESH_TOKEN_KEY = "agenthub.refresh_token";
const AUTH_PUBLIC_PATHS = new Set([
  "/auth/login",
  "/auth/register",
  "/auth/send-code",
  "/auth/forgot-password",
  "/auth/verify-reset-code",
  "/auth/reset-password",
  "/auth/refresh",
]);

export class ApiError extends Error {
  code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

export function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string | null) {
  if (token) localStorage.setItem(ACCESS_TOKEN_KEY, token);
  else localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setRefreshToken(token: string | null) {
  if (token) localStorage.setItem(REFRESH_TOKEN_KEY, token);
  else localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function clearTokens() {
  setAccessToken(null);
  setRefreshToken(null);
}

export function logout() {
  clearTokens();
  if (typeof window !== "undefined") {
    window.location.reload();
  }
}

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refreshToken = getRefreshToken();
      if (!refreshToken) return null;
      try {
        const res = await fetch(`${BASE}/auth/refresh`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${refreshToken}`,
          },
        });
        if (!res.ok) return null;
        const data = (await res.json()) as { access_token?: string };
        if (data.access_token) {
          setAccessToken(data.access_token);
          return data.access_token;
        }
        return null;
      } catch {
        return null;
      } finally {
        refreshPromise = null;
      }
    })();
  }
  return refreshPromise;
}

async function performRequest(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const token = getAccessToken();
  return fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(ADMIN_API_KEY ? { "X-API-Key": ADMIN_API_KEY } : {}),
    },
    ...init,
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res = await performRequest(path, init);

  if (res.status === 401 && !AUTH_PUBLIC_PATHS.has(path)) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await performRequest(path, init);
    } else {
      clearTokens();
      throw new ApiError("登录已过期，请重新登录", "REFRESH_TOKEN_EXPIRED");
    }
  }

  if (!res.ok) {
    const text = await res.text();
    let message = text || `HTTP ${res.status}`;
    let code: string | undefined;
    try {
      const data = JSON.parse(text);
      if (data?.detail) {
        if (typeof data.detail === "string") {
          message = data.detail;
        } else if (data.detail && typeof data.detail === "object") {
          code = data.detail.code;
          message = data.detail.message || JSON.stringify(data.detail);
        }
      }
    } catch {
      // 保持原始错误文本
    }
    throw new ApiError(message, code);
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
  getBenchmarkReport: () => request<BenchmarkReport>("/eval/benchmark/latest"),
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
  submitRating: (id: string, rating: number, comment?: string) =>
    request<Execution>(`/executions/${id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback: `rating-${rating}`, rating, comment }),
    }),
  listFeedback: (id: string) =>
    request<ExecutionFeedback[]>(`/executions/${id}/feedback`),
  optimizePrompt: (content: string) =>
    request<{ optimized: string }>("/prompts/optimize", {
      method: "POST",
      body: JSON.stringify({ content }),
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
    request<{ total: number; active: number; resolved: number }>(
      "/alerts/stats",
    ),
  resolveAlert: (id: string) =>
    request<AlertEvent>(`/alerts/${id}/resolve`, { method: "PUT" }),
  listInterventions: (id: string) =>
    request<Intervention[]>(`/executions/${id}/interventions`),
  intervene: (
    id: string,
    payload: {
      operator: string;
      action: string;
      modified_plan?: string | null;
    },
  ) =>
    request<{ status: string }>(`/executions/${id}/intervene`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listModels: () => request<ModelConfig[]>("/models"),
  createModel: (payload: {
    name: string;
    provider: string;
    base_url: string;
    api_key?: string;
    model: string;
    max_tokens?: number;
    cost_per_1k_tokens?: number;
    is_default?: boolean;
  }) =>
    request<ModelConfig>("/models", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateModel: (
    id: string,
    payload: Partial<{
      name: string;
      provider: string;
      base_url: string;
      api_key: string;
      model: string;
      max_tokens: number;
      cost_per_1k_tokens: number;
      is_active: boolean;
      is_default: boolean;
    }>,
  ) =>
    request<ModelConfig>(`/models/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  testModel: (id: string) =>
    request<{ ok: boolean; response?: string; error?: string }>(
      `/models/${id}/test`,
      { method: "POST" },
    ),
  listUserApiKeys: () => request<UserApiKey[]>("/user-api-keys"),
  createUserApiKey: (payload: {
    provider: string;
    model: string;
    base_url: string;
    api_key: string;
  }) =>
    request<UserApiKey>("/user-api-keys", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateUserApiKey: (id: string, is_active: boolean) =>
    request<UserApiKey>(`/user-api-keys/${id}`, {
      method: "PUT",
      body: JSON.stringify({ is_active }),
    }),
  deleteUserApiKey: (id: string) =>
    request<void>(`/user-api-keys/${id}`, { method: "DELETE" }),
  listSkills: () => request<Skill[]>("/skills"),
  listTools: () => request<ToolSpec[]>("/tools"),
  getQuota: () => request<QuotaSummary>("/quotas"),
  createSkill: (payload: {
    name: string;
    description: string;
    goal: Record<string, unknown>;
    plan_template: Record<string, unknown>;
    icon?: string;
  }) =>
    request<Skill>("/skills", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteSkill: (id: string) =>
    request<void>(`/skills/${id}`, { method: "DELETE" }),
  executeSkill: (id: string, input: string) =>
    request<{ execution_id: string; status: ExecutionStatus }>(
      `/skills/${id}/execute`,
      { method: "POST", body: JSON.stringify({ input }) },
    ),
  listDocuments: () => request<DocumentItem[]>("/documents"),
  createDocument: (payload: {
    name: string;
    content: string;
    metadata?: Record<string, unknown>;
  }) =>
    request<DocumentItem>("/documents", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const token = getAccessToken();
    return fetch(`${BASE}/documents/upload`, {
      method: "POST",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(ADMIN_API_KEY ? { "X-API-Key": ADMIN_API_KEY } : {}),
      },
      body: form,
    }).then((res) => {
      if (!res.ok)
        return res.text().then((text) => Promise.reject(new Error(text)));
      return res.json() as Promise<DocumentItem>;
    });
  },
  deleteDocument: (id: string) =>
    request<void>(`/documents/${id}`, { method: "DELETE" }),
  searchDocuments: (query: string, top_k = 5) =>
    request<DocumentItem[]>("/documents/search", {
      method: "POST",
      body: JSON.stringify({ query, top_k }),
    }),
  listNotifications: () => request<NotificationItem[]>("/notifications"),
  testNotification: (payload: {
    channel: string;
    template?: string;
    params?: Record<string, unknown>;
  }) =>
    request<{ status: string; error: string }>("/notifications/test", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getUsage: () => request<UsageSummary>("/usage"),
  listEvalDatasets: () => request<EvalDataset[]>("/eval/datasets"),
  createEvalDataset: (payload: {
    name: string;
    description?: string;
    items: Array<Record<string, unknown>>;
  }) =>
    request<EvalDataset>("/eval/datasets", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteEvalDataset: (id: string) =>
    request<void>(`/eval/datasets/${id}`, { method: "DELETE" }),
  runEval: (payload: {
    dataset_id: string;
    workflow_id?: string;
    threshold?: number;
  }) =>
    request<EvalRun>("/eval/run", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listEvalReports: () => request<EvalRun[]>("/eval/reports"),
  request: <T>(path: string, init?: RequestInit) => request<T>(path, init),
};

export const auth = {
  sendCode: (payload: { email: string; mode?: "login" | "register" }) =>
    request<{ status: string }>("/auth/send-code", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  register: (payload: {
    email: string;
    password: string;
    full_name: string;
    code: string;
  }) =>
    request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  login: (payload: { email: string; password: string }) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  forgotPassword: (payload: { email: string }) =>
    request<{ success: boolean; message: string }>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  verifyResetCode: (payload: { email: string; code: string }) =>
    request<{ success: boolean; message: string }>("/auth/verify-reset-code", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  resetPassword: (payload: {
    email: string;
    code: string;
    new_password: string;
  }) =>
    request<{ success: boolean; message: string }>("/auth/reset-password", {
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
