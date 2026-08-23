import { useEffect, useState } from "react";
import { BookOpen, KeyRound, MessageSquare, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const STORAGE_KEY = "agenthub.onboarded";

const steps = [
  {
    icon: MessageSquare,
    title: "自由对话",
    text: "在对话页描述任务，系统自动判断：普通对话走 LLM，任务指令交给 Kernel 确定性执行。",
  },
  {
    icon: Sparkles,
    title: "Skill 库",
    text: "Skill 是预定义任务模板（Goal + Plan + Capability），一键交给 KernelRuntime 执行，也可以创建自己的模板。",
  },
  {
    icon: KeyRound,
    title: "接入你的模型",
    text: "在“模型与设置 → 我的密钥”填入自己的 API Key，对话自动优先使用；失效时回退系统默认。",
  },
  {
    icon: BookOpen,
    title: "执行历史",
    text: "每次执行都记录步骤、实际模型、token 消耗与结果，可在执行记录中查看与评分。",
  },
];

export function OnboardingGuide() {
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      setOpen(true);
    }
    const openGuide = () => {
      setIndex(0);
      setOpen(true);
    };
    window.addEventListener("agenthub:open-guide", openGuide);
    return () => window.removeEventListener("agenthub:open-guide", openGuide);
  }, []);

  function close() {
    localStorage.setItem(STORAGE_KEY, "1");
    setOpen(false);
  }

  const StepIcon = steps[index].icon;

  return (
    <Dialog open={open} onOpenChange={(value) => !value && close()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <StepIcon className="h-5 w-5 text-primary" />
            {steps[index].title}
          </DialogTitle>
          <DialogDescription>{steps[index].text}</DialogDescription>
        </DialogHeader>

        <div className="flex justify-center gap-1.5">
          {steps.map((step, i) => (
            <span
              key={step.title}
              className={`h-1.5 rounded-full transition-all ${
                i === index ? "w-5 bg-primary" : "w-1.5 bg-muted-foreground/40"
              }`}
            />
          ))}
        </div>

        <DialogFooter className="sm:justify-between">
          <Button variant="ghost" onClick={close}>
            跳过
          </Button>
          {index < steps.length - 1 ? (
            <Button onClick={() => setIndex((i) => i + 1)}>下一步</Button>
          ) : (
            <Button onClick={close}>开始使用</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
