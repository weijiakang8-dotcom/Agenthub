import { useState } from "react";
import { ArrowRight, MessageSquareHeart, WandSparkles } from "lucide-react";

import { AuthModal } from "@/components/AuthModal";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { FeedbackDialog } from "@/components/FeedbackDialog";
import { GalaxyBackground } from "@/components/effects/GalaxyBackground";
import { StarField } from "@/components/effects/StarField";
import { Footer } from "@/components/layout/Footer";
import { Button } from "@/components/ui/button";

type Lang = "zh" | "en";

const STRINGS: Record<
  Lang,
  {
    login: string;
    register: string;
    feedback: string;
    feedbackHint: string;
    tagline1: string;
    tagline2: string;
  }
> = {
  zh: {
    login: "登录",
    register: "注册",
    feedback: "用户反馈",
    feedbackHint: "告诉我们你的想法",
    tagline1: "让 Agent 不再是固定岗位，",
    tagline2: "而成为可以动态组队、换岗和复用能力的智能执行单元。",
  },
  en: {
    login: "Sign In",
    register: "Sign Up",
    feedback: "Feedback",
    feedbackHint: "Tell us what you think",
    tagline1: "Agents are no longer fixed roles —",
    tagline2: "they team up, switch roles, and reuse capabilities dynamically.",
  },
};

const LANG_STORAGE_KEY = "agenthub.lang";

function loadLang(): Lang {
  try {
    return localStorage.getItem(LANG_STORAGE_KEY) === "en" ? "en" : "zh";
  } catch {
    return "zh";
  }
}

export default function Landing() {
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [lang, setLang] = useState<Lang>(() => loadLang());
  const t = STRINGS[lang];

  const openAuth = (mode: "login" | "register") => {
    setAuthMode(mode);
    setAuthOpen(true);
  };

  const toggleLang = () => {
    setLang((current) => {
      const next = current === "zh" ? "en" : "zh";
      try {
        localStorage.setItem(LANG_STORAGE_KEY, next);
      } catch {
        // ignore
      }
      return next;
    });
  };

  return (
    <div className="dark relative min-h-screen overflow-hidden bg-background text-foreground">
      <GalaxyBackground />

      {/* 中英文切换 */}
      <div className="absolute right-5 top-5 z-20">
        <Button
          variant="outline"
          size="sm"
          onClick={toggleLang}
          className="border-white/15 bg-white/5 backdrop-blur hover:bg-white/10"
        >
          {lang === "zh" ? "EN" : "中文"}
        </Button>
      </div>

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
            {t.tagline1}
          </span>
          <br />
          <span className="bg-gradient-to-r from-white via-indigo-100 to-purple-200 bg-clip-text text-transparent">
            {t.tagline2}
          </span>
        </p>

        {/* 大按钮：登录 / 注册 */}
        <div className="mt-12 flex flex-wrap items-center justify-center gap-6">
          <Button
            size="lg"
            onClick={() => openAuth("login")}
            className="h-14 px-12 text-lg shadow-lg shadow-primary/30 transition-transform duration-200 hover:scale-105"
          >
            {t.login}
            <ArrowRight className="h-5 w-5" />
          </Button>
          <Button
            size="lg"
            variant="outline"
            onClick={() => openAuth("register")}
            className="h-14 border-white/25 bg-white/5 px-12 text-lg text-white backdrop-blur transition-transform duration-200 hover:scale-105 hover:bg-white/10"
          >
            {t.register}
            <WandSparkles className="h-5 w-5" />
          </Button>
        </div>
      </main>

      {/* 右侧动态星空反馈按钮栏 */}
      <div className="absolute right-0 top-1/2 z-20 -translate-y-1/2">
        <button
          type="button"
          onClick={() => setFeedbackOpen(true)}
          className="group relative block h-64 w-16 overflow-hidden rounded-l-2xl border border-l-2 border-white/15 bg-black/30 backdrop-blur transition-all duration-300 hover:w-20 hover:border-primary/50 hover:bg-black/40 hover:shadow-[0_0_36px_rgba(139,92,246,0.35)]"
          title={t.feedback}
        >
          <StarField className="absolute inset-0 h-full w-full" />
          <span className="relative z-10 flex h-full flex-col items-center justify-center gap-3">
            <MessageSquareHeart className="h-5 w-5 text-white/90 transition-colors group-hover:text-primary" />
            <span
              className="text-sm font-medium tracking-widest text-white/90"
              style={{ writingMode: "vertical-rl" }}
            >
              {t.feedback}
            </span>
            <span
              className="hidden text-[10px] text-white/50 group-hover:block"
              style={{ writingMode: "vertical-rl" }}
            >
              {t.feedbackHint}
            </span>
          </span>
        </button>
      </div>

      <Footer />
      <AuthModal open={authOpen} onOpenChange={setAuthOpen} mode={authMode} />
      <FeedbackDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} />
    </div>
  );
}
