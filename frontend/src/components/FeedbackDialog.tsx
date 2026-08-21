import { useState } from "react";
import { MessageSquareHeart, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getAccessToken } from "@/lib/api";

async function submitFeedback(
  content: string,
  contact: string,
): Promise<{ ok: boolean }> {
  const token = getAccessToken();
  const res = await fetch("/api/feedback", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ content, contact }),
  });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

export function FeedbackDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [content, setContent] = useState("");
  const [contact, setContact] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const reset = () => {
    setContent("");
    setContact("");
    setSubmitted(false);
  };

  async function submit() {
    if (!content.trim() || submitting) return;
    setSubmitting(true);
    try {
      await submitFeedback(content.trim(), contact.trim());
      setSubmitted(true);
    } catch {
      toast.error("提交失败，请稍后再试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        onOpenChange(value);
        if (!value) {
          // 关闭后再打开时回到填写态
          window.setTimeout(reset, 200);
        }
      }}
    >
      <DialogContent>
        {submitted ? (
          <div className="flex flex-col items-center gap-4 py-6 text-center">
            <span className="text-6xl" role="img" aria-label="感谢">
              🥰
            </span>
            <div className="space-y-1">
              <p className="text-lg font-semibold">
                感谢您的反馈，您的支持就是我的动力
              </p>
              <p className="text-sm text-muted-foreground">
                反馈已送达站主邮箱，我们会认真阅读每一条建议 ✨
              </p>
            </div>
            <Button onClick={() => onOpenChange(false)}>好的</Button>
          </div>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <MessageSquareHeart className="h-5 w-5 text-primary" />
                用户反馈
              </DialogTitle>
              <DialogDescription>
                你的每一条建议都会直达站主邮箱，帮助我们做得更好。
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <div className="space-y-1">
                <Label>反馈内容</Label>
                <Textarea
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  placeholder="说说你的想法：哪里好用、哪里要改、想要什么新功能…"
                  rows={5}
                  maxLength={2000}
                />
              </div>
              <div className="space-y-1">
                <Label>联系方式（选填）</Label>
                <Input
                  value={contact}
                  onChange={(event) => setContact(event.target.value)}
                  placeholder="邮箱 / 微信，方便我们回复你"
                  maxLength={200}
                />
              </div>
              <Button
                className="w-full"
                onClick={submit}
                disabled={submitting || !content.trim()}
              >
                <Send className="mr-1.5 h-4 w-4" />
                {submitting ? "提交中…" : "提交反馈"}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
