import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Sidebar } from "@/components/layout/Sidebar";
import { setAccessToken } from "@/lib/api";
import { TooltipProvider } from "@/components/ui/tooltip";

function renderSidebar() {
  return render(
    <MemoryRouter>
      <TooltipProvider>
        <Sidebar />
      </TooltipProvider>
    </MemoryRouter>,
  );
}

describe("Sidebar", () => {
  it("shows only the conversation-first navigation entries", () => {
    renderSidebar();

    expect(screen.getByText("新建对话")).toBeInTheDocument();
    expect(screen.getByText("对话历史")).toBeInTheDocument();
    expect(screen.getByText("Skill 库")).toBeInTheDocument();
    expect(screen.getByText("模型与设置")).toBeInTheDocument();
    expect(screen.queryByText("工作区")).not.toBeInTheDocument();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });

  it("clears the access token when logging out", () => {
    setAccessToken("token-123");
    renderSidebar();

    fireEvent.click(screen.getByText("退出登录"));

    expect(localStorage.getItem("agenthub.access_token")).toBeNull();
  });
});
