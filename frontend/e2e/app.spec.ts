import { expect, test } from "@playwright/test";

test("unauthenticated landing page renders hero and CTAs", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("让 Agent 不再是固定岗位")).toBeVisible();
  await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始体验" })).toBeVisible();
});

test("login button opens the authentication dialog", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "登录" }).click();

  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("heading", { name: "登录 AgentHub" })).toBeVisible();
});

test("authenticated chat page can render a new conversation", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("agenthub.access_token", "playwright-e2e-token");
    localStorage.setItem("agenthub.onboarded", "1");
  });
  await page.route("**/api/conversations", async (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: "playwright-conversation",
          title: "新对话",
          messages: [],
        }),
      });
    }
    return route.continue();
  });

  await page.goto("/chat");

  await expect(
    page.getByText("开始对话，描述你想让 AgentHub 完成的任务。"),
  ).toBeVisible();
  await expect(page.getByPlaceholder("输入消息，Enter 发送")).toBeEnabled();
});

test("authenticated tools page renders the real tool registry", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("agenthub.access_token", "playwright-e2e-token");
  });
  await page.route("**/api/tools", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          name: "query_db",
          description: "Run a single read-only SQL SELECT query.",
          parameters: { required: ["sql"] },
          timeout: 30,
          requires_approval: false,
        },
      ]),
    }),
  );

  await page.goto("/tools");

  await expect(page.getByText("工具注册表")).toBeVisible();
  await expect(page.getByText("query_db")).toBeVisible();
  await expect(page.getByText("必填参数：sql")).toBeVisible();
});

test("authenticated usage page shows tenant quota", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("agenthub.access_token", "playwright-e2e-token");
    localStorage.setItem("agenthub.onboarded", "1");
  });
  await page.route("**/api/usage", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total_executions: 1,
        total_input_tokens: 100,
        total_output_tokens: 50,
        total_tokens: 150,
        total_cost: 0.01,
        today_tokens: 150,
        today_cost: 0.01,
      }),
    }),
  );
  await page.route("**/api/quotas", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        organization_id: "org",
        monthly_token_used: 300,
        monthly_token_budget: 1000,
        monthly_cost_used_cny: 0.5,
        monthly_cost_budget_cny: 10,
        concurrent_llm_calls: 1,
        concurrent_llm_limit: 4,
        month: "2026-08",
      }),
    }),
  );

  await page.goto("/settings");
  await page.getByRole("tab", { name: "用量" }).click();

  await expect(page.getByText("预算与并发（2026-08）")).toBeVisible();
  await expect(page.getByText("本月 Tokens 预算")).toBeVisible();
  await expect(page.getByText(/300 \/ 1,?000/)).toBeVisible();
});

test("failed execution can be re-launched with the original task prefilled", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("agenthub.access_token", "playwright-e2e-token");
    localStorage.setItem("agenthub.onboarded", "1");
  });
  const execution = {
    id: "exec-failed-1",
    workflow_id: "wf-1",
    status: "failed",
    current_step_index: 0,
    checkpoint_data: null,
    user_input: "发一封测试邮件",
    final_output: null,
    error_message: "approval_mismatch: params mismatch",
    created_at: "2026-08-21T00:00:00Z",
    updated_at: "2026-08-21T00:00:00Z",
    completed_at: "2026-08-21T00:01:00Z",
    eval_score: null,
    eval_details: null,
    feedback: null,
    steps: [],
    token_usage: null,
    model_used: [],
    tool_calls: [],
  };
  await page.route("**/api/executions/exec-failed-1", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(execution),
    }),
  );
  await page.route("**/api/executions/exec-failed-1/trace", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        tool_calls: [],
        approval_mismatch_count: 1,
        cost: null,
        verify_status: null,
        model_used: [],
        side_effect_proposals: [],
        spans: [
          { span: "intent", status: "ok", latency_ms: 120, model: "deepseek", tokens: 10 },
          { span: "plan", status: "ok", latency_ms: 80, model: "deepseek", tokens: 8 },
          { span: "verify", status: "error", latency_ms: 5, error: "UNKNOWN" },
        ],
      }),
    }),
  );
  await page.route("**/api/executions/exec-failed-1/interventions", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    }),
  );
  await page.route("**/api/executions/exec-failed-1/feedback", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    }),
  );
  await page.route("**/api/conversations", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: "rerun-conversation",
          title: "新对话",
          messages: [],
        }),
      });
    }
    return route.continue();
  });

  await page.goto("/executions/exec-failed-1");

  await expect(page.getByText("执行失败")).toBeVisible();
  await expect(page.getByText("approval_mismatch: params mismatch")).toBeVisible();
  await expect(page.getByText("Span 时间线")).toBeVisible();
  await expect(page.getByText("intent")).toBeVisible();
  await expect(page.getByText("UNKNOWN")).toBeVisible();
  await page.getByRole("button", { name: "重新发起" }).click();

  await expect(page).toHaveURL(/\/chat\?draft=/);
  await expect(
    page.getByPlaceholder("输入消息，Enter 发送"),
  ).toHaveValue("发一封测试邮件");
});
