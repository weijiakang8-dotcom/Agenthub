export function passwordTooShortError(password: string): string | null {
  return password.length >= 8 ? null : "密码长度不足，请输入至少8位密码";
}

export function passwordMismatchError(
  password: string,
  confirmPassword: string,
): string | null {
  if (!confirmPassword) return null;
  return password === confirmPassword ? null : "两次输入的密码不一致";
}
