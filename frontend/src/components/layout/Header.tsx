import { Bell, Menu, Moon, PanelLeft, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { AuthModal } from "@/components/AuthModal";
import { getAccessToken, logout } from "@/lib/api";
import {
  getStoredTheme,
  toggleTheme,
  type Theme,
} from "@/lib/theme";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function Header({
  title,
  onMenuClick,
  collapsed,
  onToggleCollapse,
}: {
  title: string;
  onMenuClick: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme());
  const loggedIn = Boolean(getAccessToken());

  useEffect(() => {
    const openAuth = (event: Event) => {
      const mode =
        (event as CustomEvent<string>).detail === "register"
          ? "register"
          : "login";
      setAuthMode(mode);
      setAuthOpen(true);
    };
    window.addEventListener("agenthub:open-auth", openAuth);
    return () => window.removeEventListener("agenthub:open-auth", openAuth);
  }, []);

  return (
    <header className="glass flex h-14 items-center justify-between border-b border-border/60 px-4">
      <div className="flex items-center gap-3">
        <Hint label={collapsed ? "展开侧栏" : "折叠侧栏"}>
          <Button
            variant="ghost"
            size="icon"
            className="hidden lg:inline-flex"
            onClick={onToggleCollapse}
            title={collapsed ? "展开侧栏" : "折叠侧栏"}
          >
            <PanelLeft className="h-4 w-4" />
          </Button>
        </Hint>
        <Hint label="打开菜单">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={onMenuClick}
          >
            <Menu className="h-4 w-4" />
          </Button>
        </Hint>
        <span className="hidden text-sm text-muted-foreground sm:inline">
          synplex
        </span>
        <span className="hidden text-muted-foreground/60 sm:inline">/</span>
        <span className="hidden text-sm font-semibold tracking-tight text-primary sm:inline">
          AgentHub
        </span>
        <span className="hidden text-muted-foreground/60 sm:inline">/</span>
        <h1 className="truncate text-lg font-semibold tracking-tight">
          {title}
        </h1>
      </div>

      <div className="flex items-center gap-2">
        <Hint
          label={
            theme === "dark" ? "切换为浅色日间模式" : "切换为深色夜间模式"
          }
        >
          <Button
            variant="ghost"
            size="icon"
            aria-label={theme === "dark" ? "切换为浅色模式" : "切换为深色模式"}
            onClick={() => setTheme(toggleTheme(theme))}
          >
            {theme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </Button>
        </Hint>
        {!loggedIn && (
          <>
            <Hint label="使用邮箱和密码登录（无需验证码）">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setAuthMode("login");
                  setAuthOpen(true);
                }}
              >
                登录
              </Button>
            </Hint>
            <Hint label="注册新账号（需邮箱验证码）">
              <Button
                size="sm"
                onClick={() => {
                  setAuthMode("register");
                  setAuthOpen(true);
                }}
              >
                注册
              </Button>
            </Hint>
          </>
        )}
        <Hint label="通知">
          <Button variant="ghost" size="icon">
            <Bell className="h-4 w-4" />
          </Button>
        </Hint>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 w-8 rounded-full p-0">
              <Avatar className="h-8 w-8">
                <AvatarFallback className="bg-primary text-xs text-primary-foreground">
                  魏
                </AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuLabel>魏家康</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem>个人设置</DropdownMenuItem>
            <DropdownMenuItem onClick={logout}>退出登录</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <AuthModal open={authOpen} onOpenChange={setAuthOpen} mode={authMode} />
    </header>
  );
}
