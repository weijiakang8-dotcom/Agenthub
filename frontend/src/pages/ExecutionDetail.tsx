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
  AlertTriangle,
  Check,
  CheckCircle2,
  CircleDot,
  RotateCcw,
  Star,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { Textarea } from "@/components/ui/textarea";
import { useExecutionWebSocket } from "@/hooks/useExecutionWebSocket";
import {
  api,
  type ExecutionDetail,
  type ExecutionFeedback,
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

function formatToolDuration(tc: ToolCall) {
  if (!tc.started_at || !tc.completed_at) return null;
  const ms =
    new Date(tc.completed_at).getTime() - new Date(tc.started_at).getTime();
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
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
  const [trace, setTrace] = useState<
    import("@/lib/api").Trace | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [feedbacks, setFeedbacks] = useState<ExecutionFeedback[]>([]);
  const { lastEvent } = useExecutionWebSocket(id);

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
    api
      .getTrace(id)
      .then(setTrace)
      .catch(() => setTrace(null));
  }, [id]);

  useEffect(() => {
    if (!id) return;
    api
      .listInterventions(id)
      .then(setInterventions)
      .catch(() => undefined);
  }, [id]);

  useEffect(() => {
    if (!id || !lastEvent) return;
    api
      .getExecution(id)
      .then(setData)
      .catch(() => undefined);
  }, [id, lastEvent]);

  useEffect(() => {
    if (!id) return;
    api
      .listFeedback(id)
      .then(setFeedbacks)
      .catch(() => undefined);
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
        className: "rounded-md border bg-card px-4 py-2 text-sm shadow-xs",
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
          <Hint label="返回执行记录列表">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/executions")}
            >
              <ArrowLeft className="h-4 w-4" />
              返回
            </Button>
          </Hint>
          <StatusBadge status={data.status} />
        </div>
        {data.status === "waiting_for_approval" && (
          <Hint label="按原审批继续执行该任务">
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
          </Hint>
        )}
      </div>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">执行轨迹与用量</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <span className="text-muted-foreground">
              实际模型：{data.model_used?.length ? data.model_used.join("、") : "—"}
            </span>
            <span className="text-muted-foreground">
              耗时：
              {data.completed_at
                ? `${Math.max(
                    1,
                    Math.round(
                      (new Date(data.completed_at).getTime() -
                        new Date(data.created_at).getTime()) /
                        1000,
                    ),
                  )}s`
                : "运行中"}
            </span>
          </div>

          {data.token_usage ? (
            <div className="grid gap-2 sm:grid-cols-3">
              {Object.entries(data.token_usage).map(([model, usage]) => (
                <div
                  key={model}
                  className="rounded-lg border border-border/60 p-3 text-xs"
                >
                  <p className="font-medium">{model}</p>
                  <p className="text-muted-foreground">
                    in {usage.input_tokens} · out {usage.output_tokens}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">暂无 token 明细</p>
          )}

          {data.steps?.length ? (
            <div className="space-y-1.5">
              {data.steps.map((step, index) => (
                <div
                  key={index}
                  className="flex items-center gap-2 text-xs text-muted-foreground"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                  {step.name ?? step.task_id ?? step.role ?? `步骤 ${index + 1}`}
                  {step.capability_id ? ` · ${step.capability_id}` : ""}
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">执行轨迹与可靠性</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <div className="rounded-md border border-border/60 p-2">
              <p className="text-muted-foreground">本次成本</p>
              <p className="font-medium">
                {trace?.cost != null ? `¥${Number(trace.cost).toFixed(6)}` : "—"}
              </p>
            </div>
            <div className="rounded-md border border-border/60 p-2">
              <p className="text-muted-foreground">验证状态</p>
              <p className="font-medium">
                {trace?.verify_status ?? "PASS/未验证"}
              </p>
            </div>
            <div className="rounded-md border border-border/60 p-2">
              <p className="text-muted-foreground">审批不一致</p>
              <p className="font-medium">
                {trace?.approval_mismatch_count ?? 0} 次
              </p>
            </div>
            <div className="rounded-md border border-border/60 p-2">
              <p className="text-muted-foreground">使用模型</p>
              <p className="truncate font-medium">
                {trace?.model_used?.length ? trace.model_used.join("、") : "—"}
              </p>
            </div>
          </div>

          {trace?.verify_status && (
            <div className="rounded-md border border-agent-waiting/30 bg-agent-waiting/10 px-3 py-2 text-xs text-foreground">
              本次输出未被验证器认证（{trace.verify_status}），业务结果保留但不可宣称“已验证安全”。
            </div>
          )}

          {(trace?.approval_mismatch_count ?? 0) > 0 && (
            <div className="rounded-md border border-agent-failed/30 bg-agent-failed/10 px-3 py-2 text-xs text-foreground">
              检测到 {trace?.approval_mismatch_count} 次审批不一致：执行已被中止，未产生对应副作用。
            </div>
          )}

          {trace?.side_effect_proposals?.length ? (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">
                冻结的副作用提案
              </p>
              {trace.side_effect_proposals.map((proposal, index) => (
                <div
                  key={index}
                  className="rounded-md border border-border/60 px-3 py-2 text-xs"
                >
                  <span className="font-medium">{proposal.tool ?? proposal.capability}</span>
                  {proposal.params ? (
                    <span className="ml-2 text-muted-foreground">
                      {JSON.stringify(proposal.params).slice(0, 180)}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}

          <Separator />

          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">工具调用轨迹</p>
            {trace?.tool_calls.length ? (
              trace.tool_calls.map((tc) => (
                <div
                  key={tc.id}
                  className="flex items-start gap-2 rounded-md border border-border/60 px-3 py-2 text-xs"
                >
                  {toolIcon(tc)}
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">
                      {tc.tool_name}
                      <span className="ml-2 text-muted-foreground">
                        {tc.status}
                        {formatToolDuration(tc) ? ` · ${formatToolDuration(tc)}` : ""}
                      </span>
                    </p>
                    {tc.input_params ? (
                      <p className="truncate text-muted-foreground">
                        {JSON.stringify(tc.input_params).slice(0, 200)}
                      </p>
                    ) : null}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-xs text-muted-foreground">暂无工具调用记录</p>
            )}
          </div>

          {trace?.spans?.length ? (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">
                Span 时间线
              </p>
              {trace.spans.map((span, index) => (
                <div
                  key={index}
                  className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-border/60 px-3 py-1.5 text-xs"
                >
                  <span
                    className={cn(
                      "h-2 w-2 rounded-full",
                      span.status === "ok"
                        ? "bg-agent-completed"
                        : "bg-agent-failed",
                    )}
                  />
                  <span className="font-medium">{span.span}</span>
                  {span.latency_ms != null ? (
                    <span className="text-muted-foreground">
                      {span.latency_ms}ms
                    </span>
                  ) : null}
                  {span.model ? (
                    <span className="text-muted-foreground">{span.model}</span>
                  ) : null}
                  {span.tokens != null ? (
                    <span className="text-muted-foreground">
                      {span.tokens} tok
                    </span>
                  ) : null}
                  {span.error ? (
                    <span className="text-agent-failed">{span.error}</span>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">评分与反馈</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-1">
            {[1, 2, 3, 4, 5].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setRating(value)}
                aria-label={`${value} 星`}
              >
                <Star
                  className={`h-5 w-5 ${
                    value <= rating
                      ? "fill-yellow-400 text-yellow-400"
                      : "text-muted-foreground"
                  }`}
                />
              </button>
            ))}
          </div>
          <Textarea
            placeholder="写点评价…（可选）"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
          />
          <Button
            size="sm"
            onClick={async () => {
              await api.submitRating(data.id, rating, comment || undefined);
              toast.success("感谢你的反馈");
              setFeedbacks(await api.listFeedback(data.id));
            }}
          >
            提交评分
          </Button>
          {feedbacks.length > 0 && (
            <div className="space-y-1 border-t border-border/60 pt-2">
              {feedbacks.map((feedback) => (
                <p key={feedback.id} className="text-xs text-muted-foreground">
                  {"★".repeat(feedback.rating)} · {feedback.comment ?? "无评论"}
                </p>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardContent className="space-y-2 py-4">
          <p className="type-small font-medium text-muted-foreground">
            任务指令
          </p>
          <p className="type-body">{data.user_input || "（无输入）"}</p>
        </CardContent>
      </Card>

      {data.status === "completed" && (
        <div className="rounded-md border border-agent-completed/20 bg-agent-completed/5 px-4 py-3">
          <div className="flex items-center gap-2 text-agent-completed">
            <CheckCircle2 className="h-4 w-4" />
            <span className="text-sm font-medium">执行完成，结果可查看</span>
          </div>
          {data.final_output ? (
            <p className="mt-2 text-sm leading-relaxed text-foreground">
              {data.final_output}
            </p>
          ) : null}
        </div>
      )}

      {data.status === "failed" && (
        <div className="rounded-md border border-agent-failed/20 bg-agent-failed/5 px-4 py-3">
          <div className="flex items-center gap-2 text-agent-failed">
            <AlertTriangle className="h-4 w-4" />
            <span className="text-sm font-medium">执行失败</span>
          </div>
          {data.error_message ? (
            <p className="mt-2 text-sm text-muted-foreground">
              {data.error_message}
            </p>
          ) : null}
          <Button
            size="sm"
            variant="outline"
            className="mt-3"
            onClick={() =>
              navigate(
                `/chat?draft=${encodeURIComponent(data.user_input || "")}`,
              )
            }
          >
            <RotateCcw className="h-4 w-4" />
            重新发起
          </Button>
        </div>
      )}

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
                        (step.state === "running" ||
                          step.state === "waiting") &&
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
              <div className="space-y-3">
                {data.tool_calls.map((tc, i) => (
                  <div
                    key={tc.id}
                    className="rounded-md border bg-background p-3"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2 text-sm">
                        {toolIcon(tc)}
                        <span className="truncate font-medium">
                          {i + 1}. {tc.tool_name}
                        </span>
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {tc.status}
                        {formatToolDuration(tc)
                          ? ` · ${formatToolDuration(tc)}`
                          : ""}
                      </span>
                    </div>

                    <details className="mt-2 space-y-2">
                      <summary className="cursor-pointer text-xs text-muted-foreground">
                        查看输入 / 输出
                      </summary>
                      <div className="mt-2 space-y-2">
                        <div>
                          <p className="text-xs font-medium text-muted-foreground">
                            输入参数
                          </p>
                          <pre className="mt-1 overflow-x-auto rounded-md bg-muted p-2 text-xs">
                            {JSON.stringify(tc.input_params ?? {}, null, 2)}
                          </pre>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-muted-foreground">
                            输出结果
                          </p>
                          <pre className="mt-1 overflow-x-auto rounded-md bg-muted p-2 text-xs">
                            {JSON.stringify(tc.output_result ?? {}, null, 2)}
                          </pre>
                        </div>
                      </div>
                    </details>
                  </div>
                ))}
              </div>
            )}

            {data.status === "waiting_for_approval" && (
              <div className="mt-4 space-y-3 border-t pt-4">
                <p className="text-sm text-muted-foreground">
                  Agent 想要执行：
                  {pendingCall ? pendingCall.tool_name : "下一步计划"}
                </p>
                <p className="rounded-md border border-border/60 px-3 py-2 text-xs text-muted-foreground">
                  审批冻结语义：执行必须与已批准的参数完全一致。如需修改计划，
                  请先“终止”本次执行，再重新创建任务获得新的审批。
                </p>
                <div className="flex flex-wrap gap-2">
                  <Hint label="批准并严格按冻结计划执行副作用">
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
                  </Hint>
                  <Hint label="终止本次执行，副作用立即停止">
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
                  </Hint>
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
