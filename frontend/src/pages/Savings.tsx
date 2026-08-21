import { useEffect, useState } from "react";
import { PiggyBank, Coins, TrendingDown, BarChart3 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type SavingsSummary, type TokenDashboard } from "@/lib/api";

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

export default function Savings() {
  const [savings, setSavings] = useState<SavingsSummary | null>(null);
  const [tokens, setTokens] = useState<TokenDashboard | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [savingsData, tokensData] = await Promise.all([
        api.usageSavings(),
        api.usageTokens(30),
      ]);
      setSavings(savingsData);
      setTokens(tokensData);
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <PiggyBank className="h-4 w-4" /> 本周期实际成本
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">
              ¥{((savings?.actual_cost ?? 0) / 1).toFixed(4)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Coins className="h-4 w-4" /> 全 pro 基线
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">
              ¥{((savings?.baseline_cost ?? 0) / 1).toFixed(4)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <TrendingDown className="h-4 w-4" /> 省下的钱
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold text-primary">
              ¥{((savings?.savings ?? 0) / 1).toFixed(4)}
            </p>
            <p className="text-xs text-muted-foreground">
              {savings ? `${(savings.savings_rate * 100).toFixed(0)}% 成本下降` : ""}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>省钱进度</CardTitle>
          <CardDescription>
            相比"每一步都用最强模型"的基线，动态路由为你省下的比例
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Progress value={(savings?.savings_rate ?? 0) * 100} />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>
              {formatTokens(savings?.total_tokens ?? 0)} tokens 被调度
            </span>
            <span>基线单价 ¥{savings?.max_rate ?? "—"}/1k</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            近 30 天 token 消耗（按模型）
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>模型</TableHead>
                <TableHead className="text-right">输入</TableHead>
                <TableHead className="text-right">输出</TableHead>
                <TableHead className="text-right">调用</TableHead>
                <TableHead className="text-right">成本</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(tokens?.models ?? []).map((row) => (
                <TableRow key={row.model}>
                  <TableCell>
                    <span className="font-mono text-sm">{row.model}</span>
                  </TableCell>
                  <TableCell className="text-right">
                    {formatTokens(row.input_tokens)}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatTokens(row.output_tokens)}
                  </TableCell>
                  <TableCell className="text-right">{row.calls}</TableCell>
                  <TableCell className="text-right">
                    ¥{row.cost.toFixed(4)}
                  </TableCell>
                </TableRow>
              ))}
              {!tokens?.models.length && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    本周期还没有模型调用记录——去调度中心发一个任务试试。
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          {tokens && tokens.total.calls > 0 && (
            <div className="mt-3 flex justify-end gap-3 text-sm">
              <Badge variant="secondary">
                总计 {formatTokens(tokens.total.tokens)} tokens
              </Badge>
              <Badge variant="secondary">¥{tokens.total.cost.toFixed(4)}</Badge>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button variant="outline" onClick={load}>
          刷新账单
        </Button>
      </div>
    </div>
  );
}
