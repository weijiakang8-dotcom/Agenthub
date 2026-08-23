import React, { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, HashRouter } from "react-router-dom";
import { openUrl } from "@tauri-apps/plugin-opener";

import "@xyflow/react/dist/style.css";
import "./index.css";

import App from "./App";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  getStoredTheme,
  storeTheme,
  THEME_CHANGED_EVENT,
  type Theme,
} from "@/lib/theme";

const Router =
  import.meta.env.VITE_DESKTOP_CLIENT === "true" ? HashRouter : BrowserRouter;

function Root() {
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme());
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    rootRef.current?.classList.toggle("dark", theme === "dark");
  }, [theme]);

  useEffect(() => {
    const onChange = (event: Event) => {
      const next = (event as CustomEvent<Theme>).detail;
      setTheme(next);
      storeTheme(next);
    };
    window.addEventListener(THEME_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(THEME_CHANGED_EVENT, onChange);
  }, []);

  // 桌面壳内的外部链接交给系统默认浏览器，避免把主窗口导航离开 AgentHub。
  useEffect(() => {
    const isTauri = Boolean(
      (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__,
    );
    if (!isTauri) return;
    const onClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const anchor = target?.closest("a[href^='http']") as HTMLAnchorElement | null;
      if (!anchor) return;
      event.preventDefault();
      openUrl(anchor.href).catch(() => undefined);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  return (
    <div ref={rootRef} className={theme === "dark" ? "dark" : ""}>
      <Router>
        <TooltipProvider>
          <App />
          <Toaster />
        </TooltipProvider>
      </Router>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
