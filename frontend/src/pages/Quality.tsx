import { useEffect, useState } from "react";
import { BarChart3 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Execution } from "@/lib/api";
import { cn } from "@/lib/utils";

function bin(score: number) {
  if (score >= 9) return "9-10";
  if (score >= 7) return "7-8";
  if (score >= 5) return "5-6";
  return "<5";
}

const binColor: Record<string, string> = {
  "<5": "bg-agent-failed/60",
  "5-6": "bg-agent-waiting/70",
  "7-8": "bg-agent-running/70",
  "9-10": "bg-agent-completed/70",
};

export default function Quality() {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listExecutions()
      .then(setExecutions)
      .finally(() => setLoading(false));
  }, []);

  const scored = executions.filter((e) => e.eval_score !== null);
  const distribution = [
    { name: "<5", count: scored.filter((e) => e.eval_score! < 5).length },
    {
      name: "5-6",
      count: scored.filter((e) => e.eval_score! >= 5 && e.eval_score! < 7)
        .length,
    },
    {
      name: "7-8",
      count: scored.filter((e) => e.eval_score! >= 7 && e.eval_score! < 9)
        .length,
    },
    {
      name: "9-10",
      count: scored.filter((e) => e.eval_score! >= 9).length,
    },
  ];
  const maxCount = Math.max(1, ...distribution.map((d) => d.count));
  const average = scored.length
    ? (
        scored.reduce((s, e) => s + (e.eval_score ?? 0), 0) / scored.length
      ).toFixed(2)
    : "—";

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h2 className="type-h2">质量看板</h2>
          <p className="type-body text-muted-foreground">
            LLM-as-Judge 自动化评估与评分分布
          </p>
        </div>
        <p className="shrink-0 type-small text-muted-foreground">
          平均分 {average} · 已评估 {scored.length}
        </p>
      </div>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">评分分布</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            distribution.map((d) => (
              <div key={d.name} className="flex items-center gap-3">
                <span className="w-8 shrink-0 text-right text-xs text-muted-foreground">
                  {d.name}
                </span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn("h-full rounded-full", binColor[d.name])}
                    style={{ width: `${(d.count / maxCount) * 100}%` }}
                  />
                </div>
                <span className="w-6 shrink-0 text-xs text-muted-foreground">
                  {d.count}
                </span>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">已评分执行</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-24 w-full" />
          ) : scored.length === 0 ? (
            <EmptyState
              icon={BarChart3}
              title="暂无评分数据"
              description="执行完成后会由 LLM-as-Judge 自动评分。"
            />
          ) : (
            <div className="divide-y">
              {scored.slice(0, 30).map((e) => (
                <div
                  key={e.id}
                  className="flex items-center justify-between gap-3 py-2.5"
                >
                  <span className="min-w-0 truncate text-sm text-muted-foreground">
                    {e.user_input || e.id.slice(0, 8)}
                  </span>
                  <Badge variant="outline" className="shrink-0">
                    {e.eval_score?.toFixed(1)}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
