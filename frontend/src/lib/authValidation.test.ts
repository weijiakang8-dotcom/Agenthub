import { describe, expect, it } from "vitest";

import { passwordMismatchError, passwordTooShortError } from "./authValidation";

describe("authValidation", () => {
  it("rejects short passwords", () => {
    expect(passwordTooShortError("1234567")).toBe(
      "密码长度不足，请输入至少8位密码",
    );
    expect(passwordTooShortError("12345678")).toBeNull();
  });

  it("detects password mismatch only when confirm is filled", () => {
    expect(passwordMismatchError("12345678", "")).toBeNull();
    expect(passwordMismatchError("12345678", "12345678")).toBeNull();
    expect(passwordMismatchError("12345678", "87654321")).toBe(
      "两次输入的密码不一致",
    );
  });
});
