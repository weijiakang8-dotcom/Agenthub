import { useEffect, useState } from "react";
import { Activity, BarChart3, Coins, Cpu } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type QuotaSummary, type UsageSummary } from "@/lib/api";

const emptyUsage: UsageSummary = {
  total_executions: 0,
  total_input_tokens: 0,
  total_output_tokens: 0,
  total_tokens: 0,
  total_cost: 0,
  today_tokens: 0,
  today_cost: 0,
};

export default function UsagePanel() {
  const [usage, setUsage] = useState<UsageSummary>(emptyUsage);
  const [quota, setQuota] = useState<QuotaSummary | null>(null);
  const [tokenBudget, setTokenBudget] = useState("");
  const [costBudget, setCostBudget] = useState("");
  const [concurrentLimit, setConcurrentLimit] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getUsage()
      .then(setUsage)
      .then(() => api.getQuota())
      .then((q) => {
        setQuota(q);
        setTokenBudget(String(q.monthly_token_budget));
        setCostBudget(String(q.monthly_cost_budget_cny));
        setConcurrentLimit(String(q.concurrent_llm_limit));
      })
      .catch((err) => toast.error(String(err)))
      .finally(() => setLoading(false));
  }, []);

  async function saveQuota() {
    try {
      const updated = await api.updateQuota({
        monthly_token_budget: Number(tokenBudget) || 0,
        monthly_cost_budget_cny: Number(costBudget) || 0,
        concurrent_llm_limit: Number(concurrentLimit) || 0,
      });
      setQuota(updated);
      toast.success("配额已更新");
    } catch (err) {
      toast.error(String(err));
    }
  }

  const quotaRows = quota
    ? [
        [
          "本月 Tokens 预算",
          quota.monthly_token_budget > 0
            ? `${quota.monthly_token_used.toLocaleString()} / ${quota.monthly_token_budget.toLocaleString()}`
            : `${quota.monthly_token_used.toLocaleString()}（未限制）`,
        ],
        [
          "本月成本预算",
          quota.monthly_cost_budget_cny > 0
            ? `¥${(quota.monthly_cost_used_cny ?? 0).toFixed(4)} / ¥${quota.monthly_cost_budget_cny.toFixed(2)}`
            : `¥${(quota.monthly_cost_used_cny ?? 0).toFixed(4)}（未限制）`,
        ],
        [
          "并发模型调用",
          quota.concurrent_llm_limit > 0
            ? `${quota.concurrent_llm_calls} / ${quota.concurrent_llm_limit}`
            : `${quota.concurrent_llm_calls}（未限制）`,
        ],
      ]
    : [];

  const stats = [
    {
      label: "执行总数",
      value: usage.total_executions.toLocaleString(),
      icon: Activity,
    },
    {
      label: "累计 Tokens",
      value: usage.total_tokens.toLocaleString(),
      icon: Cpu,
    },
    {
      label: "今日 Tokens",
      value: usage.today_tokens.toLocaleString(),
      icon: BarChart3,
    },
    {
      label: "累计成本",
      value: `$${usage.total_cost.toFixed(4)}`,
      icon: Coins,
    },
  ];

  return (
    <div className="space-y-5">
      {loading ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {stats.map(({ label, value, icon: Icon }) => (
            <Card key={label} className="shadow-sm">
              <CardContent className="flex items-center justify-between p-5">
                <div>
                  <p className="text-sm text-muted-foreground">{label}</p>
                  <p className="mt-2 text-2xl font-semibold tracking-tight">
                    {value}
                  </p>
                </div>
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                  <Icon className="h-5 w-5 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">用量明细</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="divide-y">
            {[
              ["输入 Tokens", usage.total_input_tokens.toLocaleString()],
              ["输出 Tokens", usage.total_output_tokens.toLocaleString()],
              ["今日成本", `$${usage.today_cost.toFixed(4)}`],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex items-center justify-between py-3"
              >
                <span className="text-sm text-muted-foreground">{label}</span>
                <span className="text-sm font-medium">{value}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {quota && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="type-h3">
              预算与并发（{quota.month}）
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="divide-y">
              {quotaRows.map(([label, value]) => (
                <div
                  key={label}
                  className="flex items-center justify-between py-3"
                >
                  <span className="text-sm text-muted-foreground">{label}</span>
                  <span className="text-sm font-medium">{value}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">
                  Token 预算
                </Label>
                <Input
                  type="number"
                  min={0}
                  value={tokenBudget}
                  onChange={(e) => setTokenBudget(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">
                  成本预算（¥）
                </Label>
                <Input
                  type="number"
                  min={0}
                  step="0.01"
                  value={costBudget}
                  onChange={(e) => setCostBudget(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">
                  并发模型调用
                </Label>
                <Input
                  type="number"
                  min={0}
                  value={concurrentLimit}
                  onChange={(e) => setConcurrentLimit(e.target.value)}
                />
              </div>
            </div>
            <Button size="sm" className="mt-4" onClick={saveQuota}>
              保存配额
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
