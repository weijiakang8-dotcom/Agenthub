import { useEffect, useState } from "react";
import { Wrench } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type ToolSpec } from "@/lib/api";

function requiredKeys(parameters: Record<string, unknown>): string[] {
  const required = parameters.required;
  return Array.isArray(required) ? required.map(String) : [];
}

export default function Tools() {
  const [tools, setTools] = useState<ToolSpec[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listTools()
      .then(setTools)
      .catch((err) => toast.error(String(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">工具注册表</h1>
        <p className="text-sm text-muted-foreground">
          当前运行时真实可用的工具（来自 Tool Registry，不含测试夹具）。
        </p>
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : tools.length === 0 ? (
        <EmptyState
          title="暂无工具"
          description="Tool Registry 为空，请联系管理员。"
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {tools.map((tool) => (
            <Card key={tool.name}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Wrench className="h-4 w-4 text-primary" />
                  {tool.name}
                  {tool.requires_approval && (
                    <Badge variant="secondary">需审批</Badge>
                  )}
                </CardTitle>
                <CardDescription>{tool.description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">timeout {tool.timeout}s</Badge>
                  <Badge variant="outline">副作用: {tool.requires_approval ? "是" : "否"}</Badge>
                </div>
                {requiredKeys(tool.parameters).length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    必填参数：{requiredKeys(tool.parameters).join(", ")}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
