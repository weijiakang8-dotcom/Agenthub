import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";

type Rule = {
  id: string;
  name: string;
  severity: string;
  condition: { metric?: string; threshold?: number };
  enabled: boolean;
};

export default function AlertRules() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [name, setName] = useState("");
  const [severity, setSeverity] = useState("warning");
  const [threshold, setThreshold] = useState("0.3");

  async function load() {
    setRules(await api.request<Rule[]>("/alert-rules"));
  }

  useEffect(() => {
    load();
  }, []);

  async function create() {
    await api.request("/alert-rules", {
      method: "POST",
      body: JSON.stringify({
        name,
        severity,
        condition: {
          metric: "execution_failure_rate",
          operator: "gt",
          threshold: Number(threshold),
        },
      }),
    });
    toast.success("规则已创建");
    setName("");
    load();
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">告警规则</h2>
        <p className="text-sm text-muted-foreground">动态配置告警触发条件</p>
      </div>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">新建规则</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-2">
              <Label>名称</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="执行失败率告警"
              />
            </div>
            <div className="space-y-2">
              <Label>严重程度</Label>
              <Select value={severity} onValueChange={setSeverity}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="info">info</SelectItem>
                  <SelectItem value="warning">warning</SelectItem>
                  <SelectItem value="critical">critical</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>失败率阈值</Label>
              <Input
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
              />
            </div>
          </div>
          <Button onClick={create}>创建规则</Button>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {rules.map((r) => (
          <Card key={r.id} className="shadow-sm">
            <CardContent className="flex items-center justify-between py-4">
              <div>
                <p className="font-medium">{r.name}</p>
                <p className="text-sm text-muted-foreground">
                  阈值 {r.condition.threshold ?? "—"} ·{" "}
                  {r.condition.metric ?? "—"}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge>{r.severity}</Badge>
                <Badge variant={r.enabled ? "default" : "outline"}>
                  {r.enabled ? "启用" : "停用"}
                </Badge>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    await api.request(`/alert-rules/${r.id}`, {
                      method: "DELETE",
                    });
                    load();
                  }}
                >
                  删除
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
