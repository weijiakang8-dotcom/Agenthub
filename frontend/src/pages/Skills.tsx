import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Play,
  Plus,
  Sparkles,
  Trash2,
  Wand2,
  RefreshCw,
  Check,
  X,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, type GrowthProposal, type Skill } from "@/lib/api";

export default function Skills() {
  const navigate = useNavigate();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [proposals, setProposals] = useState<GrowthProposal[]>([]);
  const [patterns, setPatterns] = useState<
    Array<{ task_type: string; capability: string; calls: number }>
  >([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
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
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [skillList, growth] = await Promise.all([
        api.listSkills(),
        api.growthCandidates().catch(() => ({ proposals: [], patterns: [] })),
      ]);
      setSkills(skillList);
      setProposals(growth.proposals);
      setPatterns(growth.patterns);
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function seedPresets() {
    try {
      const result = await api.seedPresets();
      toast.success(`已播种 ${result.created} 个新预设 Skill`);
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function adopt(id: string) {
    try {
      await api.adoptSkill(id);
      toast.success("已添加到我的 Skill");
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteSkill(id);
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function runGrowth() {
    setScanning(true);
    try {
      const result = await api.growthRun();
      toast.success(`扫描完成，新候选 ${result.proposals.length} 个`);
      await load();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setScanning(false);
    }
  }

  async function acceptGrowth(id: string) {
    try {
      await api.growthAccept(id);
      toast.success("已采纳为你的 Skill");
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function rejectGrowth(id: string) {
    try {
      await api.growthReject(id);
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  function parseJson(
    text: string,
    label: string,
  ): Record<string, unknown> | null {
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

  function SkillCard({ skill, owned }: { skill: Skill; owned: boolean }) {
    return (
      <Card key={skill.id}>
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-base">{skill.name}</CardTitle>
            <div className="flex shrink-0 gap-1">
              {skill.source === "preset" && (
                <Badge variant="outline">预设</Badge>
              )}
              {skill.source === "auto" && (
                <Badge variant="secondary">自成长</Badge>
              )}
              {skill.status === "proposed" && (
                <Badge variant="secondary">候选</Badge>
              )}
              {skill.times_used > 0 && (
                <Badge variant="outline">用过 {skill.times_used} 次</Badge>
              )}
            </div>
          </div>
          <CardDescription className="line-clamp-2">
            {skill.description || "无描述"}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            v{skill.version} ·{" "}
            {skill.runtime === "agent" ? "调度中心" : "确定性内核"}
          </span>
          <div className="flex gap-2">
            {owned ? (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    const input =
                      window.prompt("输入任务，用这个 Skill 执行：");
                    if (input)
                      api
                        .executeSkill(skill.id, input)
                        .then(() => {
                          toast.success("已提交执行");
                          navigate("/executions");
                        })
                        .catch((err) => toast.error(String(err)));
                  }}
                >
                  <Play className="mr-1 h-3.5 w-3.5" /> 执行
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => remove(skill.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={() => adopt(skill.id)}
              >
                <Plus className="mr-1 h-3.5 w-3.5" /> 添加到我的库
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl space-y-4">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const mine = skills.filter((skill) => skill.organization_id !== null);
  const presets = skills.filter(
    (skill) => skill.organization_id === null && skill.source === "preset",
  );

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <Tabs defaultValue="mine">
        <TabsList>
          <TabsTrigger value="mine">我的 Skill</TabsTrigger>
          <TabsTrigger value="presets">预设包</TabsTrigger>
          <TabsTrigger value="growth">自成长</TabsTrigger>
        </TabsList>

        <TabsContent value="mine" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Plus className="h-4 w-4" /> 创建 Skill
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1">
                <Label>名称</Label>
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="例如：每周竞品周报"
                />
              </div>
              <div className="space-y-1">
                <Label>描述</Label>
                <Textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={2}
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label>Goal（JSON）</Label>
                  <Textarea
                    value={goalJson}
                    onChange={(event) => setGoalJson(event.target.value)}
                    rows={6}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label>Plan 模板（JSON）</Label>
                  <Textarea
                    value={planJson}
                    onChange={(event) => setPlanJson(event.target.value)}
                    rows={6}
                    className="font-mono text-xs"
                  />
                </div>
              </div>
              <Button onClick={create} disabled={creating}>
                {creating ? "创建中…" : "创建 Skill"}
              </Button>
            </CardContent>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2">
            {mine.map((skill) => (
              <SkillCard key={skill.id} skill={skill} owned />
            ))}
          </div>
          {mine.length === 0 && (
            <EmptyState
              title="还没有自己的 Skill"
              description="从「预设包」添加，或等「自成长」根据你的使用习惯自动打包。"
            />
          )}
        </TabsContent>

        <TabsContent value="presets" className="space-y-4">
          <div className="flex justify-between">
            <p className="text-sm text-muted-foreground">
              常用任务的开箱即用模板包（WorkBuddy
              式）。添加到你的库后可以随使用不断进化。
            </p>
            <Button variant="outline" size="sm" onClick={seedPresets}>
              <Sparkles className="mr-1 h-3.5 w-3.5" /> 播种预设包
            </Button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {presets.map((skill) => (
              <SkillCard key={skill.id} skill={skill} owned={false} />
            ))}
          </div>
          {presets.length === 0 && (
            <EmptyState
              title="预设包未播种"
              description="点击右上角「播种预设包」，一次性生成 8 个常用任务 Skill。"
            />
          )}
        </TabsContent>

        <TabsContent value="growth" className="space-y-4">
          <div className="flex justify-between">
            <p className="text-sm text-muted-foreground">
              平台观察你的使用习惯，把反复出现且成功率高的任务模式打包成候选
              Skill——你点头才生效。
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={runGrowth}
              disabled={scanning}
            >
              {scanning ? (
                <>
                  <RefreshCw className="mr-1 h-3.5 w-3.5 animate-spin" /> 扫描中
                </>
              ) : (
                <>
                  <Wand2 className="mr-1 h-3.5 w-3.5" /> 立即扫描
                </>
              )}
            </Button>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                平台看见的你的任务模式
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {patterns.map((pattern) => (
                <div
                  key={`${pattern.task_type}-${pattern.capability}`}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="font-mono text-xs text-muted-foreground">
                    {pattern.task_type} · {pattern.capability || "—"}
                  </span>
                  <Badge variant="outline">{pattern.calls} 次调用</Badge>
                </div>
              ))}
              {patterns.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  还没有足够的使用数据——多执行几个任务再来看看。
                </p>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2">
            {proposals.map((proposal) => (
              <Card key={proposal.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{proposal.name}</CardTitle>
                  <CardDescription className="line-clamp-3">
                    {proposal.description}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex gap-2">
                  <Button size="sm" onClick={() => acceptGrowth(proposal.id)}>
                    <Check className="mr-1 h-3.5 w-3.5" /> 采纳
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => rejectGrowth(proposal.id)}
                  >
                    <X className="mr-1 h-3.5 w-3.5" /> 忽略
                  </Button>
                </CardContent>
              </Card>
            ))}
            {proposals.length === 0 && (
              <Card className="sm:col-span-2">
                <CardContent className="pt-6 text-center text-sm text-muted-foreground">
                  暂无候选：同类任务出现 3
                  次以上且成功率达标时，会自动出现在这里。
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
