import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Inbox, Sparkles } from "lucide-react";

import { CreateExecutionDialog } from "@/components/CreateExecutionDialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { Textarea } from "@/components/ui/textarea";
import { api, type Execution } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export default function Dashboard() {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);

  useEffect(() => {
    api
      .listExecutions()
      .then(setExecutions)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto w-full max-w-3xl space-y-10">
      <section className="space-y-3 pt-2">
        <h1 className="type-h2">欢迎回来</h1>
        <p className="type-body text-muted-foreground">
          描述一个目标，AgentHub 会编排多个智能体协作完成。
        </p>
      </section>

      <Card className="p-2">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (draft.trim()) setDialogOpen(true);
          }}
        >
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="例如：调研 LangGraph 的最新进展，并生成一份执行摘要…"
            rows={4}
            className="min-h-24 resize-none border-0 bg-transparent px-3 py-2 shadow-none focus-visible:ring-0"
          />
          <div className="flex items-center justify-between gap-3 px-2 pb-1">
            <span className="type-caption text-muted-foreground">
              回车后选择工作流并启动
            </span>
            <Button type="submit" disabled={!draft.trim()}>
              <Sparkles className="h-4 w-4" />
              开始执行
            </Button>
          </div>
        </form>
      </Card>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="type-h3">最近执行</h2>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/executions">查看全部</Link>
          </Button>
        </div>

        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : executions.length === 0 ? (
          <EmptyState
            icon={Inbox}
            title="还没有执行记录"
            description="在上方输入任务，开始你的第一个 AI 工作流。"
          />
        ) : (
          <div className="divide-y rounded-lg border bg-card">
            {executions.slice(0, 8).map((e) => (
              <Link
                key={e.id}
                to={`/executions/${e.id}`}
                className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-muted/50"
              >
                <StatusBadge status={e.status} />
                <span className="min-w-0 flex-1 truncate text-sm">
                  {e.user_input || "（无输入）"}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {timeAgo(e.created_at)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <CreateExecutionDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        defaultInput={draft}
      />
    </div>
  );
}
