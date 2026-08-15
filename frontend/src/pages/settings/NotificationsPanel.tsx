import { useEffect, useState } from "react";
import { BellRing, Send } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type NotificationItem } from "@/lib/api";

const channels = ["email", "webhook", "feishu", "dingtalk", "wecom"];

export default function NotificationsPanel() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [channel, setChannel] = useState("email");
  const [template, setTemplate] = useState("alert");
  const [paramsText, setParamsText] = useState(
    JSON.stringify({ message: "AgentHub 测试通知", to: "" }, null, 2),
  );
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setItems(await api.listNotifications());
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function send() {
    let params: Record<string, unknown>;
    try {
      params = JSON.parse(paramsText || "{}");
    } catch {
      toast.error("参数必须是合法 JSON");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.testNotification({ channel, template, params });
      toast.success(
        result.status === "success"
          ? "通知发送成功"
          : `通知发送失败：${result.error || "未知错误"}`,
      );
      await load();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-5">
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">发送测试通知</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>通知渠道</Label>
              <Select value={channel} onValueChange={setChannel}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {channels.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>消息模板</Label>
              <Select value={template} onValueChange={setTemplate}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="alert">alert</SelectItem>
                  <SelectItem value="execution_completed">
                    execution_completed
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label>模板参数（JSON）</Label>
            <textarea
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
              className="min-h-28 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            />
          </div>
          <Button onClick={send} disabled={submitting}>
            <Send className="mr-2 h-4 w-4" />
            {submitting ? "发送中…" : "发送测试通知"}
          </Button>
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">通知历史</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-32 w-full" />
          ) : items.length === 0 ? (
            <EmptyState
              icon={BellRing}
              title="暂无通知记录"
              description="发送测试通知后，记录会出现在这里。"
            />
          ) : (
            <div className="divide-y">
              {items.map((n) => (
                <div
                  key={n.id}
                  className="flex items-center justify-between gap-3 py-3"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{n.channel}</span>
                      <Badge
                        variant={
                          n.status === "success" ? "default" : "destructive"
                        }
                      >
                        {n.status}
                      </Badge>
                    </div>
                    <p className="mt-1 truncate text-xs text-muted-foreground">
                      {n.template} · {new Date(n.created_at).toLocaleString()}
                    </p>
                    {n.error && (
                      <p className="mt-1 line-clamp-2 text-xs text-danger">
                        {n.error}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
