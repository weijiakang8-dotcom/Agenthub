import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, getAccessToken, setAccessToken } from "@/lib/api";

describe("api client", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("persists and clears the access token", () => {
    expect(getAccessToken()).toBeNull();
    setAccessToken("token-123");
    expect(getAccessToken()).toBe("token-123");
    setAccessToken(null);
    expect(getAccessToken()).toBeNull();
  });

  it("attaches the bearer token and parses JSON responses", async () => {
    setAccessToken("token-123");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([{ id: "1" }]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await api.listModels();

    expect(result).toEqual([{ id: "1" }]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/models",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer token-123",
        }),
      }),
    );
  });

  it("turns backend detail into a useful error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "模型不存在" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(api.listModels()).rejects.toThrow("模型不存在");
  });
});
