import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssistantMessage } from "./AssistantMessage";

describe("AssistantMessage", () => {
  it("renders structured Markdown without exposing formatting syntax", async () => {
    render(
      <AssistantMessage
        content={[
          "## 实现方案",
          "",
          "这是包含 `inline()` 的正文。",
          "",
          "- 第一项",
          "- 第二项",
          "",
          "> 关键说明",
          "",
          "| 项目 | 状态 |",
          "| --- | --- |",
          "| API | 正常 |",
        ].join("\n")}
      />,
    );

    expect(
      await screen.findByRole("heading", { name: "实现方案" }),
    ).toBeVisible();
    expect(screen.getByText("inline()", { selector: "code" })).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("关键说明").closest("blockquote")).not.toBeNull();
    expect(screen.getByRole("table")).toBeVisible();
  });

  it("unwraps an accidentally JSON-encoded full reply", async () => {
    render(
      <AssistantMessage content={JSON.stringify("## 正常标题\n\n正常正文")} />,
    );

    expect(
      await screen.findByRole("heading", { name: "正常标题" }),
    ).toBeVisible();
    expect(screen.getByText("正常正文")).toBeVisible();
  });

  it("frames fenced code and copies only its source", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(
      <AssistantMessage
        content={"```typescript\nconst answer: number = 42;\n```"}
      />,
    );

    expect(await screen.findByText("typescript")).toBeVisible();
    expect(document.querySelector(".chat-code-block code")).toHaveTextContent(
      "const answer: number = 42;",
    );
    fireEvent.click(screen.getByRole("button", { name: "复制代码" }));
    expect(writeText).toHaveBeenCalledWith("const answer: number = 42;");
    expect(
      await screen.findByRole("button", { name: "已复制代码" }),
    ).toBeVisible();
  });

  it("opens links in a separate protected tab", async () => {
    render(<AssistantMessage content="[OpenAI](https://openai.com)" />);

    const link = await screen.findByRole("link", { name: "OpenAI" });
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
    expect(link).toHaveAttribute("target", "_blank");
  });
});
