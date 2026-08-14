import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Workflow } from "@/lib/api";
import { truncate } from "@/lib/format";

export default function Workflows() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listWorkflows()
      .then(setWorkflows)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">工作流</h2>
        <p className="text-sm text-muted-foreground">管理你的多智能体工作流</p>
      </div>

      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : workflows.length === 0 ? (
        <Card className="py-16 text-center text-sm text-muted-foreground shadow-sm">
          还没有工作流
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {workflows.map((w) => (
            <Card key={w.id} className="shadow-sm">
              <CardHeader>
                <CardTitle className="text-base">{w.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>{truncate(w.description || "（无描述）", 60)}</p>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{w.status}</Badge>
                  <span>{w.agent_chain.length} 个节点</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
