import { useEffect, useState } from "react";
import { Activity, BarChart3, Coins, Cpu } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type UsageSummary } from "@/lib/api";

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
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getUsage()
      .then(setUsage)
      .catch((err) => toast.error(String(err)))
      .finally(() => setLoading(false));
  }, []);

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
    </div>
  );
}
