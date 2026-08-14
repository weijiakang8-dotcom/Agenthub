import { useEffect, useState } from "react";
import { BellRing } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type AlertEvent } from "@/lib/api";

const severityClass: Record<string, string> = {
  critical: "bg-red-100 text-red-700",
  warning: "bg-amber-100 text-amber-700",
  info: "bg-blue-100 text-blue-700",
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
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">告警中心</h2>
        <p className="text-sm text-muted-foreground">系统健康与主动告警</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="shadow-sm">
          <CardHeader><CardTitle className="text-sm text-muted-foreground">活跃告警</CardTitle></CardHeader>
          <CardContent className="text-3xl font-semibold text-red-600">{stats.active}</CardContent>
        </Card>
        <Card className="shadow-sm">
          <CardHeader><CardTitle className="text-sm text-muted-foreground">历史总数</CardTitle></CardHeader>
          <CardContent className="text-3xl font-semibold">{stats.total}</CardContent>
        </Card>
        <Card className="shadow-sm">
          <CardHeader><CardTitle className="text-sm text-muted-foreground">已解决</CardTitle></CardHeader>
          <CardContent className="text-3xl font-semibold text-emerald-600">{stats.resolved}</CardContent>
        </Card>
      </div>

      <Card className="shadow-sm">
        <CardHeader><CardTitle className="text-base">告警列表</CardTitle></CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-32 w-full" />
          ) : alerts.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
              <BellRing className="h-6 w-6" />
              暂无告警
            </div>
          ) : (
            <div className="space-y-2">
              {alerts.map((a) => (
                <div key={a.id} className="flex items-center justify-between gap-3 border-b py-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge className={severityClass[a.severity]}>{a.severity}</Badge>
                      <Badge variant="outline">{a.status}</Badge>
                    </div>
                    <p className="mt-1 truncate text-sm">{a.message}</p>
                    <p className="text-xs text-muted-foreground">{a.triggered_at}</p>
                  </div>
                  {a.status === "active" && (
                    <Button size="sm" variant="outline" onClick={async () => { await api.resolveAlert(a.id); load(); }}>
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
