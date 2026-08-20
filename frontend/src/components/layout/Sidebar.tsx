import { NavLink } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import {
  LogOut,
  MessageSquare,
  Library,
  Settings,
  Sparkles,
  ListChecks,
  BookOpen,
  Plus,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { clearTokens } from "@/lib/api";
import { Hint } from "@/components/ui/hint";

const items = [
  { to: "/chat", label: "新建对话", icon: Plus },
  { to: "/history", label: "对话历史", icon: MessageSquare },
  { to: "/skills", label: "Skill 库", icon: Library },
  { to: "/executions", label: "执行记录", icon: ListChecks },
  { to: "/settings", label: "模型与设置", icon: Settings },
];

export function Sidebar({ collapsed = false }: { collapsed?: boolean }) {
  const navigate = useNavigate();

  return (
    <div className="glass flex h-full flex-col border-r border-border/60">
      <div
        className={cn(
          "flex h-14 items-center gap-2 border-b border-border/60",
          collapsed ? "justify-center px-2" : "px-4",
        )}
      >
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Sparkles className="h-4 w-4" />
        </div>
        {!collapsed && (
          <span className="text-sm font-semibold tracking-tight">AgentHub</span>
        )}
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {items.map(({ to, label, icon: Icon }) => (
          <Hint
            key={to}
            label={collapsed ? label : `${label}：${({
              "/chat": "创建新的对话任务",
              "/history": "查看历史对话",
              "/skills": "浏览与执行确定性 Skill",
              "/executions": "查看 Agent 执行记录与审计",
              "/guide": "查看使用指南",
              "/settings": "配置模型、知识与通知",
            })[to]}`}
            side={collapsed ? "right" : "top"}
          >
            <NavLink
              to={to}
              title={label}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-all duration-200 hover:bg-secondary hover:text-foreground",
                  isActive && "bg-primary/15 text-primary",
                  collapsed && "justify-center px-0",
                )
              }
            >
              <Icon className="h-4 w-4" />
              {!collapsed && label}
            </NavLink>
          </Hint>
        ))}
      </nav>

      <div className="space-y-2 border-t p-3">
        <Hint label="打开使用指南，快速了解核心流程">
          <button
            type="button"
            title="使用指南"
            onClick={() =>
              window.dispatchEvent(new CustomEvent("agenthub:open-guide"))
            }
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
            collapsed && "justify-center px-0",
          )}
        >
          <BookOpen className="h-3.5 w-3.5" />
          {!collapsed && "使用指南"}
          </button>
        </Hint>
        <Hint label="退出当前账号">
          <button
            type="button"
            onClick={() => {
              clearTokens();
              navigate("/");
            }}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
              collapsed && "justify-center px-0",
            )}
          >
            <LogOut className="h-3.5 w-3.5" />
            {!collapsed && "退出登录"}
          </button>
        </Hint>
        {!collapsed && (
          <p className="text-xs text-muted-foreground">v0.2.0 · MIT</p>
        )}
      </div>
    </div>
  );
}
