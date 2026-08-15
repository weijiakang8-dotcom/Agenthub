import { Cpu, FileText, BellRing, BarChart3, FlaskConical } from "lucide-react";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import DocumentsPanel from "@/pages/settings/DocumentsPanel";
import EvalPanel from "@/pages/settings/EvalPanel";
import ModelsPanel from "@/pages/settings/ModelsPanel";
import NotificationsPanel from "@/pages/settings/NotificationsPanel";
import UsagePanel from "@/pages/settings/UsagePanel";

const tabs = [
  { value: "models", label: "模型", icon: Cpu, panel: ModelsPanel },
  { value: "documents", label: "文档", icon: FileText, panel: DocumentsPanel },
  { value: "notifications", label: "通知", icon: BellRing, panel: NotificationsPanel },
  { value: "usage", label: "用量", icon: BarChart3, panel: UsagePanel },
  { value: "eval", label: "评测", icon: FlaskConical, panel: EvalPanel },
];

export default function Settings() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="type-h2">系统设置</h2>
        <p className="type-body text-muted-foreground">
          模型网关、知识库、通知、用量统计与评测闭环
        </p>
      </div>

      <Tabs defaultValue="models" className="w-full">
        <TabsList variant="line" className="w-full justify-start overflow-x-auto">
          {tabs.map(({ value, label, icon: Icon }) => (
            <TabsTrigger key={value} value={value}>
              <Icon className="h-4 w-4" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        {tabs.map(({ value, panel: Panel }) => (
          <TabsContent key={value} value={value} className="mt-5">
            <Panel />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
