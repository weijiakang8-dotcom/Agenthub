import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { OnboardingGuide } from "@/components/guides/OnboardingGuide";
import { Footer } from "@/components/layout/Footer";

import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { cn } from "@/lib/utils";

const titles: Record<string, string> = {
  "/": "工作区",
  "/chat": "Chat",
  "/dashboard": "Dashboard",
  "/dispatch": "调度中心",
  "/history": "History",
  "/skills": "Skill 库",
  "/agents": "Agent 中心",
  "/savings": "省钱账单",
  "/guide": "使用指南",
  "/workflows": "Workflows",
  "/workflows/editor": "工作流编辑器",
  "/executions": "Executions",
  "/quality": "质量看板",
  "/alerts": "告警中心",
  "/alerts/rules": "告警规则",
  "/settings": "Settings",
};

export function Layout() {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const title = titles[location.pathname] ?? dynamicTitle(location.pathname);

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside
        className={cn(
          "hidden transition-all duration-200 lg:block lg:shrink-0",
          collapsed ? "lg:w-14" : "lg:w-60",
        )}
      >
        <Sidebar collapsed={collapsed} />
      </aside>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-60 p-0">
          <SheetTitle className="sr-only">导航菜单</SheetTitle>
          <Sidebar />
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          title={title}
          onMenuClick={() => setOpen(true)}
          collapsed={collapsed}
          onToggleCollapse={() => setCollapsed((value) => !value)}
        />
        <main
          key={location.pathname}
          className="flex-1 overflow-auto p-4 lg:p-6 animate-in fade-in-0 duration-200"
        >
          <Outlet />
          <OnboardingGuide />
          <Footer />
        </main>
      </div>
    </div>
  );
}

function dynamicTitle(pathname: string): string {
  if (pathname.startsWith("/executions/")) return "执行详情";
  const segment = pathname.split("/").filter(Boolean).pop();
  if (!segment) return "工作区";
  return segment.charAt(0).toUpperCase() + segment.slice(1);
}
