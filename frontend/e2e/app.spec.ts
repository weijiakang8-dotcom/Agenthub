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
