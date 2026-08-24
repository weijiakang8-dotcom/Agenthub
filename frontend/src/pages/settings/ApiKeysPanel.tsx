import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  KeyRound,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Zap,
} from "lucide-react";
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
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type UserApiKey } from "@/lib/api";

type TestStatus = { ok: boolean; message: string } | null;

export default function ApiKeysPanel() {
  const [keys, setKeys] = useState<UserApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [provider, setProvider] = useState("openai-compatible");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testStatus, setTestStatus] = useState<TestStatus>(null);
  const [submitting, setSubmitting] = useState(false);

  const chatModels = useMemo(
    () => models.filter((item) => !item.toLowerCase().includes("image")),
    [models],
  );

  async function load() {
    setLoading(true);
    try {
      setKeys(await api.listUserApiKeys());
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function resetProbe() {
    setModels([]);
    setModel("");
    setTestStatus(null);
  }

  async function discover() {
    if (!baseUrl.trim() || !apiKey.trim()) {
      toast.error("请先填写 Base URL 和 API Key");
      return;
    }
    setDiscovering(true);
    setTestStatus(null);
    try {
      const submittedBaseUrl = baseUrl.trim();
      const result = await api.discoverUserModels({
        base_url: submittedBaseUrl,
        api_key: apiKey.trim(),
      });
      setBaseUrl(result.base_url);
      setModels(result.models);
      const availableChatModels = result.models.filter(
        (item) => !item.toLowerCase().includes("image"),
      );
      // 优先保留用户已填模型；其次推荐 sol；最后选择第一个聊天模型。
      const recommended =
        availableChatModels.find((item) => item === model) ??
        availableChatModels.find((item) =>
          item.toLowerCase().endsWith("-sol"),
        ) ??
        availableChatModels[0] ??
        result.models[0];
      setModel(recommended ?? "");
      toast.success(
        result.base_url === submittedBaseUrl.replace(/\/$/, "")
          ? `发现 ${result.models.length} 个模型，请测试后保存`
          : `发现 ${result.models.length} 个模型，API 地址已规范为 ${result.base_url}`,
      );
    } catch (err) {
      setModels([]);
      setModel("");
      toast.error(String(err));
    } finally {
      setDiscovering(false);
    }
  }

  async function testConnection(): Promise<boolean> {
    if (!baseUrl.trim() || !apiKey.trim() || !model.trim()) {
      toast.error("请先检测并选择模型");
      return false;
    }
    setTesting(true);
    setTestStatus(null);
    try {
      const result = await api.testUserModelConnection({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        model: model.trim(),
      });
      setTestStatus({
        ok: true,
        message: `${result.model} 连接成功${result.preview ? ` · ${result.preview}` : ""}`,
      });
      toast.success(`${result.model} 连接成功`);
      return true;
    } catch (err) {
      const message = String(err);
      setTestStatus({ ok: false, message });
      toast.error(message);
      return false;
    } finally {
      setTesting(false);
    }
  }

  async function create() {
    if (!apiKey.trim() || !model.trim() || !baseUrl.trim()) {
      toast.error("请填写 Base URL、API Key 并选择模型");
      return;
    }
    if (!testStatus?.ok) {
      const passed = await testConnection();
      if (!passed) return;
    }
    setSubmitting(true);
    try {
      await api.createUserApiKey({
        provider: provider.trim() || "openai-compatible",
        model: model.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
      });
      toast.success("模型连接已验证，API Key 已加密保存");
      setApiKey("");
      setModels([]);
      setModel("");
      setTestStatus(null);
      await load();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteUserApiKey(id);
      toast.success("API Key 已删除");
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function rotate(id: string) {
    const secret = window.prompt("请输入新的 API Key（旧密钥将立即失效）");
    if (!secret || !secret.trim()) return;
    try {
      await api.rotateUserApiKey(id, secret.trim());
      toast.success("API Key 已轮换；建议重新添加并测试模型连接");
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-5 w-5" />
            我的 API Key
          </CardTitle>
          <CardDescription>
            先检测服务返回的真实模型，再测试聊天连接；通过后密钥才会加密保存并优先用于对话。
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="key-provider">Provider</Label>
            <Input
              id="key-provider"
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
              placeholder="openai-compatible"
            />
          </div>
          <div className="space-y-1.5 md:col-span-2">
            <Label htmlFor="key-base-url">Base URL</Label>
            <Input
              id="key-base-url"
              value={baseUrl}
              onChange={(event) => {
                setBaseUrl(event.target.value);
                resetProbe();
              }}
              placeholder="http://example.com/v1"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="key-secret">API Key</Label>
            <Input
              id="key-secret"
              type="password"
              placeholder="sk-…"
              value={apiKey}
              onChange={(event) => {
                setApiKey(event.target.value);
                resetProbe();
              }}
            />
          </div>

          <Button
            variant="outline"
            onClick={discover}
            disabled={discovering || !baseUrl.trim() || !apiKey.trim()}
            className="md:col-span-4"
          >
            {discovering ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            {discovering ? "正在检测模型…" : "检测可用模型"}
          </Button>

          {models.length > 0 && (
            <>
              <div className="space-y-1.5 md:col-span-3">
                <Label htmlFor="key-model">模型标识</Label>
                <select
                  id="key-model"
                  value={model}
                  onChange={(event) => {
                    setModel(event.target.value);
                    setTestStatus(null);
                  }}
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm text-foreground shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  {chatModels.map((item) => (
                    <option key={item} value={item}>
                      {item}
                      {item.toLowerCase().endsWith("-sol") ? "（推荐）" : ""}
                    </option>
                  ))}
                </select>
                {models.length > chatModels.length && (
                  <p className="text-xs text-muted-foreground">
                    已自动排除 {models.length - chatModels.length}{" "}
                    个图片/非聊天模型。
                  </p>
                )}
              </div>
              <div className="flex items-end">
                <Button
                  variant="outline"
                  onClick={() => testConnection()}
                  disabled={testing || !model}
                  className="w-full"
                >
                  {testing ? (
                    <RefreshCw className="h-4 w-4 animate-spin" />
                  ) : (
                    <Zap className="h-4 w-4" />
                  )}
                  {testing ? "测试中…" : "测试连接"}
                </Button>
              </div>
            </>
          )}

          {testStatus && (
            <div
              className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm md:col-span-4 ${
                testStatus.ok
                  ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400"
                  : "border-destructive/30 bg-destructive/5 text-destructive"
              }`}
            >
              {testStatus.ok && <CheckCircle2 className="h-4 w-4 shrink-0" />}
              <span>{testStatus.message}</span>
            </div>
          )}

          <Button
            onClick={create}
            disabled={submitting || testing || !testStatus?.ok}
            className="md:col-span-4"
          >
            <Plus className="h-4 w-4" />
            {submitting ? "保存中…" : "保存已验证模型"}
          </Button>
        </CardContent>
      </Card>

      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : keys.length === 0 ? (
        <EmptyState
          icon={KeyRound}
          title="还没有 API Key"
          description="检测并添加你自己的 OpenAI 兼容模型，让它优先于系统默认模型。"
        />
      ) : (
        <div className="space-y-2">
          {keys.map((key) => (
            <Card key={key.id}>
              <CardContent className="flex items-center justify-between py-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{key.provider}</span>
                    <span className="text-sm text-muted-foreground">
                      {key.model}
                    </span>
                    <Badge variant={key.is_active ? "default" : "secondary"}>
                      {key.is_active ? "启用" : "停用"}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {key.base_url} · {key.api_key_masked}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => rotate(key.id)}
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    轮换
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => api.updateUserApiKey(key.id, !key.is_active)}
                  >
                    {key.is_active ? "停用" : "启用"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => remove(key.id)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
