import { useState } from "react";
import {
  ArrowRight,
  Layers,
  Network,
  RefreshCw,
  WandSparkles,
} from "lucide-react";

import { AuthModal } from "@/components/AuthModal";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { GalaxyBackground } from "@/components/effects/GalaxyBackground";
import { Footer } from "@/components/layout/Footer";
import { Button } from "@/components/ui/button";

const features = [
  {
    icon: Network,
    title: "智能组队",
    description:
      "根据任务目标动态选择最合适的 Agent，让多个 Agent 自动形成协作团队。",
    points: ["自动任务拆解", "多 Agent 协同", "动态能力匹配"],
  },
  {
    icon: RefreshCw,
    title: "动态换岗",
    description:
      "Agent 不再被固定角色限制，可根据任务上下文动态切换角色与能力。",
    points: ["上下文驱动", "动态角色切换", "任务不中断"],
  },
  {
    icon: Layers,
    title: "能力复用",
    description:
      "将 Agent 执行过程中沉淀的能力、经验与知识持续复用，让系统越用越强。",
    points: ["能力沉淀", "知识复用", "跨任务复用"],
  },
];

export default function Landing() {
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");

  const openAuth = (mode: "login" | "register") => {
    setAuthMode(mode);
    setAuthOpen(true);
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-background text-foreground">
      <GalaxyBackground />

      <main className="relative z-10 mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center px-6 text-center">
        <BrandLogo
          size="xl"
          layout="stack"
          bright
          className="mb-8"
          wordmark="Synplex"
          wordmarkImage
        />

        <h1 className="sr-only">Synplex · AgentHub</h1>
        <p className="mt-4 max-w-2xl text-xl leading-relaxed text-white sm:text-2xl">
          <span className="bg-gradient-to-r from-white via-indigo-100 to-purple-200 bg-clip-text text-transparent">
            让 Agent 不再是固定岗位，
          </span>
          <br />
          <span className="bg-gradient-to-r from-white via-indigo-100 to-purple-200 bg-clip-text text-transparent">
            而成为可以动态组队、换岗和复用能力的智能执行单元。
          </span>
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Button size="lg" onClick={() => openAuth("login")}>
            登录
            <ArrowRight className="h-4 w-4" />
          </Button>
          <Button
            size="lg"
            variant="outline"
            onClick={() => openAuth("register")}
          >
            开始体验
            <WandSparkles className="h-4 w-4" />
          </Button>
        </div>

        <div className="mt-16 grid gap-4 text-left sm:grid-cols-3">
          {features.map(({ icon: Icon, title, description, points }) => (
            <div
              key={title}
              className="group rounded-xl border border-border/60 bg-card/40 p-5 backdrop-blur transition-all duration-300 ease-out hover:-translate-y-1 hover:border-primary/40 hover:bg-card/60 hover:shadow-lg hover:shadow-primary/10"
            >
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary transition-shadow duration-300 group-hover:shadow-[0_0_24px_rgba(139,92,246,0.28)]">
                <Icon className="h-5 w-5" />
              </span>
              <p className="mt-4 text-base font-semibold text-foreground">
                {title}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {description}
              </p>
              <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
                {points.map((point) => (
                  <li key={point} className="flex items-center gap-1.5">
                    <span className="h-1 w-1 rounded-full bg-primary/70" />
                    {point}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </main>
      <Footer />
      <AuthModal open={authOpen} onOpenChange={setAuthOpen} mode={authMode} />
    </div>
  );
}
