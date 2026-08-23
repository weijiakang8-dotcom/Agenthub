import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  api,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "@/lib/api";

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

  it("persists and clears the refresh token", () => {
    expect(getRefreshToken()).toBeNull();
    setRefreshToken("refresh-123");
    expect(getRefreshToken()).toBe("refresh-123");
    setRefreshToken(null);
    expect(getRefreshToken()).toBeNull();
  });

  it("clearTokens removes access and refresh tokens", () => {
    setAccessToken("token-123");
    setRefreshToken("refresh-123");
    clearTokens();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
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
    const request = fetchMock.mock.calls[0]?.[1];
    expect(new Headers(request?.headers).has("X-API-Key")).toBe(false);
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

  it("refreshes the access token and retries on 401", async () => {
    setAccessToken("expired-access");
    setRefreshToken("refresh-token");

    const responses = [
      new Response(
        JSON.stringify({ detail: "Invalid or missing authentication" }),
        {
          status: 401,
        },
      ),
      new Response(JSON.stringify({ access_token: "new-access" }), {
        status: 200,
      }),
      new Response(JSON.stringify([{ id: "1" }]), { status: 200 }),
    ];

    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => responses.shift()!);

    const result = await api.listModels();

    expect(result).toEqual([{ id: "1" }]);
    expect(getAccessToken()).toBe("new-access");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("logs out when refresh fails", async () => {
    setAccessToken("expired-access");
    setRefreshToken("bad-refresh");

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "刷新令牌无效" }), {
        status: 401,
      }),
    );

    await expect(api.listModels()).rejects.toThrow("登录已过期，请重新登录");
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
});
