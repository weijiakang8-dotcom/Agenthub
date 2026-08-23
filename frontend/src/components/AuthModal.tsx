import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Eye, EyeOff } from "lucide-react";

import { BrandLogo } from "@/components/brand/BrandLogo";
import { ApiError, auth, setAccessToken, setRefreshToken } from "@/lib/api";
import {
  passwordMismatchError,
  passwordTooShortError,
} from "@/lib/authValidation";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type AuthMode = "login" | "register" | "forgot";
type ForgotStep = "email" | "code" | "password";

const AUTH_ERROR_MESSAGES: Record<string, string> = {
  AUTH_001: "操作失败，请稍后再试",
  EMAIL_ALREADY_EXISTS: "邮箱已被注册，请直接登录或找回密码",
  INVALID_PASSWORD: "账号或密码错误，请检查后重试",
  INVALID_VERIFY_CODE: "验证码错误，请重新输入",
  VERIFY_CODE_EXPIRED: "验证码错误或已过期",
  USER_NOT_FOUND: "账号不存在，请检查后重试",
  PASSWORD_RESET_FAILED: "密码重置失败，请稍后再试",
  INVALID_REFRESH_TOKEN: "登录已失效，请重新登录",
  REFRESH_TOKEN_EXPIRED: "登录已过期，请重新登录",
};

function authErrorMessage(err: unknown) {
  if (err instanceof ApiError && err.code) {
    return AUTH_ERROR_MESSAGES[err.code] || err.message;
  }
  return err instanceof Error ? err.message : String(err);
}

function isValidEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export function AuthModal({
  open,
  onOpenChange,
  mode: initialMode = "login",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode?: "login" | "register";
}) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [forgotStep, setForgotStep] = useState<ForgotStep>("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [code, setCode] = useState("");
  const [countdown, setCountdown] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  useEffect(() => {
    if (open) {
      setMode(initialMode);
      setForgotStep("email");
      setCode("");
      setCountdown(0);
    }
  }, [open, initialMode]);

  useEffect(() => {
    setCode("");
    setCountdown(0);
    setForgotStep("email");
    setConfirmPassword("");
    setShowPassword(false);
    setShowConfirmPassword(false);
  }, [mode]);

  useEffect(() => {
    if (!countdown) return;
    const t = window.setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => window.clearTimeout(t);
  }, [countdown]);

  async function sendCode() {
    if (!isValidEmail(email)) {
      toast.error("请输入正确的邮箱");
      return;
    }
    setSendingCode(true);
    try {
      if (mode === "forgot") {
        await auth.forgotPassword({ email: email.trim() });
        toast.info("如果该邮箱已注册，我们会发送验证码");
        setForgotStep("code");
      } else {
        await auth.sendCode({ email: email.trim(), mode });
        toast.success("验证码已发送");
      }
      setCountdown(60);
    } catch (err) {
      toast.error(authErrorMessage(err));
    } finally {
      setSendingCode(false);
    }
  }

  async function verifyCode() {
    if (!code) {
      toast.error("请输入验证码");
      return;
    }
    setSubmitting(true);
    try {
      const res = await auth.verifyResetCode({ email: email.trim(), code });
      if (res.success) {
        setForgotStep("password");
      } else {
        toast.error(res.message || "验证码错误或已过期");
      }
    } catch (err) {
      toast.error(authErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function resetPassword() {
    if (password.length < 8) {
      toast.error("密码长度不足，请输入至少8位密码");
      return;
    }
    if (password !== confirmPassword) {
      toast.error("两次输入的密码不一致");
      return;
    }
    setSubmitting(true);
    try {
      await auth.resetPassword({
        email: email.trim(),
        code,
        new_password: password,
      });
      toast.success("密码修改成功，请重新登录");
      setMode("login");
      setPassword("");
      setConfirmPassword("");
      setCode("");
      setCountdown(0);
      setForgotStep("email");
      onOpenChange(false);
    } catch (err) {
      toast.error(authErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function submit() {
    if (!isValidEmail(email)) {
      toast.error("请输入正确的邮箱");
      return;
    }
    if (mode === "register") {
      const shortError = passwordTooShortError(password);
      if (shortError) {
        toast.error(shortError);
        return;
      }
      const mismatch = passwordMismatchError(password, confirmPassword);
      if (mismatch) {
        toast.error(mismatch);
        return;
      }
    }
    setSubmitting(true);
    try {
      const normalizedEmail = email.trim();
      const res =
        mode === "login"
          ? await auth.login({ email: normalizedEmail, password })
          : await auth.register({
              email: normalizedEmail,
              password,
              full_name: fullName,
              code,
            });
      setAccessToken(res.access_token);
      setRefreshToken(res.refresh_token);
      toast.success(mode === "login" ? "登录成功" : "注册成功");
      onOpenChange(false);
      window.location.reload();
    } catch (err) {
      toast.error(authErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="surface-isolated overflow-hidden border-border/80 shadow-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BrandLogo size="sm" showWordmark={false} />
            <span>
              {mode === "login"
                ? "登录 AgentHub"
                : mode === "register"
                  ? "注册 AgentHub"
                  : "找回密码"}
            </span>
          </DialogTitle>
        </DialogHeader>

        {mode === "forgot" ? (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (forgotStep === "email") sendCode();
              else if (forgotStep === "code") verifyCode();
              else resetPassword();
            }}
          >
            {forgotStep === "email" && (
              <>
                <div className="space-y-2">
                  <Label>注册邮箱</Label>
                  <Input
                    autoFocus
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="请输入注册邮箱"
                  />
                </div>
                <Button
                  type="submit"
                  className="w-full"
                  disabled={sendingCode || countdown > 0}
                >
                  {countdown > 0
                    ? `${countdown}s`
                    : sendingCode
                      ? "发送中…"
                      : "发送验证码"}
                </Button>
              </>
            )}

            {forgotStep === "code" && (
              <>
                <p className="text-sm text-muted-foreground">
                  如果该邮箱已注册，验证码将发送至 {email}
                </p>
                <div className="space-y-2">
                  <Label>验证码</Label>
                  <Input
                    autoFocus
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="6 位数字验证码"
                  />
                </div>
                <Button type="submit" className="w-full" disabled={submitting}>
                  {submitting ? "验证中…" : "验证验证码"}
                </Button>
              </>
            )}

            {forgotStep === "password" && (
              <>
                <div className="space-y-2">
                  <Label>新密码</Label>
                  <Input
                    autoFocus
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="至少 8 位"
                  />
                </div>
                <div className="space-y-2">
                  <Label>确认新密码</Label>
                  <Input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="再次输入新密码"
                  />
                </div>
                <Button type="submit" className="w-full" disabled={submitting}>
                  {submitting ? "提交中…" : "重置密码"}
                </Button>
              </>
            )}

            <button
              type="button"
              className="w-full text-center text-sm text-muted-foreground underline-offset-4 hover:underline"
              onClick={() => setMode("login")}
            >
              返回登录
            </button>
          </form>
        ) : (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            {mode === "register" && (
              <div className="space-y-2">
                <Label>姓名</Label>
                <Input
                  autoFocus={mode === "register"}
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>
            )}
            <div className="space-y-2">
              <Label>邮箱</Label>
              <Input
                autoFocus={mode === "login"}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </div>
            <div className="space-y-2">
              <Label>密码</Label>
              <div className="relative">
                <Input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pr-9"
                />
                <Hint label={showPassword ? "隐藏密码" : "显示密码"}>
                  <button
                    type="button"
                    aria-label={showPassword ? "隐藏密码" : "显示密码"}
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </Hint>
              </div>
            </div>
            {mode === "register" && (
              <>
                <div className="space-y-2">
                  <Label>确认密码</Label>
                  <div className="relative">
                    <Input
                      type={showConfirmPassword ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="pr-9"
                    />
                    <Hint label={showConfirmPassword ? "隐藏密码" : "显示密码"}>
                      <button
                        type="button"
                        aria-label={
                          showConfirmPassword ? "隐藏密码" : "显示密码"
                        }
                        onClick={() => setShowConfirmPassword((v) => !v)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
                      >
                        {showConfirmPassword ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    </Hint>
                  </div>
                  {passwordMismatchError(password, confirmPassword) && (
                    <p className="text-xs text-red-600">两次输入的密码不一致</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label>邮箱验证码</Label>
                  <div className="flex gap-2">
                    <Input
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      placeholder="6 位数字验证码"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={sendCode}
                      disabled={countdown > 0 || sendingCode}
                    >
                      {countdown > 0
                        ? `${countdown}s`
                        : sendingCode
                          ? "发送中…"
                          : "获取验证码"}
                    </Button>
                  </div>
                </div>
              </>
            )}
            <Button
              type="submit"
              className="w-full"
              disabled={
                submitting ||
                (mode === "register" &&
                  Boolean(passwordMismatchError(password, confirmPassword)))
              }
            >
              {submitting ? "提交中…" : mode === "login" ? "登录" : "注册"}
            </Button>

            {mode === "login" && (
              <button
                type="button"
                className="w-full text-center text-sm text-muted-foreground underline-offset-4 hover:underline"
                onClick={() => setMode("forgot")}
              >
                忘记密码？
              </button>
            )}

            <button
              type="button"
              className="w-full text-center text-sm text-muted-foreground underline-offset-4 hover:underline"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
            >
              {mode === "login" ? "没有账号？注册" : "已有账号？登录"}
            </button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
