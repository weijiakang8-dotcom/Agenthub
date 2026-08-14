import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";

import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

const titles: Record<string, string> = {
  "/": "Dashboard",
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
  const location = useLocation();
  const title =
    titles[location.pathname] ??
    (location.pathname.startsWith("/executions/") ? "执行详情" : "AgentHub");

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="hidden lg:block lg:w-60 lg:shrink-0">
        <Sidebar />
      </aside>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-60 p-0">
          <SheetTitle className="sr-only">导航菜单</SheetTitle>
          <Sidebar />
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <Header title={title} onMenuClick={() => setOpen(true)} />
        <main
          key={location.pathname}
          className="flex-1 overflow-auto p-4 lg:p-6 animate-in fade-in-0 duration-200"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
