import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  api: {
    listModels: vi.fn().mockResolvedValue([]),
    listDocuments: vi.fn().mockResolvedValue([]),
    listNotifications: vi.fn().mockResolvedValue([]),
    getUsage: vi.fn().mockResolvedValue({
      total_executions: 0,
      total_input_tokens: 0,
      total_output_tokens: 0,
      total_tokens: 0,
      total_cost: 0,
      today_tokens: 0,
      today_cost: 0,
    }),
    listEvalDatasets: vi.fn().mockResolvedValue([]),
    listEvalReports: vi.fn().mockResolvedValue([]),
    listWorkflows: vi.fn().mockResolvedValue([]),
  },
}));

import DocumentsPanel from "@/pages/settings/DocumentsPanel";
import EvalPanel from "@/pages/settings/EvalPanel";
import ModelsPanel from "@/pages/settings/ModelsPanel";
import NotificationsPanel from "@/pages/settings/NotificationsPanel";
import UsagePanel from "@/pages/settings/UsagePanel";

describe("Settings resource tabs", () => {
  it("renders the models tab", async () => {
    render(<ModelsPanel />);
    expect(await screen.findByText("模型列表")).toBeInTheDocument();
  });

  it("renders the documents tab", async () => {
    render(<DocumentsPanel />);
    expect(await screen.findByText("知识库文档")).toBeInTheDocument();
  });

  it("renders the notifications tab", async () => {
    render(<NotificationsPanel />);
    expect(await screen.findByText("通知历史")).toBeInTheDocument();
  });

  it("renders the usage tab", async () => {
    render(<UsagePanel />);
    expect(await screen.findByText("用量明细")).toBeInTheDocument();
  });

  it("renders the eval tab", async () => {
    render(<EvalPanel />);
    expect(await screen.findByText("创建评测数据集")).toBeInTheDocument();
  });
});
