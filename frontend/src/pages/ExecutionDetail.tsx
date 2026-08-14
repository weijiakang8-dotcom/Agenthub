import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import {
  ArrowLeft,
  Check,
  CircleDot,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  api,
  type ExecutionDetail,
  type Intervention,
  type ToolCall,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function toolIcon(tc: ToolCall) {
  if (tc.status === "success" || tc.status === "approved") {
    return <Check className="h-4 w-4 text-agent-completed" />;
  }
  if (tc.status === "failed" || tc.status === "rejected") {
    return <X className="h-4 w-4 text-agent-failed" />;
  }
  return <CircleDot className="h-4 w-4 text-agent-running" />;
}

type ActivityState = "received" | "running" | "waiting" | "done" | "error";

function activityDotClass(state: ActivityState) {
  return {
    received: "bg-muted-foreground",
    running: "bg-agent-running",
    waiting: "bg-agent-waiting",
    done: "bg-agent-completed",
    error: "bg-agent-failed",
  }[state];
}

export default function ExecutionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<ExecutionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [modifiedPlan, setModifiedPlan] = useState("");

  useEffect(() => {
    if (!id) return;
    api
      .getExecution(id)
      .then(setData)
      .catch((e) => toast.error(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!id) return;
    api.listInterventions(id).then(setInterventions).catch(() => undefined);
  }, [id]);

  const activity = useMemo(() => {
    if (!data) return [];
    const steps: { id: string; text: string; state: ActivityState }[] = [
      {
        id: "received",
        text: "收到任务指令",
        state: "received",
      },
    ];

    data.tool_calls.forEach((tc) => {
      if (tc.status === "pending") {
        steps.push({
          id: tc.id,
          text: `正在执行：${tc.tool_name}`,
          state: "running",
        });
      } else if (tc.status === "success" || tc.status === "approved") {
        steps.push({
          id: tc.id,
          text: `完成：${tc.tool_name}`,
          state: "done",
        });
      } else {
        steps.push({
          id: tc.id,
          text: `${tc.status}：${tc.tool_name}`,
          state: "error",
        });
      }
    });

    if (data.status === "waiting_for_approval") {
      steps.push({
        id: "waiting",
        text: "等待人工审批",
        state: "waiting",
      });
    } else if (data.status === "completed") {
      steps.push({ id: "finished", text: "任务已完成", state: "done" });
    } else if (data.status === "failed") {
      steps.push({ id: "finished", text: "任务失败", state: "error" });
    } else if (data.status === "running") {
      steps.push({
        id: "running",
        text: "Agent 正在思考与执行",
        state: "running",
      });
    }

    return steps;
  }, [data]);

  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [] as Node[], edges: [] as Edge[] };
    const calls = data.tool_calls;
    const nodeList: Node[] = [
      {
        id: "start",
        type: "input",
        position: { x: 0, y: 0 },
        data: { label: <div className="text-sm font-medium">开始</div> },
        className:
          "rounded-md border bg-card px-4 py-2 text-sm shadow-xs",
      },
    ];

    calls.forEach((tc, i) => {
      nodeList.push({
        id: tc.id,
        position: { x: 0, y: (i + 1) * 110 },
        data: {
          label: (
            <div className="flex items-center gap-2 text-sm">
              {toolIcon(tc)}
              {tc.tool_name}
            </div>
          ),
        },
        className: cn(
          "rounded-md border bg-card px-4 py-2 text-sm shadow-xs",
          tc.status === "pending" && "animate-pulse",
        ),
      });
    });

    nodeList.push({
      id: "end",
      type: "output",
      position: { x: 0, y: (calls.length + 1) * 110 },
      data: { label: <div className="text-sm font-medium">结束</div> },
      className: "rounded-md border bg-card px-4 py-2 text-sm shadow-xs",
    });

    const edgeList: Edge[] = [];
    for (let i = 0; i < nodeList.length - 1; i++) {
      edgeList.push({
        id: `e-${i}`,
        source: nodeList[i].id,
        target: nodeList[i + 1].id,
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed },
      });
    }

    return { nodes: nodeList, edges: edgeList };
  }, [data]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }
  if (!data) return null;

  const pendingCall = data.tool_calls.find(
    (tc) => tc.requires_approval && tc.status === "pending",
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/executions")}
          >
            <ArrowLeft className="h-4 w-4" />
            返回
          </Button>
          <StatusBadge status={data.status} />
        </div>
        {data.status === "waiting_for_approval" && (
          <Button
            size="sm"
            variant="outline"
            onClick={async () => {
              await api.resumeExecution(data.id, true);
              toast.success("已恢复执行");
              window.location.reload();
            }}
          >
            <RotateCcw className="h-4 w-4" />
            断点续跑
          </Button>
        )}
      </div>

      <Card className="shadow-sm">
        <CardContent className="space-y-2 py-4">
          <p className="type-small font-medium text-muted-foreground">
            任务指令
          </p>
          <p className="type-body">{data.user_input || "（无输入）"}</p>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="shadow-sm lg:col-span-2">
          <CardHeader>
            <CardTitle className="type-h3">活动日志</CardTitle>
          </CardHeader>
          <CardContent>
            {activity.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无活动记录</p>
            ) : (
              <div className="space-y-3">
                {activity.map((step, i) => (
                  <div key={step.id} className="flex items-start gap-3">
                    <span
                      className={cn(
                        "mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full",
                        activityDotClass(step.state),
                        (step.state === "running" || step.state === "waiting") &&
                          "animate-pulse",
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <p
                        className={cn(
                          "text-sm",
                          step.state === "received"
                            ? "text-muted-foreground"
                            : "text-foreground",
                        )}
                      >
                        {step.text}
                      </p>
                      {i === 0 && data.user_input ? (
                        <p className="mt-0.5 truncate text-xs text-muted-foreground">
                          {data.user_input}
                        </p>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <Separator className="my-4" />

            <p className="mb-2 text-xs font-medium text-muted-foreground">
              工具调用
            </p>
            {data.tool_calls.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                当前执行尚未产生工具调用记录。
              </p>
            ) : (
              <div className="space-y-2">
                {data.tool_calls.map((tc, i) => (
                  <div
                    key={tc.id}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      {toolIcon(tc)}
                      <span className="truncate">
                        {i + 1}. {tc.tool_name}
                      </span>
                    </div>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {tc.status}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {data.status === "waiting_for_approval" && (
              <div className="mt-4 space-y-3 border-t pt-4">
                <p className="text-sm text-muted-foreground">
                  Agent 想要执行：{pendingCall ? pendingCall.tool_name : "下一步计划"}
                </p>
                <textarea
                  className="w-full rounded-md border border-input bg-background p-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  rows={3}
                  value={modifiedPlan}
                  onChange={(e) => setModifiedPlan(e.target.value)}
                  placeholder="修改 Agent 的下一步计划…"
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    className="flex-1"
                    onClick={async () => {
                      await api.intervene(data.id, {
                        operator: "admin",
                        action: "approved",
                      });
                      toast.success("已按原计划执行");
                      window.location.reload();
                    }}
                  >
                    批准执行
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1"
                    onClick={async () => {
                      await api.intervene(data.id, {
                        operator: "admin",
                        action: "modified",
                        modified_plan: modifiedPlan,
                      });
                      toast.success("已按修改内容执行");
                      window.location.reload();
                    }}
                  >
                    按修改执行
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={async () => {
                      await api.intervene(data.id, {
                        operator: "admin",
                        action: "terminate",
                      });
                      toast.success("已终止任务");
                      window.location.reload();
                    }}
                  >
                    终止
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-sm lg:col-span-3">
          <CardHeader>
            <CardTitle className="type-h3">决策树</CardTitle>
          </CardHeader>
          <CardContent className="h-[480px]">
            <ReactFlow nodes={nodes} edges={edges} fitView>
              <Background />
              <Controls />
            </ReactFlow>
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">质量评分</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.eval_score !== null ? (
            <>
              <p className="text-3xl font-semibold">
                {data.eval_score.toFixed(1)}
                <span className="text-sm text-muted-foreground"> / 10</span>
              </p>
              {data.eval_details && (
                <p className="text-sm text-muted-foreground">
                  准确性 {data.eval_details.accuracy ?? "—"} · 完整性{" "}
                  {data.eval_details.completeness ?? "—"} · 逻辑性{" "}
                  {data.eval_details.logic ?? "—"}
                </p>
              )}
              {data.eval_details?.comment && (
                <p className="text-sm text-muted-foreground">
                  {data.eval_details.comment}
                </p>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              执行完成后将自动进行质量评估。
            </p>
          )}
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                await api.sendFeedback(data.id, "useful");
                toast.success("感谢反馈");
                window.location.reload();
              }}
            >
              <ThumbsUp className="h-4 w-4" />
              有用
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                await api.sendFeedback(data.id, "useless");
                toast.success("感谢反馈");
                window.location.reload();
              }}
            >
              <ThumbsDown className="h-4 w-4" />
              无用
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">人工干预记录</CardTitle>
        </CardHeader>
        <CardContent>
          {interventions.length === 0 ? (
            <EmptyState title="暂无干预记录" />
          ) : (
            <div className="space-y-3">
              {interventions.map((it) => (
                <div key={it.id} className="border-l-2 border-border pl-3">
                  <p className="text-sm font-medium">
                    {it.operator} · {it.action}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {it.created_at}
                  </p>
                  {it.modified_plan && (
                    <p className="mt-1 text-sm text-muted-foreground">
                      {it.modified_plan}
                    </p>
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
