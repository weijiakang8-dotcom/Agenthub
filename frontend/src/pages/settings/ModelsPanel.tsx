import { useEffect, useState } from "react";
import { Cpu, PlayCircle, Star } from "lucide-react";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type ModelConfig } from "@/lib/api";

const providers = ["deepseek", "openai", "azure", "ollama", "custom"];

export default function ModelsPanel() {
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [provider, setProvider] = useState("deepseek");
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com/v1");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("deepseek-chat");
  const [maxTokens, setMaxTokens] = useState("4096");
  const [cost, setCost] = useState("0.002");
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setModels(await api.listModels());
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function create() {
    if (!name.trim() || !baseUrl.trim() || !model.trim()) {
      toast.error("请填写模型名称、Base URL 和模型标识");
      return;
    }
    setSubmitting(true);
    try {
      await api.createModel({
        name: name.trim(),
        provider,
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        model: model.trim(),
        max_tokens: Number(maxTokens) || 4096,
        cost_per_1k_tokens: Number(cost) || 0,
      });
      toast.success("模型已添加");
      setName("");
      setApiKey("");
      setModel("");
      await load();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function test(id: string) {
    toast.promise(api.testModel(id), {
      loading: "正在测试模型连接…",
      success: (data) =>
        data.ok ? "模型连接正常" : `连接失败：${data.error ?? "未知错误"}`,
      error: (err) => String(err),
    });
  }

  async function setDefault(id: string) {
    try {
      await api.updateModel(id, { is_default: true });
      toast.success("已设为默认模型");
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function toggleActive(modelItem: ModelConfig) {
    try {
      await api.updateModel(modelItem.id, { is_active: !modelItem.is_active });
      toast.success(modelItem.is_active ? "模型已停用" : "模型已启用");
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  return (
    <div className="space-y-5">
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">添加模型</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-2">
              <Label>名称</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="DeepSeek 主模型"
              />
            </div>
            <div className="space-y-2">
              <Label>Provider</Label>
              <Select value={provider} onValueChange={setProvider}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 lg:col-span-2">
              <Label>Base URL</Label>
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.deepseek.com/v1"
              />
            </div>
            <div className="space-y-2">
              <Label>API Key</Label>
              <Input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-…"
              />
            </div>
            <div className="space-y-2">
              <Label>模型标识</Label>
              <Input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="deepseek-chat"
              />
            </div>
            <div className="space-y-2">
              <Label>Max Tokens</Label>
              <Input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>每 1K Tokens 成本</Label>
              <Input
                type="number"
                step="0.0001"
                value={cost}
                onChange={(e) => setCost(e.target.value)}
              />
            </div>
          </div>
          <Button className="mt-4" onClick={create} disabled={submitting}>
            {submitting ? "添加中…" : "添加模型"}
          </Button>
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">模型列表</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-32 w-full" />
          ) : models.length === 0 ? (
            <EmptyState
              icon={Cpu}
              title="还没有模型"
              description="添加至少一个模型后，Agent 才能完成多模型路由。"
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>名称</TableHead>
                  <TableHead>Provider</TableHead>
                  <TableHead>模型</TableHead>
                  <TableHead>成本</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {models.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="font-medium">
                      <span className="flex items-center gap-2">
                        {m.name}
                        {m.is_default && (
                          <Star className="h-3.5 w-3.5 text-warning" />
                        )}
                      </span>
                    </TableCell>
                    <TableCell>{m.provider}</TableCell>
                    <TableCell className="max-w-[180px] truncate">
                      {m.model}
                    </TableCell>
                    <TableCell>${m.cost_per_1k_tokens.toFixed(4)}</TableCell>
                    <TableCell>
                      <Badge variant={m.is_active ? "default" : "outline"}>
                        {m.is_active ? "启用" : "停用"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => test(m.id)}
                        >
                          <PlayCircle className="mr-1 h-3.5 w-3.5" />
                          测试
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setDefault(m.id)}
                          disabled={m.is_default}
                        >
                          设默认
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => toggleActive(m)}
                        >
                          {m.is_active ? "停用" : "启用"}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
