import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  BellRing,
  GitBranch,
  Gauge,
  PlaySquare,
  Settings,
  Sparkles,
  Workflow,
} from "lucide-react";

import { cn } from "@/lib/utils";

const items = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/workflows", label: "Workflows", icon: Workflow, end: false },
  { to: "/workflows/editor", label: "工作流编辑器", icon: GitBranch, end: false },
  { to: "/executions", label: "Executions", icon: PlaySquare, end: false },
  { to: "/quality", label: "质量看板", icon: Gauge, end: false },
  { to: "/alerts", label: "告警中心", icon: BellRing, end: false },
  { to: "/alerts/rules", label: "告警规则", icon: BellRing, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
];

export function Sidebar() {
  return (
    <div className="flex h-full w-60 flex-col border-r bg-white">
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Sparkles className="h-4 w-4" />
        </div>
        <span className="text-sm font-semibold tracking-tight">AgentHub</span>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-all duration-200 hover:bg-secondary hover:text-foreground",
                isActive && "bg-secondary text-foreground",
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t p-3 text-xs text-muted-foreground">
        v0.1.0 · MIT
      </div>
    </div>
  );
}
