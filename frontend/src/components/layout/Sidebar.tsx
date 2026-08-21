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
  Wrench,
  Plus,
  Gauge,
  PiggyBank,
  Bot,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { clearTokens } from "@/lib/api";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { Hint } from "@/components/ui/hint";

const items = [
  { to: "/chat", label: "新建对话", icon: Plus },
  { to: "/dispatch", label: "调度中心", icon: Gauge },
  { to: "/history", label: "对话历史", icon: MessageSquare },
  { to: "/skills", label: "Skill 库", icon: Library },
  { to: "/agents", label: "Agent 中心", icon: Bot },
  { to: "/savings", label: "省钱账单", icon: PiggyBank },
  { to: "/tools", label: "工具", icon: Wrench },
  { to: "/executions", label: "执行记录", icon: ListChecks },
  { to: "/guide", label: "使用指南", icon: BookOpen },
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
        <BrandLogo
          size="md"
          showWordmark={!collapsed}
          wordmark="synplex"
        />
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {items.map(({ to, label, icon: Icon }) => (
          <Hint
            key={to}
            label={collapsed ? label : `${label}：${({
              "/chat": "创建新的对话任务",
              "/dispatch": "发布任务前的复杂度评分与路由方案",
              "/history": "查看历史对话",
              "/skills": "预设、自建与自成长 Skill 包",
              "/agents": "自带 Agent 阵容与自更新版本",
              "/savings": "动态路由省下的真金白银",
              "/tools": "查看当前运行时真实工具注册表",
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
                  collapsed ? "justify-center px-0" : "justify-between",
                )
              }
            >
              {!collapsed && label}
              <Icon className="h-4 w-4 shrink-0" />
            </NavLink>
          </Hint>
        ))}
      </nav>

      <div className="space-y-2 border-t p-3">
        <Hint label="打开新手引导，快速了解核心流程">
          <button
            type="button"
            title="新手引导"
            onClick={() =>
              window.dispatchEvent(new CustomEvent("agenthub:open-guide"))
            }
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
              collapsed && "justify-center px-0",
            )}
          >
            <Sparkles className="h-3.5 w-3.5" />
            {!collapsed && "新手引导"}
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
