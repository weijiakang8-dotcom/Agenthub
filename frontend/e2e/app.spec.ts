import { expect, test } from "@playwright/test";

test("unauthenticated landing page renders hero and CTAs", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("让 Agent 不再是固定岗位")).toBeVisible();
  await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
  await expect(page.getByRole("button", { name: "注册" })).toBeVisible();
  await expect(page.getByRole("button", { name: "用户反馈" })).toBeVisible();
});

test("login button opens the authentication dialog", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "登录" }).click();

  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "登录 AgentHub" }),
  ).toBeVisible();
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

test("assistant replies render polished Markdown and framed code", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("agenthub.access_token", "playwright-e2e-token");
    localStorage.setItem("agenthub.onboarded", "1");
  });
  await page.route("**/api/conversations/markdown-preview", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "markdown-preview",
        messages: [
          { role: "user", content: "写一段代码" },
          {
            role: "assistant",
            content:
              "## 示例实现\n\n下面是标准代码：\n\n```typescript\nconst answer = 42;\n```\n\n- 清晰\n- 可复制",
          },
        ],
      }),
    }),
  );

  await page.goto("/chat?id=markdown-preview");

  await expect(page.getByRole("heading", { name: "示例实现" })).toBeVisible();
  await expect(page.locator(".chat-code-block")).toContainText(
    "const answer = 42;",
  );
  await expect(page.getByRole("button", { name: "复制代码" })).toBeVisible();
  await expect(page.locator(".assistant-markdown li")).toHaveCount(2);
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
  await page.route("**/api/quotas", (route) => {
    const body = {
      organization_id: "org",
      monthly_token_used: 300,
      monthly_token_budget: route.request().method() === "PUT" ? 2000 : 1000,
      monthly_cost_used_cny: 0.5,
      monthly_cost_budget_cny: 10,
      concurrent_llm_calls: 1,
      concurrent_llm_limit: 4,
      month: "2026-08",
    };
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  await page.goto("/settings");
  await page.getByRole("tab", { name: "用量" }).click();

  await expect(page.getByText("预算与并发（2026-08）")).toBeVisible();
  await expect(page.getByText("本月 Tokens 预算")).toBeVisible();
  await expect(page.getByText(/300 \/ 1,?000/)).toBeVisible();
  await page.getByRole("button", { name: "保存配额" }).click();
  await expect(page.getByText("配额已更新")).toBeVisible();
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
          {
            span: "intent",
            status: "ok",
            latency_ms: 120,
            model: "deepseek",
            tokens: 10,
          },
          {
            span: "plan",
            status: "ok",
            latency_ms: 80,
            model: "deepseek",
            tokens: 8,
          },
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
  await expect(
    page.getByText("approval_mismatch: params mismatch"),
  ).toBeVisible();
  await expect(page.getByText("Span 时间线")).toBeVisible();
  await expect(page.getByText("intent")).toBeVisible();
  await expect(page.getByText("UNKNOWN")).toBeVisible();
  await page.getByRole("button", { name: "重新发起" }).click();

  await expect(page).toHaveURL(/\/chat\?draft=/);
  await expect(page.getByPlaceholder("输入消息，Enter 发送")).toHaveValue(
    "发一封测试邮件",
  );
});

test("api key can be rotated from settings", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("agenthub.access_token", "playwright-e2e-token");
    localStorage.setItem("agenthub.onboarded", "1");
  });
  const original = {
    id: "key-1",
    provider: "deepseek",
    model: "deepseek-chat",
    base_url: "https://api.deepseek.com/v1",
    api_key_masked: "****1234",
    is_active: true,
    created_at: "2026-08-21T00:00:00Z",
  };
  let rotated = false;
  await page.route("**/api/user-api-keys", async (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          rotated ? { ...original, api_key_masked: "****9999" } : original,
        ]),
      });
    }
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...original, api_key_masked: "****9999" }),
      });
    }
    return route.continue();
  });
  await page.route("**/api/user-api-keys/key-1/rotate", (route) => {
    rotated = true;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...original, api_key_masked: "****9999" }),
    });
  });
  page.on("dialog", (dialog) => dialog.accept("sk-new-9999"));

  await page.goto("/settings");
  await page.getByRole("tab", { name: "我的密钥" }).click();

  await expect(page.getByText("****1234")).toBeVisible();
  await page.getByRole("button", { name: "轮换" }).click();
  await expect(page.getByText("****9999")).toBeVisible();
  await expect(page.getByText("API Key 已轮换")).toBeVisible();
});

test("user discovers, tests and saves an OpenAI-compatible model", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("agenthub.access_token", "playwright-e2e-token");
    localStorage.setItem("agenthub.onboarded", "1");
  });
  let saved = false;
  let testedBaseUrl = "";
  let savedBaseUrl = "";
  const savedKey = {
    id: "key-user-provider",
    provider: "openai-compatible",
    api_mode: "chat_completions",
    model: "gpt-5.6-sol",
    base_url: "https://llm.example.com/v1",
    api_key_masked: "****55a9",
    is_active: true,
    created_at: "2026-08-23T00:00:00Z",
  };
  await page.route("**/api/models", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/user-api-keys/discover-models", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        base_url: "https://llm.example.com/v1",
        models: [
          "gpt-5.4",
          "gpt-5.5",
          "gpt-5.6-luna",
          "gpt-5.6-sol",
          "gpt-5.6-terra",
          "gpt-image-2",
        ],
        chat_models: [
          "gpt-5.4",
          "gpt-5.5",
          "gpt-5.6-luna",
          "gpt-5.6-sol",
          "gpt-5.6-terra",
        ],
        api_mode: "chat_completions",
      }),
    }),
  );
  await page.route("**/api/user-api-keys/test-connection", async (route) => {
    testedBaseUrl = (await route.request().postDataJSON()).base_url;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        model: "gpt-5.6-sol",
        preview: "OK",
        api_mode: "chat_completions",
      }),
    });
  });
  await page.route("**/api/user-api-keys", async (route) => {
    if (route.request().method() === "POST") {
      saved = true;
      savedBaseUrl = (await route.request().postDataJSON()).base_url;
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(savedKey),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(saved ? [savedKey] : []),
    });
  });

  await page.goto("/settings");
  await page.getByRole("tab", { name: "我的密钥" }).click();
  await page.locator("#key-base-url").fill("https://llm.example.com");
  await page.locator("#key-secret").fill("sk-user-test");
  await page.getByRole("button", { name: "检测可用模型" }).click();

  await expect(page.locator("#key-base-url")).toHaveValue(
    "https://llm.example.com/v1",
  );
  await expect(page.locator("#key-model")).toHaveValue("gpt-5.6-sol");
  await page.getByRole("button", { name: "测试连接" }).click();
  await expect(
    page.getByText("gpt-5.6-sol 连接成功 · OK", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "保存已验证模型" }).click();

  expect(testedBaseUrl).toBe("https://llm.example.com/v1");
  expect(savedBaseUrl).toBe("https://llm.example.com/v1");
  await expect(page.getByText("****55a9")).toBeVisible();
  await expect(
    page.getByText("模型连接已验证，API Key 已加密保存"),
  ).toBeVisible();
});
