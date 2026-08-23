import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ChevronDown,
  ChevronUp,
  HelpCircle,
  MessageCircle,
  Send,
  Sparkles,
  Wand2,
} from "lucide-react";
import { toast } from "sonner";

import { MouseGlow } from "@/components/effects/MouseGlow";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  apiUrl,
  getAccessToken,
  type DispatchAnalysis,
  type ExecutionDetail,
} from "@/lib/api";
import { getStoredTheme, THEME_CHANGED_EVENT, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

type Message = { role: "user" | "assistant"; content: string };

type ChatMode = "chat" | "agent" | "skills";

type ClarificationRequest = {
  question: string;
  options: string[];
  clarification_id?: string | null;
};

type FlowItem = {
  id: string;
  kind:
    | "intent"
    | "complexity"
    | "plan"
    | "step"
    | "routing"
    | "tool"
    | "approval"
    | "verify"
    | "clarify"
    | "done";
  label: string;
  detail?: string;
  status: "running" | "success" | "error" | "waiting";
};

const CAPABILITY_LABELS: Record<string, string> = {
  answer: "直接回答",
  research: "联网检索",
  web_search: "网络搜索",
  knowledge: "知识库问答",
  search_knowledge: "知识检索",
  recall: "记忆检索",
  query_db: "数据查询",
  analysis: "综合分析",
  execute: "执行动作",
  send_email: "发送邮件",
};

const MODE_META: Record<
  ChatMode,
  { label: string; icon: typeof MessageCircle; hint: string }
> = {
  chat: {
    label: "闲聊",
    icon: MessageCircle,
    hint: "像 ChatGPT 一样聊天，不启动任务流程",
  },
  agent: {
    label: "Agent 协作",
    icon: Sparkles,
    hint: "多 Agent 拆解并执行任务，全程可审计",
  },
  skills: {
    label: "技能工坊",
    icon: Wand2,
    hint: "从 Skill / 插件库挑选流程，即选即用",
  },
};

const MODE_STORAGE_KEY = "agenthub.chat-mode";

function loadMode(): ChatMode {
  try {
    const value = localStorage.getItem(MODE_STORAGE_KEY);
    return value === "chat" || value === "skills" ? value : "agent";
  } catch {
    return "agent";
  }
}

let flowSequence = 0;

export default function Chat() {
  const [searchParams] = useSearchParams();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState(() => searchParams.get("draft") ?? "");
  const [mode, setMode] = useState<ChatMode>(() => loadMode());
  const [sending, setSending] = useState(false);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [details, setDetails] = useState<ExecutionDetail | null>(null);
  const [modifiedPlan, setModifiedPlan] = useState("");
  const [activeModel, setActiveModel] = useState<string | null>(null);
  const [optimizing, setOptimizing] = useState(false);
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme());
  const [clarification, setClarification] =
    useState<ClarificationRequest | null>(null);
  const [answeringClarification, setAnsweringClarification] = useState(false);
  const [flowItems, setFlowItems] = useState<FlowItem[]>([]);
  const [flowOpen, setFlowOpen] = useState(true);
  const [matchedSkills, setMatchedSkills] = useState<
    DispatchAnalysis["skills"]
  >([]);
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const pushFlow = (item: Omit<FlowItem, "id">) => {
    flowSequence += 1;
    const withId = { ...item, id: `flow-${flowSequence}` };
    setFlowItems((items) => [...items, withId]);
    return withId.id;
  };

  useEffect(() => {
    const onChange = (event: Event) =>
      setTheme((event as CustomEvent<Theme>).detail);
    window.addEventListener(THEME_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(THEME_CHANGED_EVENT, onChange);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(MODE_STORAGE_KEY, mode);
    } catch {
      // ignore
    }
  }, [mode]);

  // 技能工坊：输入时实时匹配 Skill（纯规则，零成本）
  useEffect(() => {
    if (mode !== "skills") return;
    if (!draft.trim()) {
      setMatchedSkills([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        setMatchedSkills(await api.matchSkills(draft.trim()));
      } catch {
        setMatchedSkills([]);
      }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [mode, draft]);

  useEffect(() => {
    (async () => {
      try {
        const keys = await api.listUserApiKeys();
        const key = keys.find((item) => item.is_active);
        if (key) {
          setActiveModel(key.model);
          return;
        }
        const models = await api.listModels();
        const model = models.find((item) => item.is_active && item.enabled);
        if (model) setActiveModel(model.model);
      } catch {
        // 模型状态获取失败时静默降级为“系统默认”
      }
    })();
  }, []);

  useEffect(() => {
    const existingId = searchParams.get("id");
    if (existingId) {
      api
        .request<{ id: string; messages: Message[] }>(
          `/conversations/${existingId}`,
        )
        .then((c) => {
          setConversationId(c.id);
          setMessages(c.messages ?? []);
        });
    } else {
      api
        .request<{ id: string; messages: Message[] }>("/conversations", {
          method: "POST",
          body: JSON.stringify({ title: "新对话" }),
        })
        .then((c) => {
          setConversationId(c.id);
          setMessages(c.messages ?? []);
        });
    }
  }, [searchParams]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function answerClarification(answer: string) {
    const current = clarification;
    if (!current || !current.clarification_id) {
      setClarification(null);
      return;
    }
    setAnsweringClarification(true);
    try {
      await api.answerClarification(current.clarification_id, answer);
      toast.success(`已按「${answer.slice(0, 30)}」继续执行`);
    } catch (err) {
      toast.error(String(err));
    } finally {
      setAnsweringClarification(false);
      setClarification(null);
    }
  }

  function handleFlowEvent(data: Record<string, unknown>) {
    const event = String(data.event ?? "");
    if (event === "complexity") {
      const report = (data.report ?? {}) as {
        score?: number;
        level?: string;
        factors?: Array<{ detail?: string }>;
      };
      const factors = (report.factors ?? [])
        .map((factor) => factor.detail)
        .filter(Boolean)
        .slice(0, 3)
        .join("、");
      pushFlow({
        kind: "complexity",
        label: `复杂度评估 · ${Math.round((report.score ?? 0) * 100)} 分 · ${
          report.level === "complex" ? "复杂任务" : "简单任务"
        }`,
        detail: factors || undefined,
        status: "success",
      });
      return;
    }
    if (event === "routing" && data.preview) {
      const preview = (data.preview ?? []) as Array<{
        step_id?: string;
        capability?: string;
        complexity?: string;
      }>;
      const summary = preview
        .map(
          (item) =>
            `${item.step_id ?? ""} ${CAPABILITY_LABELS[item.capability ?? ""] ?? item.capability ?? ""}·${
              item.complexity === "complex" ? "强模型" : "轻量模型"
            }`,
        )
        .join("｜");
      pushFlow({
        kind: "routing",
        label: "模型调度方案",
        detail: summary || undefined,
        status: "success",
      });
      return;
    }
    if (event === "routing" && data.decision) {
      const decision = (data.decision ?? {}) as {
        step_id?: string;
        capability?: string;
        complexity?: string;
      };
      const escalated = data.outcome === "escalated";
      pushFlow({
        kind: "routing",
        label: escalated
          ? `自动升级 · ${CAPABILITY_LABELS[decision.capability ?? ""] ?? ""}改用强模型重做`
          : `模型调度 · ${CAPABILITY_LABELS[decision.capability ?? ""] ?? decision.step_id ?? ""} · ${
              decision.complexity === "complex" ? "强模型" : "轻量模型"
            }`,
        status: escalated ? "running" : "success",
      });
      return;
    }
    if (event === "step") {
      const node = String(data.node ?? "");
      const stepIndex = Number(data.step_index ?? -1);
      const status = String(data.status ?? "");
      const key = `step-${stepIndex}-${node}`;
      if (status === "started") {
        const id = pushFlow({
          kind: "step",
          label: `执行步骤 · ${CAPABILITY_LABELS[node] ?? node}`,
          detail: `第 ${stepIndex + 1} 步`,
          status: "running",
        });
        setFlowItems((items) =>
          items.map((item) => (item.id === id ? { ...item, id: key } : item)),
        );
      } else if (status === "completed") {
        const key = `step-${stepIndex}-${node}`;
        setFlowItems((items) =>
          items.map((item) =>
            item.id === key ? { ...item, status: "success" } : item,
          ),
        );
      }
      return;
    }
    if (event === "tool_call") {
      pushFlow({
        kind: "tool",
        label: `工具调用 · ${String(data.tool_name ?? "")}`,
        status: "running",
      });
      return;
    }
    if (event === "tool_result") {
      pushFlow({
        kind: "tool",
        label: `工具返回 · ${String(data.tool_name ?? "")} · ${
          data.status === "success" ? "成功" : "失败"
        }`,
        status: data.status === "success" ? "success" : "error",
      });
      return;
    }
    if (event === "approval_required") {
      pushFlow({
        kind: "approval",
        label: "等待人工审批",
        detail: "副作用已冻结，批准后才执行，且只执行一次",
        status: "waiting",
      });
      return;
    }
    if (event === "clarification_required") {
      pushFlow({
        kind: "clarify",
        label: "语义确认",
        detail: "任务暂停，等待你选择最接近的理解",
        status: "waiting",
      });
      return;
    }
    if (event === "verify") {
      pushFlow({
        kind: "verify",
        label: "结果验证",
        detail: "验证不过会自动重排只读步骤，绝不假装成功",
        status: "running",
      });
      return;
    }
    if (event === "done") {
      setFlowItems((items) =>
        items.length > 0
          ? [
              ...items,
              {
                id: `flow-done-${Date.now()}`,
                kind: "done",
                label: data.status === "failed" ? "任务失败" : "任务完成",
                status: data.status === "failed" ? "error" : "success",
              },
            ]
          : items,
      );
    }
  }

  async function send() {
    if (!conversationId || !draft.trim() || sending) return;
    if (mode === "skills" && selectedSkillId) {
      await api.markSkillUsed(selectedSkillId).catch(() => undefined);
    }
    const userMessage = draft.trim();
    setDraft("");
    setSelectedSkillId(null);
    setMessages((m) => [...m, { role: "user", content: userMessage }]);
    setMessages((m) => [...m, { role: "assistant", content: "" }]);
    setSending(true);
    setFlowItems([]);
    setFlowOpen(true);
    flowSequence = 0;

    const token = getAccessToken();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const res = await fetch(
        apiUrl(`/conversations/${conversationId}/stream`),
        {
          method: "POST",
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            content: userMessage,
            mode,
            skill_id: mode === "skills" ? selectedSkillId : null,
          }),
        },
      );
      if (!res.ok || !res.body) throw new Error(String(res.status));

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistant = "";
      let clarificationSeen = false;

      const updateAssistant = (text: string) => {
        assistant = text;
        setMessages((m) => {
          const next = [...m];
          const idx = next.length - 1;
          if (next[idx]?.role === "assistant") {
            next[idx] = { role: "assistant", content: text };
          }
          return next;
        });
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.execution_id) setExecutionId(data.execution_id);
            handleFlowEvent(data);
            if (data.event === "token" && typeof data.token === "string") {
              assistant += data.token;
              updateAssistant(assistant);
            }
            if (
              data.event === "clarification" &&
              typeof data.message === "string" &&
              data.message
            ) {
              clarificationSeen = true;
              assistant = data.message;
              updateAssistant(assistant);
            }
            if (data.event === "clarification_required") {
              clarificationSeen = true;
              const payload = data.clarification ?? {};
              setClarification({
                question: String(payload.question ?? "请确认你的意图："),
                options: Array.isArray(payload.options)
                  ? payload.options.map(String)
                  : [],
                clarification_id: payload.clarification_id ?? null,
              });
              const hint = `⏸ 任务暂停，等待你确认语义：${String(payload.question ?? "")}`;
              updateAssistant(assistant ? `${assistant}\n\n${hint}` : hint);
            }
            if (
              data.event === "error" &&
              !clarificationSeen &&
              typeof data.message === "string" &&
              data.message
            ) {
              assistant = `请求失败：${data.message}`;
              updateAssistant(assistant);
            }
            if (
              data.event === "execution_failed" &&
              !clarificationSeen &&
              typeof data.error === "string" &&
              data.error
            ) {
              assistant = `执行失败：${data.error}`;
              updateAssistant(assistant);
            }
            if (data.final_output) updateAssistant(data.final_output);
            if (data.event === "done") {
              if (data.status === "failed") {
                if (
                  !clarificationSeen &&
                  typeof data.error_message === "string" &&
                  data.error_message
                ) {
                  assistant = `执行失败：${data.error_message}`;
                  updateAssistant(assistant);
                }
              } else {
                updateAssistant(data.final_output ?? assistant);
              }
              if (data.execution_id) {
                try {
                  setDetails(await api.getExecution(data.execution_id));
                } catch {
                  setDetails(null);
                }
              }
            }
          } catch {
            // ignore malformed SSE chunks
          }
        }
      }
    } catch (err) {
      const message =
        err instanceof Error && err.message
          ? err.message
          : "请求失败，请稍后重试";
      setMessages((m) => {
        const next = [...m];
        const idx = next.length - 1;
        if (next[idx]?.role === "assistant") {
          next[idx] = { role: "assistant", content: `请求失败：${message}` };
        }
        return next;
      });
    } finally {
      abortRef.current = null;
      setSending(false);
    }
  }

  async function stopGenerating() {
    abortRef.current?.abort();
    if (executionId) {
      try {
        await api.cancelExecution(executionId);
      } catch {
        // ignore cancel errors
      }
    }
    setSending(false);
  }

  async function optimize() {
    if (!draft.trim() || optimizing) return;
    setOptimizing(true);
    try {
      const result = await api.optimizePrompt(draft.trim());
      if (result.optimized) setDraft(result.optimized);
    } catch (err) {
      toast.error(String(err));
    } finally {
      setOptimizing(false);
    }
  }

  async function refreshDetails() {
    if (!executionId) return;
    try {
      setDetails(await api.getExecution(executionId));
    } catch {
      setDetails(null);
    }
  }

  const flowStatusBadge = (item: FlowItem) => {
    if (item.status === "success")
      return <Badge variant="default">✓ 完成</Badge>;
    if (item.status === "error")
      return <Badge variant="destructive">失败</Badge>;
    if (item.status === "waiting")
      return <Badge variant="secondary">等待你</Badge>;
    return <Badge variant="outline">进行中</Badge>;
  };

  return (
    <div className="relative flex h-[calc(100vh-7rem)] w-full items-center justify-center">
      <MouseGlow variant={theme === "light" ? "water" : "purple"} />
      <div className="relative z-10 flex h-full w-full max-w-3xl flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto py-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <p>开始对话，描述你想让 AgentHub 完成的任务。</p>
              <p className="text-xs">
                当前模式：{MODE_META[mode].label} —— {MODE_META[mode].hint}
              </p>
            </div>
          ) : (
            messages.map((m, i) => (
              <div
                key={i}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <Card
                  className={`max-w-[80%] px-4 py-2 text-sm ${
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : ""
                  }`}
                >
                  {m.content ||
                    (sending && i === messages.length - 1 ? "" : "（空回复）")}
                  {sending &&
                  i === messages.length - 1 &&
                  m.role === "assistant" ? (
                    <span className="animate-cursor-blink">▍</span>
                  ) : null}
                  {m.role === "assistant" &&
                  i === messages.length - 1 &&
                  details ? (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs text-muted-foreground">
                        查看执行详情
                      </summary>
                      <div className="mt-2 space-y-1 text-xs">
                        <p>状态：{details.status}</p>
                        {(details.tool_calls ?? []).map((tc) => (
                          <p key={tc.id}>
                            {tc.tool_name} · {tc.status}
                          </p>
                        ))}
                        {details.status === "waiting_for_approval" ? (
                          <div className="mt-2 space-y-2">
                            <textarea
                              value={modifiedPlan}
                              onChange={(e) => setModifiedPlan(e.target.value)}
                              className="w-full rounded-md border p-2 text-xs"
                              rows={2}
                              placeholder="修改 Agent 的下一步计划…"
                            />
                            <div className="flex flex-wrap gap-2">
                              <Button
                                size="sm"
                                onClick={async () => {
                                  await api.intervene(executionId!, {
                                    operator: "user",
                                    action: "approved",
                                  });
                                  await refreshDetails();
                                }}
                              >
                                批准执行
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={async () => {
                                  await api.intervene(executionId!, {
                                    operator: "user",
                                    action: "modified",
                                    modified_plan: modifiedPlan,
                                  });
                                  await refreshDetails();
                                }}
                              >
                                按修改执行
                              </Button>
                              <Button
                                size="sm"
                                variant="destructive"
                                onClick={async () => {
                                  await api.intervene(executionId!, {
                                    operator: "user",
                                    action: "terminate",
                                  });
                                  await refreshDetails();
                                }}
                              >
                                终止任务
                              </Button>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </details>
                  ) : null}
                </Card>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>

        {/* 执行流程面板：可展开/收起，人话关键词，展示真正有用的过程 */}
        {flowItems.length > 0 && (
          <Card className="mb-2 shrink-0 border-border/60 bg-card/70">
            <button
              type="button"
              onClick={() => setFlowOpen((open) => !open)}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-muted-foreground"
            >
              <span className="inline-flex items-center gap-2">
                <Sparkles className="h-3.5 w-3.5 text-primary" />
                执行流程（{flowItems.length} 步 · 全程留痕可审计）
              </span>
              {flowOpen ? (
                <ChevronDown className="h-3.5 w-3.5" />
              ) : (
                <ChevronUp className="h-3.5 w-3.5" />
              )}
            </button>
            {flowOpen && (
              <div className="max-h-44 space-y-1 overflow-y-auto border-t border-border/50 px-3 py-2">
                {flowItems.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between gap-2 text-xs"
                  >
                    <div className="min-w-0">
                      <span
                        className={cn(
                          "font-medium",
                          item.status === "error" && "text-destructive",
                        )}
                      >
                        {item.label}
                      </span>
                      {item.detail && (
                        <span className="ml-2 truncate text-muted-foreground">
                          {item.detail}
                        </span>
                      )}
                    </div>
                    <div className="shrink-0">{flowStatusBadge(item)}</div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}

        {/* 技能匹配（技能工坊模式） */}
        {mode === "skills" && matchedSkills.length > 0 && (
          <div className="mb-2 flex shrink-0 flex-wrap gap-1.5">
            {matchedSkills.slice(0, 4).map((skill) => (
              <Button
                key={skill.id}
                size="sm"
                variant={selectedSkillId === skill.id ? "default" : "outline"}
                onClick={() =>
                  setSelectedSkillId(
                    selectedSkillId === skill.id ? null : skill.id,
                  )
                }
              >
                <Wand2 className="mr-1 h-3 w-3" />
                {skill.name} · {(skill.score * 100).toFixed(0)}%
              </Button>
            ))}
          </div>
        )}

        <div className="relative z-10 shrink-0 space-y-2 pb-2">
          {/* 模式切换：闲聊 / Agent 协作 / 技能工坊 */}
          <div className="flex flex-wrap items-center gap-1 rounded-lg border border-border/60 bg-card/60 p-1 backdrop-blur">
            {(Object.keys(MODE_META) as ChatMode[]).map((value) => {
              const meta = MODE_META[value];
              const Icon = meta.icon;
              const active = mode === value;
              return (
                <Button
                  key={value}
                  type="button"
                  size="sm"
                  variant={active ? "default" : "ghost"}
                  className="h-8 gap-1.5 px-3"
                  onClick={() => {
                    setMode(value);
                    setSelectedSkillId(null);
                  }}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {meta.label}
                </Button>
              );
            })}
            <span className="ml-auto hidden truncate pr-2 text-xs text-muted-foreground sm:inline">
              {MODE_META[mode].hint}
            </span>
          </div>

          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="输入消息，Enter 发送"
            rows={3}
            className="glass resize-none border-border/70 bg-card/60 backdrop-blur"
          />
          <div className="flex items-center justify-between gap-2">
            <p className="truncate text-xs text-muted-foreground">
              当前模型：{activeModel ?? "系统默认"}
            </p>
            <div className="flex shrink-0 items-center gap-2">
              {localStorage.getItem("agenthub.prompt_optimize") !== "0" && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={optimize}
                  disabled={optimizing || !draft.trim()}
                >
                  <Sparkles className="mr-1 h-4 w-4" />
                  {optimizing ? "优化中…" : "优化"}
                </Button>
              )}
              {sending && (
                <Button variant="outline" size="sm" onClick={stopGenerating}>
                  停止生成
                </Button>
              )}
              <Button
                size="sm"
                onClick={send}
                disabled={sending || !draft.trim()}
              >
                <Send className="mr-1 h-4 w-4" />
                {sending ? "生成中…" : "发送"}
              </Button>
            </div>
          </div>
        </div>
      </div>

      <Dialog
        open={clarification !== null}
        onOpenChange={(open) =>
          !open && !answeringClarification && setClarification(null)
        }
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <HelpCircle className="h-5 w-5 text-primary" />
              需要你确认一下语义
            </DialogTitle>
            <DialogDescription className="pt-1">
              {clarification?.question}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            {(clarification?.options ?? []).map((option, index) => (
              <Button
                key={`${option}-${index}`}
                variant="outline"
                className="justify-start text-left"
                disabled={answeringClarification}
                onClick={() => answerClarification(option)}
              >
                {option}
              </Button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            选择后任务从断点继续执行，选择会被记入审计（为什么走这条路，全程可查）。
          </p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
