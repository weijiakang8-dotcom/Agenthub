import { describe, expect, it } from "vitest";

import { getStoredTheme, storeTheme, type Theme } from "./theme";

describe("theme", () => {
  it("defaults to dark when nothing stored", () => {
    localStorage.removeItem("agenthub.theme");
    expect(getStoredTheme()).toBe("dark");
  });

  it("persists and reads light preference", () => {
    storeTheme("light" as Theme);
    expect(getStoredTheme()).toBe("light");
    storeTheme("dark" as Theme);
    expect(getStoredTheme()).toBe("dark");
  });
});
