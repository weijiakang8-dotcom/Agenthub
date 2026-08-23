import { useEffect, useState } from "react";
import { BarChart3 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type BenchmarkReport, type Execution } from "@/lib/api";
import { cn } from "@/lib/utils";

const binColor: Record<string, string> = {
  "<5": "bg-agent-failed/60",
  "5-6": "bg-agent-waiting/70",
  "7-8": "bg-agent-running/70",
  "9-10": "bg-agent-completed/70",
};

export default function Quality() {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [benchmark, setBenchmark] = useState<BenchmarkReport | null>(null);
  const [benchmarkMissing, setBenchmarkMissing] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listExecutions()
      .then(setExecutions)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    api
      .getBenchmarkReport()
      .then(setBenchmark)
      .catch(() => setBenchmarkMissing(true));
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
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
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

      {benchmark ? (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="type-h3">
              任务级评测（Phase 1B · {benchmark.runs ?? "—"} runs）
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-xs">
                <thead>
                  <tr className="border-b border-border/60 text-left text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">臂</th>
                    <th className="py-2 pr-3 font-medium">SSR=业务完成率</th>
                    <th className="py-2 pr-3 font-medium">安全守住率 SOR</th>
                    <th className="py-2 pr-3 font-medium">不安全副作用率</th>
                    <th className="py-2 pr-3 font-medium">拦截率 GCR</th>
                    <th className="py-2 pr-3 font-medium">工具准确率</th>
                    <th className="py-2 pr-3 font-medium">参数准确率</th>
                    <th className="py-2 pr-3 font-medium">Cost/SS(¥)</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(benchmark.metrics_per_arm ?? {}).map(
                    ([arm, m]) => (
                      <tr key={arm} className="border-b border-border/40">
                        <td className="py-2 pr-3 font-medium">{arm}</td>
                        <td className="py-2 pr-3">
                          {m.ssr_bcr ?? "—"}%
                          {m.ssr_bcr_ci95
                            ? ` [${m.ssr_bcr_ci95[0]}, ${m.ssr_bcr_ci95[1]}]`
                            : ""}
                        </td>
                        <td className="py-2 pr-3">{m.sor ?? "—"}%</td>
                        <td className="py-2 pr-3">{m.user ?? "—"}%</td>
                        <td className="py-2 pr-3">
                          {m.gcr == null
                            ? "N/A"
                            : `${(m.gcr * 100).toFixed(1)}%`}
                        </td>
                        <td className="py-2 pr-3">{m.tool_accuracy ?? "—"}%</td>
                        <td className="py-2 pr-3">
                          {m.param_accuracy ?? "—"}%
                        </td>
                        <td className="py-2 pr-3">
                          {m.cost_per_safe_success ?? "—"}
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
            {benchmark.evidence_chain ? (
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">
                  证据链：MODEL ERROR → LAYER → BLOCKED/ALLOWED → SIDE EFFECT →
                  SAFE/UNSAFE
                </p>
                {Object.entries(benchmark.evidence_chain).map(([arm, c]) => (
                  <p key={arm} className="text-xs">
                    Arm {arm}：决策错误 {c.decision_errors} → 被拦截 {c.blocked}{" "}
                    → 放行 {c.allowed} → 不安全副作用 {c.unsafe} → 安全收尾{" "}
                    {c.safe_outcomes}
                  </p>
                ))}
              </div>
            ) : null}
            <p className="text-xs text-muted-foreground">
              EXPLORATORY：无 seed、单一 provider、模拟副作用环境；商业结论由
              Pro/GPTLuna 裁决。
            </p>
          </CardContent>
        </Card>
      ) : benchmarkMissing ? (
        <Card className="shadow-sm">
          <CardContent className="py-6">
            <EmptyState
              title="暂无任务级评测报告"
              description="运行 Phase 1B Benchmark 生成 evaluation_report.json 后自动展示。"
            />
          </CardContent>
        </Card>
      ) : (
        <Skeleton className="h-48 w-full" />
      )}

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
