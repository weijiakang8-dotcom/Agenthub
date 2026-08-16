import { useEffect, useState } from "react";
import { toast } from "sonner";

import { auth, setAccessToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function AuthModal({
  open,
  onOpenChange,
  mode: initialMode = "login",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode?: "login" | "register";
}) {
  const [mode, setMode] = useState(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [code, setCode] = useState("");
  const [countdown, setCountdown] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!countdown) return;
    const t = window.setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => window.clearTimeout(t);
  }, [countdown]);

  async function sendCode() {
    if (!email) {
      toast.error("请输入邮箱");
      return;
    }
    try {
      await auth.sendCode({ email });
      toast.success("验证码已发送");
      setCountdown(60);
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function submit() {
    setSubmitting(true);
    try {
      const res =
        mode === "login"
          ? await auth.login({ email, password, code })
          : await auth.register({ email, password, full_name: fullName, code });
      setAccessToken(res.access_token);
      toast.success(mode === "login" ? "登录成功" : "注册成功");
      onOpenChange(false);
      window.location.reload();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === "login" ? "登录" : "注册"}</DialogTitle>
        </DialogHeader>
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
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>验证码</Label>
            <div className="flex gap-2">
              <Input value={code} onChange={(e) => setCode(e.target.value)} />
              <Button
                type="button"
                variant="outline"
                onClick={sendCode}
                disabled={countdown > 0}
              >
                {countdown > 0 ? `${countdown}s` : "获取验证码"}
              </Button>
            </div>
          </div>
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "提交中…" : mode === "login" ? "登录" : "注册"}
          </Button>
          <button
            type="button"
            className="w-full text-center text-sm text-muted-foreground underline-offset-4 hover:underline"
            onClick={() => setMode(mode === "login" ? "register" : "login")}
          >
            {mode === "login" ? "没有账号？注册" : "已有账号？登录"}
          </button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
