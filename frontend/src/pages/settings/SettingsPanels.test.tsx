import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  api: {
    listModels: vi.fn().mockResolvedValue([]),
  },
}));

import Settings from "@/pages/Settings";

describe("Settings resource panels", () => {
  it("renders the models tab as the default resource panel", async () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );

    expect(screen.getByRole("tab", { name: /模型/ })).toBeInTheDocument();
    expect((await screen.findAllByText("添加模型")).length).toBeGreaterThan(0);
    expect(await screen.findByText("模型列表")).toBeInTheDocument();
  });
});
