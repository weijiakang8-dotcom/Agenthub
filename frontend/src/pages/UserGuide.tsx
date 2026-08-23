import {
  Bot,
  CheckCircle2,
  CircleHelp,
  Database,
  Gauge,
  History,
  Layers,
  MessageSquare,
  Network,
  RefreshCcw,
  Rocket,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Workflow,
} from "lucide-react";

import { BrandLogo } from "@/components/brand/BrandLogo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const quickLinks = [
  ["what-is", "01 什么是 AgentHub"],
  ["capabilities", "02 核心能力"],
  ["quickstart", "03 快速开始"],
  ["agents", "04 Agent"],
  ["multi-agent", "05 Multi-Agent"],
  ["workflow", "06 Workflow"],
  ["rag", "07 RAG"],
  ["execution", "08 Execution"],
  ["approval", "09 Human Approval"],
  ["troubleshooting", "10 Troubleshooting"],
  ["faq", "FAQ"],
] as const;

function SectionCard({
  id,
  icon: Icon,
  title,
  badge,
  children,
}: {
  id: string;
  icon: typeof Bot;
  title: string;
  badge?: string;
  children: React.ReactNode;
}) {
  return (
    <Card id={id} className="scroll-mt-24">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="h-5 w-5" />
          </span>
          {title}
          {badge ? <Badge variant="secondary">{badge}</Badge> : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm leading-relaxed text-muted-foreground">
        {children}
      </CardContent>
    </Card>
  );
}

function Step({
  index,
  title,
  children,
}: {
  index: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
        {index}
      </span>
      <div>
        <p className="font-medium text-foreground">{title}</p>
        <p className="mt-1">{children}</p>
      </div>
    </div>
  );
}

function Tip({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2.5 text-sm text-primary-foreground">
      <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <div>{children}</div>
    </div>
  );
}

function Warn({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2.5 text-sm text-foreground">
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
      <div>{children}</div>
    </div>
  );
}

function Faq({ q, children }: { q: string; children: React.ReactNode }) {
  return (
    <details className="group rounded-lg border border-border bg-card/50 px-4 py-3">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-foreground">
        {q}
        <CircleHelp className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-2 text-sm leading-relaxed text-muted-foreground">
        {children}
      </div>
    </details>
  );
}

function ExampleCard({
  title,
  prompt,
  children,
}: {
  title: string;
  prompt: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-4">
      <div className="flex items-center gap-2">
        <MessageSquare className="h-4 w-4 text-primary" />
        <p className="text-sm font-semibold text-foreground">{title}</p>
      </div>
      <blockquote className="mt-2 rounded-md bg-secondary/60 px-3 py-2 text-sm text-foreground">
        {prompt}
      </blockquote>
      <div className="mt-3 space-y-2 text-sm text-muted-foreground">
        {children}
      </div>
    </div>
  );
}

function CapabilityCard({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Bot;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-background/50 p-4">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-primary" />
        <p className="text-sm font-semibold text-foreground">{title}</p>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed">{children}</p>
    </div>
  );
}

function ProblemCard({
  title,
  symptom,
  reason,
  solution,
}: {
  title: string;
  symptom: string;
  reason: string;
  solution: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-background/50 p-4">
      <div className="flex items-center gap-2">
        <TriangleAlert className="h-4 w-4 text-amber-500" />
        <p className="text-sm font-semibold text-foreground">{title}</p>
      </div>
      <div className="mt-3 space-y-2 text-xs leading-relaxed">
        <p>
          <span className="font-medium text-foreground">现象：</span>
          {symptom}
        </p>
        <p>
          <span className="font-medium text-foreground">原因：</span>
          {reason}
        </p>
        <p>
          <span className="font-medium text-foreground">解决方法：</span>
          {solution}
        </p>
      </div>
    </div>
  );
}

export default function UserGuide() {
  return (
    <div className="mx-auto max-w-3xl space-y-8 py-2">
      <div className="flex flex-col gap-4">
        <BrandLogo size="lg" />
        <div>
          <h1 className="type-h1">AgentHub 用户使用手册</h1>
          <p className="mt-2 max-w-2xl text-muted-foreground">
            这份手册面向第一次使用 AgentHub 的用户，用最简单的方式解释：AgentHub
            是什么、Agent 如何组队与换岗、Workflow
            怎么用、知识库怎么上传、任务执行到哪里看，以及出问题时怎么办。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {quickLinks.map(([id, label]) => (
            <Button key={id} asChild variant="outline" size="sm">
              <a href={`#${id}`}>{label}</a>
            </Button>
          ))}
        </div>
      </div>

      <SectionCard
        id="what-is"
        icon={Rocket}
        title="01 什么是 AgentHub"
        badge="新手必读"
      >
        <p>
          AgentHub 是一个面向多 Agent
          协作与执行的智能工作平台。你可以把任务交给平台，它会自动安排多个 AI
          Agent 分工、协作并执行，最后把过程和结果完整展示给你。
        </p>
        <p>核心理念只有一句话：</p>
        <Tip>
          Agent 不再是固定岗位，而是可以动态组队、换岗和复用能力的智能执行单元。
        </Tip>
        <p>
          与传统聊天机器人相比，AgentHub
          不只是“回答问题”，而是会拆解目标、规划步骤、调用工具、执行操作，并让你全程看得见、管得住。
        </p>
      </SectionCard>

      <SectionCard
        id="capabilities"
        icon={Layers}
        title="02 核心能力"
        badge="8 项能力"
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <CapabilityCard icon={Network} title="智能组队（Dynamic Teaming）">
            任务自动拆解 → 调度/规划/执行/验证/澄清/记账 6 个 Agent 按需分工，
            Skill 匹配为你选最合适的流程骨架。
          </CapabilityCard>
          <CapabilityCard
            icon={RefreshCcw}
            title="动态换岗（Dynamic Role Switching）"
          >
            意图路由 +
            复杂度评分决定每步"谁来干"；执行中可弹选项澄清、断点恢复，
            任务不中断。
          </CapabilityCard>
          <CapabilityCard icon={Layers} title="能力复用（Capability Reuse）">
            自成长 Skill：同类任务做多了自动打包成候选技能；RAG 知识库 +
            长期记忆 + 历史执行召回跨任务复用；模型绩效档案让路由越用越准。
          </CapabilityCard>
          <CapabilityCard icon={Workflow} title="Workflow">
            用节点和连线搭建可复用的任务流水线。
          </CapabilityCard>
          <CapabilityCard icon={Database} title="RAG">
            上传资料建立知识库，让 Agent 基于你的资料回答。
          </CapabilityCard>
          <CapabilityCard icon={ShieldCheck} title="Human Approval">
            高风险操作暂停等待人工确认，安全可控。
          </CapabilityCard>
          <CapabilityCard icon={History} title="Execution Resume">
            中断的执行可以查看状态、恢复或重新执行。
          </CapabilityCard>
          <CapabilityCard icon={CheckCircle2} title="Execution Audit">
            每个步骤、工具调用和结果都有完整记录可追溯。
          </CapabilityCard>
        </div>
      </SectionCard>

      <SectionCard
        id="quickstart"
        icon={Sparkles}
        title="03 快速开始"
        badge="5 分钟上手"
      >
        <Step index={1} title="注册 / 登录">
          注册需要邮箱验证码；登录只需邮箱和密码。
        </Step>
        <Step index={2} title="创建 Agent 模板">
          当前平台通过 Skill 库管理可复用的任务模板；你也可以在 Skill
          库创建自定义模板。
        </Step>
        <Step index={3} title="配置能力">
          在 Skill 或 Workflow 中配置 Agent 需要使用的步骤、工具和知识。
        </Step>
        <Step index={4} title="创建 Workflow">
          需要固定流程时，在 Workflow 编辑器中添加 Agent 节点并连接。
        </Step>
        <Step index={5} title="提交任务">
          在对话页或执行页输入任务目标。
        </Step>
        <Step index={6} title="Agent 自动执行">
          系统会自动组队、规划并执行。
        </Step>
        <Step index={7} title="查看执行过程">
          在对话下方或执行记录中查看当前步骤。
        </Step>
        <Step index={8} title="获得最终结果">
          任务完成后查看最终输出、报告或操作结果。
        </Step>
        <Tip>
          第一次使用建议先提交一个简单任务，例如“帮我总结 AI
          行业最近的三个趋势”，完整走一遍流程。
        </Tip>
      </SectionCard>

      <SectionCard id="agents" icon={Bot} title="04 Agent" badge="角色与组成">
        <p>
          Agent 是负责具体工作的智能执行单元。一个 Agent 通常由以下部分组成：
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <span className="font-medium text-foreground">Role：</span>
            它当前扮演的角色，例如调研、分析或执行。
          </li>
          <li>
            <span className="font-medium text-foreground">Model：</span>
            驱动它的 AI 模型，系统会根据任务复杂度自动选择。
          </li>
          <li>
            <span className="font-medium text-foreground">Tools：</span>
            它能调用的工具，例如检索、执行动作等。
          </li>
          <li>
            <span className="font-medium text-foreground">Knowledge：</span>
            它可以访问的知识库资料。
          </li>
          <li>
            <span className="font-medium text-foreground">
              Memory / Context：
            </span>
            当前任务中积累的上下文。
          </li>
          <li>
            <span className="font-medium text-foreground">Execution：</span>
            它实际执行任务的步骤记录。
          </li>
        </ul>
        <Warn>
          大多数任务不需要你手动指定 Agent。系统会自动拆解任务并选择合适的 Agent
          组合。
        </Warn>
      </SectionCard>

      <SectionCard
        id="multi-agent"
        icon={Network}
        title="05 Multi-Agent"
        badge="为什么需要多个 Agent"
      >
        <p>
          复杂任务很难由一个 Agent 从头做到尾。多个 Agent
          可以分工协作：一个负责查资料，一个负责分析，一个负责执行，一个负责检查结果。
        </p>
        <ExampleCard
          title="一个典型的多 Agent 流程"
          prompt="帮我研究新能源行业趋势，并生成一份报告。"
        >
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <Badge variant="secondary">Research Agent</Badge>
            <span>↓</span>
            <Badge variant="secondary">Analysis Agent</Badge>
            <span>↓</span>
            <Badge variant="secondary">Execution Agent</Badge>
            <span>↓</span>
            <Badge variant="secondary">Reviewer Agent</Badge>
            <span>↓</span>
            <Badge variant="secondary">最终结果</Badge>
          </div>
          <p>
            每个环节都可以根据上下文动态换岗，前一个 Agent 的结果会成为下一个
            Agent 的输入。
          </p>
        </ExampleCard>
        <p>
          这就是“动态组队”：不是把所有 Agent
          都放上去，而是根据任务目标选择最合适的组合；执行过程中也可以“换岗”，让更合适的角色接手。
        </p>
      </SectionCard>

      <SectionCard
        id="workflow"
        icon={Workflow}
        title="06 Workflow"
        badge="固定流程"
      >
        <p>Workflow 用图形化的方式定义任务流程。你会看到的几个概念：</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <span className="font-medium text-foreground">Node（节点）：</span>
            流程中的一个环节，例如一个 Agent 或一个工具。
          </li>
          <li>
            <span className="font-medium text-foreground">Edge（连线）：</span>
            节点之间的执行顺序。
          </li>
          <li>
            <span className="font-medium text-foreground">Agent Node：</span>由
            Agent 负责的节点。
          </li>
          <li>
            <span className="font-medium text-foreground">Tool Node：</span>
            由工具负责的节点，例如检索、文件操作。
          </li>
          <li>
            <span className="font-medium text-foreground">
              Conditional Route：
            </span>
            根据中间结果决定下一步走哪条分支。
          </li>
          <li>
            <span className="font-medium text-foreground">
              Execution State：
            </span>
            当前执行到哪一步、每个节点的状态。
          </li>
          <li>
            <span className="font-medium text-foreground">Checkpoint：</span>
            关键步骤的进度记录，用于恢复执行。
          </li>
        </ul>
        <p>
          在“Workflows”页面可以创建和管理工作流；在“工作流编辑器”中拖动节点、连线并保存。
        </p>
      </SectionCard>

      <SectionCard
        id="rag"
        icon={Database}
        title="07 RAG / 知识库"
        badge="基于你的资料"
      >
        <p>知识库让 Agent 的回答有“依据”，而不是只靠模型记忆。</p>
        <div className="grid gap-1.5 text-sm">
          <Step index={1} title="上传资料">
            在“模型与设置 → 知识库”上传文档。
          </Step>
          <Step index={2} title="系统建立索引">
            AgentHub 会把资料处理成可检索的内容。
          </Step>
          <Step index={3} title="用户提问">
            例如“根据这些资料总结产品架构”。
          </Step>
          <Step index={4} title="知识库检索">
            系统找到相关资料并交给 Agent。
          </Step>
          <Step index={5} title="Agent 生成答案">
            最终回答基于你的资料生成。
          </Step>
        </div>
        <p>
          为什么 RAG
          比单纯依赖模型记忆可靠？因为模型记忆是“大概知道”，知识库是“查证后回答”，答案有明确来源，也更不容易编造。
        </p>
        <Tip>上传资料时尽量使用命名清晰、内容完整的文档，检索效果会更好。</Tip>
      </SectionCard>

      <SectionCard
        id="execution"
        icon={Gauge}
        title="08 Execution 执行"
        badge="状态与恢复"
      >
        <p>执行状态是你判断任务走到哪一步的关键：</p>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Badge variant="outline">PENDING</Badge>
            <span>任务已排队，等待开始。</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary">RUNNING</Badge>
            <span>正在执行，可在详情中查看当前步骤。</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline">COMPLETED</Badge>
            <span>执行成功，查看最终结果。</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="destructive">FAILED</Badge>
            <span>执行失败，查看失败原因后重试。</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary">CANCELLED</Badge>
            <span>你主动停止了任务。</span>
          </div>
        </div>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <span className="font-medium text-foreground">
              如何查看执行到哪一步：
            </span>
            打开“执行记录”，进入执行详情，按步骤查看状态。
          </li>
          <li>
            <span className="font-medium text-foreground">如何恢复：</span>
            如果执行支持恢复，详情中会提供恢复入口；失败任务可以修正后重新执行。
          </li>
          <li>
            <span className="font-medium text-foreground">如何取消：</span>
            在对话页点击停止，或在执行记录中取消。
          </li>
        </ul>
      </SectionCard>

      <SectionCard
        id="approval"
        icon={ShieldCheck}
        title="09 Human Approval"
        badge="安全确认"
      >
        <p>当 Agent 准备执行高风险操作时，会暂停下来等你确认。常见场景包括：</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>发送邮件；</li>
          <li>修改数据；</li>
          <li>执行敏感操作。</li>
        </ul>
        <div className="grid gap-1.5 text-sm">
          <Step index={1} title="Agent 请求操作">
            系统展示下一步计划。
          </Step>
          <Step index={2} title="任务暂停">
            进入等待确认状态。
          </Step>
          <Step index={3} title="你审核计划">
            确认是否符合预期。
          </Step>
          <Step index={4} title="批准 / 拒绝 / 修改">
            批准后继续，拒绝后停止，也可以修改计划后执行。
          </Step>
        </div>
      </SectionCard>

      <SectionCard
        id="troubleshooting"
        icon={CircleHelp}
        title="10 Troubleshooting"
        badge="常见错误"
      >
        <div className="grid gap-3">
          <ProblemCard
            title="登录失败"
            symptom="输入邮箱和密码后无法登录。"
            reason="邮箱未注册，或密码错误（登录不再需要验证码）。"
            solution="确认邮箱已注册、密码正确；若忘记密码，请使用“找回密码”重置。"
          />
          <ProblemCard
            title="Agent 执行失败"
            symptom="任务进入 FAILED，没有最终结果。"
            reason="任务描述信息不足、外部工具返回错误或模型暂时不可用。"
            solution="打开执行详情查看失败原因，补充说明后重新执行。"
          />
          <ProblemCard
            title="模型不可用"
            symptom="对话没有回复，或提示模型请求失败。"
            reason="模型服务超时、密钥失效或服务暂时不可用。"
            solution="稍后重试；如果配置了自己的密钥，检查密钥是否有效。"
          />
          <ProblemCard
            title="RAG 没有检索结果"
            symptom="Agent 回答没有引用你上传的资料。"
            reason="资料未上传成功、问题主题不明确，或资料内容与问题无关。"
            solution="确认文档已上传并完成处理，在问题中包含明确主题词。"
          />
          <ProblemCard
            title="Workflow 卡住"
            symptom="任务长时间停在 RUNNING。"
            reason="某个节点等待外部响应、等待审批或执行时间较长。"
            solution="查看执行详情确认当前节点；如果是等待审批，请完成审批；否则取消后重新执行。"
          />
          <ProblemCard
            title="Execution Failed"
            symptom="执行记录显示 FAILED。"
            reason="节点报错、数据源失败或模型调用失败。"
            solution="查看失败节点和错误信息，修正后重试。"
          />
          <ProblemCard
            title="Resume 失败"
            symptom="点击恢复执行后没有继续。"
            reason="执行状态已过期、上下文缺失或任务已被取消。"
            solution="重新提交任务，或从执行详情查看是否仍可恢复。"
          />
          <ProblemCard
            title="SSE / Streaming 中断"
            symptom="对话回复到一半停止。"
            reason="网络波动、服务超时或连接被中断。"
            solution="点击停止后重新发送，或刷新页面查看是否已生成部分内容。"
          />
        </div>
      </SectionCard>

      <SectionCard
        id="faq"
        icon={MessageSquare}
        title="常见问题 FAQ"
        badge="10 问"
      >
        <div className="space-y-2">
          <Faq q="Agent 和普通 ChatGPT 式聊天有什么区别？">
            普通聊天只回答；AgentHub 会拆解任务、组队、执行并记录完整过程。
          </Faq>
          <Faq q="什么是多 Agent？">
            多个不同角色的 Agent 分工协作完成一个复杂任务。
          </Faq>
          <Faq q="Agent 如何动态组队？">
            系统根据任务目标自动选择合适的 Agent 组合，而不是固定使用同一个
            Agent。
          </Faq>
          <Faq q="Agent 如何换岗？">
            执行过程中，如果某个环节更适合其他角色，系统可以动态切换，任务不中断。
          </Faq>
          <Faq q="能力如何复用？">
            Agent 执行中沉淀的模板、知识和经验可以在后续任务中重复使用。
          </Faq>
          <Faq q="如何创建 Agent？">
            当前平台通过 Skill 库创建可复用的任务模板；固定流程则在 Workflow
            编辑器中创建。
          </Faq>
          <Faq q="如何创建 Workflow？">
            进入 Workflows 页面，在编辑器中添加节点、连线并保存。
          </Faq>
          <Faq q="如何查看日志 / Trace？">
            打开执行记录中的执行详情，可以查看步骤、工具调用和状态。
          </Faq>
          <Faq q="我的数据会影响其他用户吗？">
            不会，每个账号的数据相互隔离。
          </Faq>
          <Faq q="任务失败后怎么办？">
            查看失败原因，修正后重新执行；临时故障可稍后重试。
          </Faq>
        </div>
      </SectionCard>

      <div className="flex flex-col items-start gap-2 rounded-xl border border-border bg-card/60 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <CheckCircle2 className="h-4 w-4 text-primary" />
          你已经读完基础手册
        </div>
        <p className="text-sm text-muted-foreground">
          现在可以回到对话页，创建你的第一个任务。遇到新概念时，随时回来查阅。
        </p>
        <Button asChild className="mt-2">
          <a href="/chat">开始第一个任务</a>
        </Button>
      </div>
    </div>
  );
}
