import { NavLink } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import {
  LogOut,
  MessageSquare,
  Settings,
  Sparkles,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { setAccessToken } from "@/lib/api";

const items = [
  { to: "/", label: "Chat", icon: MessageSquare, end: true },
  { to: "/history", label: "History", icon: MessageSquare, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
];

export function Sidebar() {
  const navigate = useNavigate();

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

      <div className="space-y-2 border-t p-3">
        <button
          type="button"
          onClick={() => {
            setAccessToken(null);
            navigate("/login");
          }}
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <LogOut className="h-3.5 w-3.5" />
          退出登录
        </button>
        <p className="text-xs text-muted-foreground">v0.1.0 · MIT</p>
      </div>
    </div>
  );
}
