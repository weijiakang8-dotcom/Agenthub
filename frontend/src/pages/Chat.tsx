import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { api, getAccessToken, type ExecutionDetail } from "@/lib/api";

type Message = { role: "user" | "assistant"; content: string };

export default function Chat() {
  const [searchParams] = useSearchParams();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [details, setDetails] = useState<ExecutionDetail | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const existingId = searchParams.get("id");
    if (existingId) {
      api
        .request<{ id: string; messages: Message[] }>(`/conversations/${existingId}`)
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

  async function send() {
    if (!conversationId || !draft.trim() || sending) return;
    const userMessage = draft.trim();
    setDraft("");
    setMessages((m) => [...m, { role: "user", content: userMessage }]);
    setMessages((m) => [...m, { role: "assistant", content: "" }]);
    setSending(true);

    const token = getAccessToken();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const res = await fetch(`/api/conversations/${conversationId}/stream`, {
        method: "POST",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ content: userMessage }),
      });
      if (!res.ok || !res.body) throw new Error(String(res.status));

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistant = "";

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
            if (data.event === "token" && typeof data.token === "string") {
              assistant += data.token;
              updateAssistant(assistant);
            }
            if (data.final_output) updateAssistant(data.final_output);
            if (data.event === "done") {
              updateAssistant(data.final_output ?? assistant);
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
      setMessages((m) => {
        const next = [...m];
        const idx = next.length - 1;
        if (next[idx]?.role === "assistant") {
          next[idx] = { role: "assistant", content: `请求失败：${String(err)}` };
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

  return (
    <div className="mx-auto flex h-[calc(100vh-7rem)] max-w-3xl flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto py-4">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            开始对话，描述你想让 AgentHub 完成的任务。
          </div>
        ) : (
          messages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <Card
                className={`max-w-[80%] px-4 py-2 text-sm ${
                  m.role === "user" ? "bg-primary text-primary-foreground" : ""
                }`}
              >
                {m.content || (sending && i === messages.length - 1 ? "…" : "")}
                {m.role === "assistant" && i === messages.length - 1 && details ? (
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
                    </div>
                  </details>
                ) : null}
              </Card>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      <div className="shrink-0 space-y-2 pb-2">
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
        />
        <div className="flex justify-end gap-2">
          {sending && (
            <Button variant="outline" onClick={stopGenerating}>
              停止生成
            </Button>
          )}
          <Button onClick={send} disabled={sending || !draft.trim()}>
            <Send className="h-4 w-4" />
            {sending ? "生成中…" : "发送"}
          </Button>
        </div>
      </div>
    </div>
  );
}
