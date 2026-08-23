import { useEffect, useState } from "react";
import { Bot, RefreshCw, Undo2, Wand2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type AgentRosterItem, type AgentVersionItem } from "@/lib/api";

const ROLE_ICONS: Record<string, string> = {
  dispatcher: "🧭",
  planner: "🗺️",
  executor: "🛠️",
  verifier: "✅",
  clarifier: "❓",
  billing: "🧾",
};

export default function Agents() {
  const [roster, setRoster] = useState<AgentRosterItem[]>([]);
  const [versions, setVersions] = useState<Record<string, AgentVersionItem[]>>(
    {},
  );
  const [expanded, setExpanded] = useState<string | null>(null);
  const [updating, setUpdating] = useState<AgentRosterItem | null>(null);
  const [changeNote, setChangeNote] = useState("");
  const [examples, setExamples] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setRoster(await api.agentRoster());
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function toggleVersions(name: string) {
    if (expanded === name) {
      setExpanded(null);
      return;
    }
    setExpanded(name);
    if (!versions[name]) {
      try {
        const rows = await api.agentVersions(name);
        setVersions((current) => ({ ...current, [name]: rows }));
      } catch (err) {
        toast.error(String(err));
      }
    }
  }

  async function propose() {
    if (!updating) return;
    setSubmitting(true);
    try {
      const result = await api.agentUpdate(updating.name, {
        change_note: changeNote.trim() || "自更新候选",
        examples: examples
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean),
      });
      toast.success(`已生成候选版本 v${result.version}（${result.status}）`);
      setUpdating(null);
      setChangeNote("");
      setExamples("");
      await load();
      setExpanded(null);
    } catch (err) {
      toast.error(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function activate(name: string, versionId: string) {
    try {
      await api.agentActivate(versionId);
      toast.success("版本已激活");
      setVersions((current) => {
        const next = { ...current };
        delete next[name];
        return next;
      });
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function rollback(name: string) {
    try {
      const result = await api.agentRollback(name);
      toast.success(
        result.version
          ? `已回滚到 v${result.version}`
          : "已回退到内置默认提示词",
      );
      setVersions((current) => {
        const next = { ...current };
        delete next[name];
        return next;
      });
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl space-y-4">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5" />
            Agent 中心
          </CardTitle>
          <CardDescription>
            平台自带 6 个 Agent 各司其职；它们会从你的使用数据中自更新（候选 →
            门禁 → 激活），每一步都有版本、可回滚。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {roster.map((agent) => {
            const agentVersions = versions[agent.name] ?? [];
            return (
              <Card key={agent.name} className="border">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">
                      {ROLE_ICONS[agent.name]} {agent.name} · {agent.role}
                    </CardTitle>
                    <div className="flex gap-2">
                      <Badge
                        variant={agent.active_version ? "default" : "outline"}
                      >
                        {agent.active_version
                          ? `v${agent.active_version} 生效中`
                          : "内置默认"}
                      </Badge>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="line-clamp-2 text-xs text-muted-foreground">
                    {agent.active_system_prompt_preview}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => toggleVersions(agent.name)}
                    >
                      {expanded === agent.name ? "收起版本" : "版本历史"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setUpdating(agent)}
                    >
                      <Wand2 className="mr-1 h-3.5 w-3.5" /> 自更新
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => rollback(agent.name)}
                    >
                      <Undo2 className="mr-1 h-3.5 w-3.5" /> 回滚
                    </Button>
                  </div>
                  {expanded === agent.name && (
                    <div className="space-y-2 pt-2">
                      {agentVersions.length === 0 && (
                        <p className="text-xs text-muted-foreground">
                          暂无版本记录——点「自更新」生成第一个候选版本。
                        </p>
                      )}
                      {agentVersions.map((version) => (
                        <div
                          key={version.id}
                          className="flex items-center justify-between rounded-lg border p-2"
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-sm">
                                v{version.version}
                              </span>
                              <Badge
                                variant={
                                  version.status === "active"
                                    ? "default"
                                    : "secondary"
                                }
                              >
                                {version.status}
                              </Badge>
                              <span className="text-xs text-muted-foreground">
                                {version.change_note}
                              </span>
                            </div>
                            <p className="truncate text-xs text-muted-foreground">
                              {version.system_prompt_preview}
                            </p>
                          </div>
                          {version.status !== "active" &&
                            version.status !== "retired" && (
                              <Button
                                size="sm"
                                onClick={() => activate(agent.name, version.id)}
                              >
                                激活
                              </Button>
                            )}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </CardContent>
      </Card>

      <Dialog
        open={updating !== null}
        onOpenChange={(open) => !open && setUpdating(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <RefreshCw className="h-4 w-4" /> 自更新 {updating?.name}
            </DialogTitle>
            <DialogDescription>
              把最近成功的执行样本提炼成提示词增强，生成候选版本；指标不劣于当前版本才会通过门禁。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>更新说明</Label>
              <Textarea
                value={changeNote}
                onChange={(event) => setChangeNote(event.target.value)}
                placeholder="例如：加入两个新的成功规划样本"
                rows={2}
              />
            </div>
            <div className="space-y-1">
              <Label>成功样本（每行一个，最多 5 个）</Label>
              <Textarea
                value={examples}
                onChange={(event) => setExamples(event.target.value)}
                placeholder={
                  "样本A：三步完成调研并附来源\n样本B：复用技能骨架节省两步"
                }
                rows={4}
              />
            </div>
            <Button onClick={propose} disabled={submitting} className="w-full">
              {submitting ? "生成中…" : "生成候选版本（过门禁）"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
