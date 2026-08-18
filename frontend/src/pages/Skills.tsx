import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Play, Plus, Sparkles, Trash2 } from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
import { api, type Skill } from "@/lib/api";

export default function Skills() {
  const navigate = useNavigate();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [goalJson, setGoalJson] = useState(
    '{"predicate":"observation_exists","required_evidence":"L3_OBSERVED"}',
  );
  const [planJson, setPlanJson] = useState(
    JSON.stringify(
      {
        goal: {
          predicate: "observation_exists",
          required_evidence: "L3_OBSERVED",
        },
        tasks: [
          {
            task_id: "t-observe",
            capability_id: "observe",
            idempotency_key: "skill-{execution_id}",
            payload: { url: "{input}" },
          },
        ],
      },
      null,
      2,
    ),
  );
  const [inputBySkill, setInputBySkill] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setSkills(await api.listSkills());
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function parseJson(text: string, label: string): Record<string, unknown> | null {
    try {
      return JSON.parse(text) as Record<string, unknown>;
    } catch {
      toast.error(`${label} 不是合法 JSON`);
      return null;
    }
  }

  async function create() {
    const goal = parseJson(goalJson, "Goal");
    const plan = parseJson(planJson, "Plan 模板");
    if (!goal || !plan || !name.trim()) return;
    setCreating(true);
    try {
      await api.createSkill({
        name: name.trim(),
        description: description.trim(),
        goal,
        plan_template: plan,
      });
      toast.success("Skill 已创建");
      setName("");
      setDescription("");
      await load();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setCreating(false);
    }
  }

  async function run(skill: Skill) {
    const input = inputBySkill[skill.id]?.trim();
    if (!input) {
      toast.error("请填写执行输入");
      return;
    }
    try {
      const result = await api.executeSkill(skill.id, input);
      toast.success("Skill 已交给 Kernel 执行");
      navigate(`/executions/${result.execution_id}`);
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteSkill(id);
      toast.success("Skill 已删除");
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="type-h2 flex items-center gap-2">
          <Sparkles className="h-6 w-6" />
          Skill 库
        </h2>
        <p className="type-body text-muted-foreground">
          预定义任务模板（Goal + Plan + Capability 组合），一键交给 KernelRuntime 执行
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>创建自定义 Skill</CardTitle>
          <CardDescription>
            Goal 与 Plan 模板必须符合 Kernel 语义（8 个 Capability，OBSERVE/MUTATE 需
            idempotency_key）。
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="skill-name">名称</Label>
            <Input
              id="skill-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="skill-desc">描述</Label>
            <Input
              id="skill-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="skill-goal">Goal（JSON）</Label>
            <Textarea
              id="skill-goal"
              className="font-mono text-xs"
              rows={3}
              value={goalJson}
              onChange={(e) => setGoalJson(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="skill-plan">Plan 模板（JSON，支持 {"{input}"}）</Label>
            <Textarea
              id="skill-plan"
              className="font-mono text-xs"
              rows={6}
              value={planJson}
              onChange={(e) => setPlanJson(e.target.value)}
            />
          </div>
          <Button
            onClick={create}
            disabled={creating}
            className="md:col-span-2"
          >
            <Plus className="h-4 w-4" />
            创建 Skill
          </Button>
        </CardContent>
      </Card>

      {loading ? (
        <Skeleton className="h-40 w-full" />
      ) : skills.length === 0 ? (
        <EmptyState
          icon={Sparkles}
          title="Skill 库为空"
          description="创建你的第一个可复用任务模板。"
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {skills.map((skill) => (
            <Card key={skill.id}>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-base">
                    {skill.icon === "eye" ? "👁️" : <Sparkles className="h-4 w-4" />}
                    {skill.name}
                  </span>
                  {!skill.created_by ? (
                    <Badge variant="secondary">内置</Badge>
                  ) : (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => remove(skill.id)}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  )}
                </CardTitle>
                <CardDescription>{skill.description || "无描述"}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <Input
                  placeholder="执行输入，例如 https://example.com/data"
                  value={inputBySkill[skill.id] ?? ""}
                  onChange={(e) =>
                    setInputBySkill((prev) => ({
                      ...prev,
                      [skill.id]: e.target.value,
                    }))
                  }
                />
                <Button
                  className="w-full"
                  onClick={() => run(skill)}
                >
                  <Play className="h-4 w-4" />
                  执行
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
