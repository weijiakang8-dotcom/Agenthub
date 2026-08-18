import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const KEY = "agenthub.prompt_optimize";

export default function ExperiencePanel() {
  const [enabled, setEnabled] = useState(localStorage.getItem(KEY) !== "0");

  function toggle() {
    const next = !enabled;
    setEnabled(next);
    localStorage.setItem(KEY, next ? "1" : "0");
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <SlidersHorizontal className="h-5 w-5" />
            体验设置
          </CardTitle>
          <CardDescription>
            提示词优化默认开启：发送前点击“优化”，由轻量级模型改写得更清晰。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">提示词优化（回车前优化）</p>
            <p className="text-xs text-muted-foreground">
              开启后，对话输入框旁显示“优化”按钮。
            </p>
          </div>
          <Button variant={enabled ? "default" : "outline"} onClick={toggle}>
            {enabled ? "已开启" : "已关闭"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
