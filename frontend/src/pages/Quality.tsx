import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Execution } from "@/lib/api";

function bin(score: number) {
  if (score >= 9) return "9-10";
  if (score >= 7) return "7-8";
  if (score >= 5) return "5-6";
  return "<5";
}

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
    { name: "5-6", count: scored.filter((e) => e.eval_score! >= 5 && e.eval_score! < 7).length },
    { name: "7-8", count: scored.filter((e) => e.eval_score! >= 7 && e.eval_score! < 9).length },
    { name: "9-10", count: scored.filter((e) => e.eval_score! >= 9).length },
  ];
  const average = scored.length
    ? (scored.reduce((s, e) => s + (e.eval_score ?? 0), 0) / scored.length).toFixed(2)
    : "—";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">质量看板</h2>
        <p className="text-sm text-muted-foreground">
          LLM-as-Judge 自动化评估与评分分布
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">平均质量分</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{average}</CardContent>
        </Card>
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">已评估执行</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{scored.length}</CardContent>
        </Card>
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">待评估</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {executions.filter((e) => e.status === "completed" && e.eval_score === null).length}
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">评分分布</CardTitle>
        </CardHeader>
        <CardContent className="h-64">
          {loading ? (
            <Skeleton className="h-full w-full" />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={distribution}>
                <XAxis dataKey="name" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                  {distribution.map((d, i) => (
                    <Cell key={i} fill={i >= 2 ? "#10b981" : i === 1 ? "#f59e0b" : "#ef4444"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">已评分执行</CardTitle>
        </CardHeader>
        <CardContent>
          {scored.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">暂无评分数据</p>
          ) : (
            <div className="space-y-2">
              {scored.slice(0, 20).map((e) => (
                <div key={e.id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="min-w-0 truncate text-muted-foreground">
                    {e.user_input || e.id.slice(0, 8)}
                  </span>
                  <Badge variant="outline">{e.eval_score?.toFixed(1)}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
