import { describe, expect, it, vi } from "vitest";

import { STATUS_META, timeAgo, truncate } from "@/lib/format";

describe("format utilities", () => {
  it("defines metadata for every execution status", () => {
    expect(Object.keys(STATUS_META).sort()).toEqual(
      [
        "pending",
        "running",
        "waiting_for_approval",
        "completed",
        "failed",
        "rolled_back",
      ].sort(),
    );
  });

  it("truncates long values with an ellipsis", () => {
    expect(truncate("short", 10)).toBe("short");
    expect(truncate("1234567890abc", 10)).toBe("1234567890…");
  });

  it("returns human-readable relative time", () => {
    const now = Date.now();
    vi.spyOn(Date, "now").mockReturnValue(now);

    expect(timeAgo(new Date(now - 1000).toISOString())).toBe("刚刚");
    expect(timeAgo(new Date(now - 2 * 60 * 1000).toISOString())).toBe(
      "2 分钟前",
    );
    expect(timeAgo(new Date(now - 2 * 60 * 60 * 1000).toISOString())).toBe(
      "2 小时前",
    );
    expect(timeAgo(new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString())).toBe(
      "2 天前",
    );
  });
});
