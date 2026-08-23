import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Gauge,
  Route,
  Sparkles,
  Zap,
  ArrowRight,
  RefreshCw,
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
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type DispatchAnalysis } from "@/lib/api";

const TIER_LABELS: Record<string, string> = {
  economy: "省钱优先",
  balanced: "均衡",
  quality: "质量优先",
};

const FACTOR_LABELS: Record<string, string> = {
  category_task: "任务型意图",
  category_action: "含副作用",
  requires_tool: "需要工具",
  requires_data: "需要数据",
  requires_side_effect: "真实副作用",
  multi_goal: "多目标",
  needs_web_search: "需要联网",
  long_input: "输入较长",
  many_steps: "步骤多",
  side_effect_step: "副作用步骤",
  heavy_reasoning: "深度推理",
  dependencies: "步骤依赖",
  llm_judge: "模型法官",
  history_weak: "历史偏弱",
  history_strong: "历史可靠",
  task_score: "任务复杂度",
  capability: "能力权重",
};

export default function Dispatch() {
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [tier, setTier] = useState("balanced");
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<DispatchAnalysis | null>(null);

  async function analyze() {
    if (!input.trim()) return;
    setLoading(true);
    setAnalysis(null);
    try {
      setAnalysis(await api.analyzeDispatch({ input: input.trim(), tier }));
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }

  async function adopt(skillId: string) {
    try {
      await api.adoptSkill(skillId);
      toast.success("Skill 已添加到你的库");
    } catch (err) {
      toast.error(String(err));
    }
  }

  function goChatWithSkill(skillName?: string) {
    const draft = encodeURIComponent(input.trim());
    navigate(
      `/chat?draft=${draft}${skillName ? `&skill=${encodeURIComponent(skillName)}` : ""}`,
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Gauge className="h-5 w-5" />
            调度中心
          </CardTitle>
          <CardDescription>
            发布任务前先分析：复杂度评分、Skill
            匹配、每步路由方案——发布后执行全程直播，每步选哪个模型都有理由、有记录。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="描述你的任务，例如：帮我调研民宿行业 2026 趋势，整理成周报，并列出三家值得关注的竞品"
            rows={3}
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">执行策略：</span>
            {(["economy", "balanced", "quality"] as const).map((value) => (
              <Button
                key={value}
                size="sm"
                variant={tier === value ? "default" : "outline"}
                onClick={() => setTier(value)}
              >
                {TIER_LABELS[value]}
              </Button>
            ))}
            <div className="flex-1" />
            <Button onClick={analyze} disabled={loading || !input.trim()}>
              {loading ? (
                <>
                  <RefreshCw className="mr-1 h-4 w-4 animate-spin" /> 分析中
                </>
              ) : (
                <>
                  <Zap className="mr-1 h-4 w-4" /> 分析任务
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {loading && (
        <Card>
          <CardContent className="space-y-2 pt-6">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-20 w-full" />
          </CardContent>
        </Card>
      )}

      {analysis && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                复杂度评分
                <Badge
                  variant={
                    analysis.complexity.level === "complex"
                      ? "destructive"
                      : "secondary"
                  }
                >
                  {analysis.complexity.level === "complex" ? "复杂" : "简单"} ·{" "}
                  {(analysis.complexity.score * 100).toFixed(0)} 分
                </Badge>
              </CardTitle>
              <CardDescription>
                来源：{analysis.complexity.source} · 置信度{" "}
                {(analysis.complexity.confidence * 100).toFixed(0)}%
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {analysis.complexity.factors.map((factor) => (
                <div
                  key={`${factor.factor}-${factor.detail}`}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-muted-foreground">
                    {FACTOR_LABELS[factor.factor] ?? factor.factor}
                    <span className="ml-2 text-xs">{factor.detail}</span>
                  </span>
                  <Badge variant="outline">
                    {factor.contribution > 0 ? "+" : ""}
                    {factor.contribution.toFixed(2)}
                  </Badge>
                </div>
              ))}
            </CardContent>
          </Card>

          {analysis.skills.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="h-5 w-5" />
                  匹配到的 Skill
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {analysis.skills.slice(0, 5).map((skill) => (
                  <div
                    key={skill.id}
                    className="flex items-center justify-between rounded-lg border p-3"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-medium">
                          {skill.name}
                        </span>
                        <Badge variant="secondary">
                          {(skill.score * 100).toFixed(0)}% 匹配
                        </Badge>
                        {skill.source === "preset" && (
                          <Badge variant="outline">预设</Badge>
                        )}
                      </div>
                      <p className="truncate text-xs text-muted-foreground">
                        {skill.description}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {skill.reason}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => adopt(skill.id)}
                      >
                        添加到我的库
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => goChatWithSkill(skill.name)}
                      >
                        带它执行 <ArrowRight className="ml-1 h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {analysis.routing_preview.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Route className="h-5 w-5" />
                  路由预览
                </CardTitle>
                <CardDescription>
                  候选模型（按成本升序）：{analysis.candidates.join(" → ")}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {analysis.routing_preview.map((route) => (
                  <div
                    key={route.step_id}
                    className="flex items-center justify-between rounded-lg border p-3"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">{route.capability}</Badge>
                        <span className="text-sm font-medium">
                          {route.step_id}
                        </span>
                        <Badge
                          variant={
                            route.complexity === "complex"
                              ? "destructive"
                              : "secondary"
                          }
                        >
                          {route.complexity === "complex"
                            ? "强模型"
                            : "便宜模型"}
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {route.reason}
                      </p>
                    </div>
                    <span className="shrink-0 text-sm text-muted-foreground">
                      {(route.score * 100).toFixed(0)} 分
                    </span>
                  </div>
                ))}
                <p className="text-xs text-muted-foreground">
                  执行中每步会按此方案实时选模型；便宜模型失败会自动升级强模型重做该步（每步最多
                  1 次），全部留痕可查。
                </p>
              </CardContent>
            </Card>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => goChatWithSkill()}>
              直接执行 <ArrowRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
