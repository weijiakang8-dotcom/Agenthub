import { useState } from "react";
import { ArrowRight, Sparkles, WandSparkles } from "lucide-react";

import { AuthModal } from "@/components/AuthModal";
import { MouseGlow } from "@/components/effects/MouseGlow";
import { Button } from "@/components/ui/button";

export default function Landing() {
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");

  const openAuth = (mode: "login" | "register") => {
    setAuthMode(mode);
    setAuthOpen(true);
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-background text-foreground">
      <div
        className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(99,102,241,0.22),_transparent_55%)]"
        aria-hidden
      />
      <MouseGlow />

      <main className="relative z-10 mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center px-6 text-center">
        <div className="mb-8 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg shadow-indigo-500/25">
          <Sparkles className="h-8 w-8 text-white" />
        </div>

        <h1 className="type-display bg-gradient-to-r from-white via-indigo-100 to-purple-200 bg-clip-text text-transparent">
          AgentHub
        </h1>
        <p className="mt-3 max-w-xl text-lg text-muted-foreground">
          可验证、可终止、确定性的多智能体协作平台
          <br />
          让每一个结论都能溯源到现实。
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

        <div className="mt-16 grid gap-3 text-left sm:grid-cols-3">
          {[
            ["可验证", "Evidence Level L1–L4，Prediction 永远不等于 Observation"],
            ["可终止", "确定性 State Transition Kernel + GoalEvaluator"],
            ["可对账", "Command → Receipt → Observation 完整副作用生命周期"],
          ].map(([title, text]) => (
            <div
              key={title}
              className="rounded-xl border border-border/60 bg-card/40 p-4 backdrop-blur"
            >
              <p className="text-sm font-semibold">{title}</p>
              <p className="mt-1 text-xs text-muted-foreground">{text}</p>
            </div>
          ))}
        </div>
      </main>
      <AuthModal open={authOpen} onOpenChange={setAuthOpen} mode={authMode} />
    </div>
  );
}
