import { useEffect, useState } from "react";
import { KeyRound, Plus, Trash2 } from "lucide-react";
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

export default function ApiKeysPanel() {
  const [keys, setKeys] = useState<UserApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [provider, setProvider] = useState("deepseek");
  const [model, setModel] = useState("deepseek-v4-flash");
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com/v1");
  const [apiKey, setApiKey] = useState("");
  const [submitting, setSubmitting] = useState(false);

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

  async function create() {
    if (!apiKey.trim() || !model.trim() || !baseUrl.trim()) {
      toast.error("请填写模型、Base URL 和 API Key");
      return;
    }
    setSubmitting(true);
    try {
      await api.createUserApiKey({
        provider: provider.trim(),
        model: model.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
      });
      toast.success("API Key 已加密保存");
      setApiKey("");
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

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-5 w-5" />
            我的 API Key
          </CardTitle>
          <CardDescription>
            密钥加密存储、只显示尾号；对话执行时优先使用你的 Key，失效自动回退系统默认。
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="key-provider">Provider</Label>
            <Input
              id="key-provider"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="key-model">模型标识</Label>
            <Input
              id="key-model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="key-base-url">Base URL</Label>
            <Input
              id="key-base-url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="key-secret">API Key</Label>
            <Input
              id="key-secret"
              type="password"
              placeholder="sk-…"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>
          <Button
            onClick={create}
            disabled={submitting}
            className="md:col-span-4"
          >
            <Plus className="h-4 w-4" />
            添加密钥
          </Button>
        </CardContent>
      </Card>

      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : keys.length === 0 ? (
        <EmptyState
          icon={KeyRound}
          title="还没有 API Key"
          description="添加你自己的 Provider Key，让它优先于系统默认模型。"
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
