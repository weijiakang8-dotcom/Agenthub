import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MessageSquare, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";

type Conversation = {
  id: string;
  title: string;
  messages: { role: string; content: string }[];
  updated_at: string;
};

export default function History() {
  const [items, setItems] = useState<Conversation[]>([]);

  async function load() {
    setItems(await api.request<Conversation[]>("/conversations"));
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="type-h2">对话历史</h2>
        <p className="type-body text-muted-foreground">管理和切换历史对话</p>
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon={MessageSquare}
          title="暂无历史对话"
          description="开始一次对话后，它会出现在这里。"
        />
      ) : (
        <div className="divide-y rounded-lg border bg-card">
          {items.map((c) => (
            <div
              key={c.id}
              className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/50"
            >
              <Link to={`/chat?id=${c.id}`} className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{c.title}</p>
                <p className="text-xs text-muted-foreground">
                  {new Date(c.updated_at).toLocaleString()} · {c.messages.length} 条消息
                </p>
              </Link>
              <Button
                variant="ghost"
                size="icon"
                onClick={async () => {
                  await api.request(`/conversations/${c.id}`, { method: "DELETE" });
                  load();
                }}
              >
                <Trash2 className="h-4 w-4 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
