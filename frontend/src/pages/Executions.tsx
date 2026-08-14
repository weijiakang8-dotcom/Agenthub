import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Inbox, Plus } from "lucide-react";
import { toast } from "sonner";

import { CreateExecutionDialog } from "@/components/CreateExecutionDialog";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type Execution, type ExecutionStatus } from "@/lib/api";
import { timeAgo, truncate } from "@/lib/format";

type TabKey =
  | "all"
  | "running"
  | "waiting_for_approval"
  | "completed"
  | "failed";

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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="type-h2">执行记录</h2>
          <p className="type-body text-muted-foreground">
            追踪所有 AI 工作流的运行状态
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)} className="w-full sm:w-auto">
          <Plus className="h-4 w-4" />
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
        <div className="space-y-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : executions.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title="还没有执行记录"
          description="点击右上角“新建执行”开始你的第一个 AI 工作流。"
        />
      ) : (
        <div className="divide-y rounded-lg border bg-card">
          {executions.map((e) => (
            <div
              key={e.id}
              className="group flex items-center gap-4 px-4 py-3 transition-colors hover:bg-muted/50"
            >
              <StatusBadge status={e.status} className="shrink-0" />
              <button
                type="button"
                className="min-w-0 flex-1 cursor-pointer text-left"
                onClick={() => navigate(`/executions/${e.id}`)}
              >
                <p className="truncate text-sm font-medium">
                  {truncate(e.user_input || "（无输入）", 80)}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {e.id.slice(0, 8)} · {timeAgo(e.created_at)}
                </p>
              </button>
              <Button
                variant="ghost"
                size="icon"
                className="shrink-0 text-muted-foreground"
                onClick={() => navigate(`/executions/${e.id}`)}
              >
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      )}

      <CreateExecutionDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}
