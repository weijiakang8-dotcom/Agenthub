import { useEffect, useState } from "react";
import { BellRing } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type AlertEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

const severityClass: Record<string, string> = {
  critical: "bg-danger/10 text-danger",
  warning: "bg-warning/10 text-warning",
  info: "bg-info/10 text-info",
};

export default function Alerts() {
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [stats, setStats] = useState({ total: 0, active: 0, resolved: 0 });
  const [loading, setLoading] = useState(true);

  async function load() {
    const [list, stat] = await Promise.all([api.listAlerts(), api.alertStats()]);
    setAlerts(list);
    setStats(stat);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="type-h2">告警中心</h2>
          <p className="type-body text-muted-foreground">系统健康与主动告警</p>
        </div>
        <p className="shrink-0 type-small text-muted-foreground">
          {stats.active} 活跃 · {stats.total} 总数 · {stats.resolved} 已解决
        </p>
      </div>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">告警列表</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : alerts.length === 0 ? (
            <EmptyState
              icon={BellRing}
              title="暂无告警"
              description="系统目前运行正常。"
            />
          ) : (
            <div className="divide-y">
              {alerts.map((a) => (
                <div
                  key={a.id}
                  className="flex items-center justify-between gap-3 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs font-medium",
                          severityClass[a.severity],
                        )}
                      >
                        {a.severity}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {a.status}
                      </span>
                    </div>
                    <p className="mt-1 truncate text-sm">{a.message}</p>
                    <p className="text-xs text-muted-foreground">
                      {a.triggered_at}
                    </p>
                  </div>
                  {a.status === "active" && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={async () => {
                        await api.resolveAlert(a.id);
                        load();
                      }}
                    >
                      解决
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
