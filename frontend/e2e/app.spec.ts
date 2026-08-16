import { expect, test } from "@playwright/test";

test("unauthenticated landing page renders workspace and sidebar", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.locator("main").getByRole("heading", { name: "工作区" }),
  ).toBeVisible();
  await expect(page.getByText("请先登录后再使用")).toBeVisible();
  await expect(page.getByRole("link", { name: "对话" })).toBeVisible();
  await expect(page.getByRole("link", { name: "历史记录" })).toBeVisible();
  await expect(page.getByRole("link", { name: "设置" })).toBeVisible();
});

test("login button opens the authentication dialog", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "登录 / 注册" }).click();

  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("heading", { name: "登录" })).toBeVisible();
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
