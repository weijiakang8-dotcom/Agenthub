import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  BarChart3,
  CheckCircle2,
  Clock,
  Database,
  Loader2,
  Plus,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

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
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type Execution } from "@/lib/api";
import { STATUS_META, timeAgo } from "@/lib/format";

const WELCOME_KEY = "agenthub.welcomed";

type CacheStats = { hits: number; misses: number; saved: number };

export default function Dashboard() {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [cache, setCache] = useState<CacheStats>({ hits: 0, misses: 0, saved: 0 });
  const [loading, setLoading] = useState(true);
  const [welcomeOpen, setWelcomeOpen] = useState(false);

  useEffect(() => {
    api
      .listExecutions()
      .then(setExecutions)
      .finally(() => setLoading(false));
    if (!localStorage.getItem(WELCOME_KEY)) setWelcomeOpen(true);

    fetch("/metrics")
      .then((r) => r.text())
      .then((text) => {
        const hits = Number(text.match(/cache_hits_total\s+([\d.]+)/)?.[1] ?? 0);
        const misses = Number(text.match(/cache_misses_total\s+([\d.]+)/)?.[1] ?? 0);
        const saved = Number(text.match(/tokens_saved_total\s+([\d.]+)/)?.[1] ?? 0);
        setCache({ hits, misses, saved });
      })
      .catch(() => undefined);
  }, []);

  const cacheRate = cache.hits + cache.misses > 0
    ? Math.round((cache.hits / (cache.hits + cache.misses)) * 100)
    : 0;

  const stats = [
    { label: "总执行数", value: executions.length, icon: BarChart3, className: "bg-blue-100 text-blue-600" },
    { label: "运行中", value: executions.filter((e) => e.status === "running").length, icon: Loader2, className: "bg-amber-100 text-amber-600" },
    { label: "待审核", value: executions.filter((e) => e.status === "waiting_for_approval").length, icon: Clock, className: "bg-purple-100 text-purple-600" },
    { label: "已完成", value: executions.filter((e) => e.status === "completed").length, icon: CheckCircle2, className: "bg-emerald-100 text-emerald-600" },
  ];

  const scored = executions
    .filter((e) => e.eval_score !== null)
    .sort((a, b) => (a.created_at > b.created_at ? 1 : -1))
    .slice(-12);
  const qualityData = scored.map((e, i) => ({ name: String(i + 1), score: e.eval_score ?? 0 }));

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label} className="shadow-sm">
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-sm text-muted-foreground">{s.label}</p>
                {loading ? (
                  <Skeleton className="mt-2 h-8 w-12" />
                ) : (
                  <p className="mt-1 text-3xl font-semibold">{s.value}</p>
                )}
              </div>
              <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${s.className}`}>
                <s.icon className="h-5 w-5" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Database className="h-4 w-4 text-primary" />
              语义缓存
            </CardTitle>
            <CardDescription>命中率 {cacheRate}%</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">命中 / 未命中</span>
              <span className="font-medium">{cache.hits} / {cache.misses}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">估算节省 Token</span>
              <span className="font-medium">{cache.saved}</span>
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <TrendingUp className="h-4 w-4 text-primary" />
              执行质量趋势
            </CardTitle>
          </CardHeader>
          <CardContent className="h-40">
            {qualityData.length === 0 ? (
              <p className="pt-8 text-center text-sm text-muted-foreground">暂无评分数据</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={qualityData}>
                  <XAxis dataKey="name" />
                  <YAxis domain={[0, 10]} />
                  <Tooltip />
                  <Line type="monotone" dataKey="score" stroke="#2563eb" strokeWidth={2} dot />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="shadow-sm xl:col-span-2">
          <CardHeader>
            <CardTitle>最近执行记录</CardTitle>
            <CardDescription>最近 5 条工作流执行</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : executions.length === 0 ? (
              <div className="py-10 text-center text-sm text-muted-foreground">
                还没有执行记录
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>状态</TableHead>
                    <TableHead>用户输入</TableHead>
                    <TableHead>时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {executions.slice(0, 5).map((e) => {
                    const meta = STATUS_META[e.status];
                    return (
                      <TableRow key={e.id}>
                        <TableCell>
                          <Badge className={meta.className}>{meta.label}</Badge>
                        </TableCell>
                        <TableCell className="max-w-[260px] truncate">
                          {e.user_input || "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {timeAgo(e.created_at)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle>快速开始</CardTitle>
            <CardDescription>创建你的第一个 AI 工作流</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              在 Executions 页面选择工作流并输入指令，AgentHub
              会自动编排多个智能体完成任务。
            </p>
            <Button asChild className="w-full">
              <Link to="/executions">
                <Plus className="mr-2 h-4 w-4" />
                新建执行
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      <Dialog open={welcomeOpen} onOpenChange={setWelcomeOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              Welcome to AgentHub
            </DialogTitle>
            <DialogDescription>
              欢迎使用企业级多智能体协作平台。从这里开始编排、执行并追踪你的
              AI 工作流。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              onClick={() => {
                localStorage.setItem(WELCOME_KEY, "1");
                setWelcomeOpen(false);
              }}
            >
              开始使用
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
