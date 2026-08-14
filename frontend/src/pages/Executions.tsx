import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Inbox, Plus } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type Execution,
  type ExecutionStatus,
  type Workflow,
} from "@/lib/api";
import { STATUS_META, timeAgo, truncate } from "@/lib/format";

type TabKey = "all" | "running" | "waiting_for_approval" | "completed" | "failed";

const TABS: { value: TabKey; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "running", label: "运行中" },
  { value: "waiting_for_approval", label: "待审核" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
];

export default function Executions() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabKey>("all");
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [workflowId, setWorkflowId] = useState("");
  const [userInput, setUserInput] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const status = tab === "all" ? undefined : (tab as ExecutionStatus);
      setExecutions(await api.listExecutions(status));
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.listWorkflows().then(setWorkflows).catch(() => undefined);
  }, []);

  async function submit() {
    if (!workflowId || !userInput.trim()) return;
    setSubmitting(true);
    try {
      const res = await api.createExecution(workflowId, userInput.trim());
      toast.success("执行已创建");
      navigate(`/executions/${res.execution_id}`);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">执行记录</h2>
          <p className="text-sm text-muted-foreground">
            追踪所有 AI 工作流的运行状态
          </p>
        </div>
        <Button
          onClick={() => setDialogOpen(true)}
          className="bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700"
        >
          <Plus className="mr-2 h-4 w-4" />
          新建执行
        </Button>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : executions.length === 0 ? (
        <Card className="flex flex-col items-center justify-center gap-3 py-16 text-center shadow-sm">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
            <Inbox className="h-6 w-6 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground">
            还没有执行记录，点击上方按钮开始你的第一个 AI 工作流
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {executions.map((e) => {
            const meta = STATUS_META[e.status];
            return (
              <Card
                key={e.id}
                className="cursor-pointer p-5 shadow-sm transition-all duration-200 hover:shadow-md"
                onClick={() => navigate(`/executions/${e.id}`)}
              >
                <div className="flex items-center justify-between gap-4">
                  <div className="flex min-w-0 items-center gap-3">
                    <Badge variant="outline" className="font-mono">
                      {e.id.slice(0, 8)}
                    </Badge>
                    <Badge className={meta.className}>
                      <span
                        className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${meta.dot}`}
                      />
                      {meta.label}
                    </Badge>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={(ev) => {
                      ev.stopPropagation();
                      navigate(`/executions/${e.id}`);
                    }}
                  >
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </div>
                <p className="mt-3 text-sm font-medium">
                  {truncate(e.user_input || "（无输入）")}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {timeAgo(e.created_at)}
                </p>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建执行</DialogTitle>
            <DialogDescription>选择工作流并输入你的指令</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>工作流</Label>
              <Select value={workflowId} onValueChange={setWorkflowId}>
                <SelectTrigger>
                  <SelectValue placeholder="选择一个工作流" />
                </SelectTrigger>
                <SelectContent>
                  {workflows.map((w) => (
                    <SelectItem key={w.id} value={w.id}>
                      {w.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>用户指令</Label>
              <Textarea
                value={userInput}
                onChange={(e) => setUserInput(e.target.value)}
                placeholder="例如：请调研 LangGraph 的最新进展"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button
              onClick={submit}
              disabled={submitting || !workflowId || !userInput.trim()}
            >
              {submitting ? "创建中…" : "启动执行"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
