import { useEffect, useState } from "react";
import { FlaskConical, Play, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, type EvalDataset, type EvalRun, type Workflow } from "@/lib/api";

export default function EvalPanel() {
  const [datasets, setDatasets] = useState<EvalDataset[]>([]);
  const [reports, setReports] = useState<EvalRun[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [itemsText, setItemsText] = useState(
    '[{"input": "你好，请用一句话介绍你自己", "expected": ""}]',
  );
  const [selectedDataset, setSelectedDataset] = useState("");
  const [selectedWorkflow, setSelectedWorkflow] = useState("none");
  const [threshold, setThreshold] = useState("7");
  const [running, setRunning] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [ds, rs, ws] = await Promise.all([
        api.listEvalDatasets(),
        api.listEvalReports(),
        api.listWorkflows(),
      ]);
      setDatasets(ds);
      setReports(rs);
      setWorkflows(ws);
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function createDataset() {
    if (!name.trim()) {
      toast.error("请填写数据集名称");
      return;
    }
    let items: Record<string, unknown>[];
    try {
      items = JSON.parse(itemsText || "[]");
      if (!Array.isArray(items)) throw new Error("items must be an array");
    } catch (err) {
      toast.error(`测试用例 JSON 格式错误：${String(err)}`);
      return;
    }
    try {
      await api.createEvalDataset({
        name: name.trim(),
        description: description.trim(),
        items,
      });
      toast.success("评测数据集已创建");
      setName("");
      setDescription("");
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function removeDataset(id: string) {
    try {
      await api.deleteEvalDataset(id);
      toast.success("数据集已删除");
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function run() {
    if (!selectedDataset) {
      toast.error("请选择评测数据集");
      return;
    }
    setRunning(true);
    try {
      const result = await api.runEval({
        dataset_id: selectedDataset,
        workflow_id: selectedWorkflow === "none" ? undefined : selectedWorkflow,
        threshold: Number(threshold) || 7,
      });
      toast.success(
        `评测完成，平均分 ${result.score ?? "—"}，通过 ${String(
          (result.report as { passed?: number })?.passed ?? 0,
        )} 项`,
      );
      await load();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-5">
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">创建评测数据集</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>名称</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="基础对话回归集"
              />
            </div>
            <div className="space-y-2">
              <Label>描述</Label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="用于每次发版前的快速回归"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>测试用例 JSON</Label>
            <Textarea
              value={itemsText}
              onChange={(e) => setItemsText(e.target.value)}
              className="min-h-36 font-mono text-xs"
            />
          </div>
          <Button onClick={createDataset}>创建数据集</Button>
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">运行评测</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label>数据集</Label>
              <Select
                value={selectedDataset}
                onValueChange={setSelectedDataset}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="选择数据集" />
                </SelectTrigger>
                <SelectContent>
                  {datasets.map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>工作流</Label>
              <Select
                value={selectedWorkflow}
                onValueChange={setSelectedWorkflow}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">默认评测工作流</SelectItem>
                  {workflows.map((w) => (
                    <SelectItem key={w.id} value={w.id}>
                      {w.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>通过阈值</Label>
              <Input
                type="number"
                step="0.1"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
              />
            </div>
          </div>
          <Button onClick={run} disabled={running}>
            <Play className="mr-2 h-4 w-4" />
            {running ? "评测运行中…" : "运行评测"}
          </Button>
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="type-h3">数据集</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-32 w-full" />
            ) : datasets.length === 0 ? (
              <EmptyState
                icon={FlaskConical}
                title="暂无数据集"
                description="创建一组测试用例，用于自动评测 Agent 输出质量。"
              />
            ) : (
              <div className="divide-y">
                {datasets.map((d) => (
                  <div
                    key={d.id}
                    className="flex items-start justify-between gap-3 py-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{d.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {d.description || "暂无描述"} · {d.items.length} 条用例
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeDataset(d.id)}
                    >
                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="type-h3">评测报告</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-32 w-full" />
            ) : reports.length === 0 ? (
              <EmptyState
                icon={FlaskConical}
                title="暂无评测报告"
                description="运行评测后，报告会显示在这里。"
              />
            ) : (
              <div className="divide-y">
                {reports.map((r) => (
                  <div
                    key={r.id}
                    className="flex items-center justify-between gap-3 py-3"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={
                            r.status === "completed" ? "default" : "outline"
                          }
                        >
                          {r.status}
                        </Badge>
                        <span className="text-sm font-medium">
                          平均分 {r.score?.toFixed(2) ?? "—"}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {new Date(r.created_at).toLocaleString()} ·{" "}
                        {String((r.report as { total?: number })?.total ?? 0)}{" "}
                        项
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
