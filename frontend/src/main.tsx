import React, { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

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

  return (
    <div ref={rootRef} className={theme === "dark" ? "dark" : ""}>
      <BrowserRouter>
        <TooltipProvider>
          <App />
          <Toaster />
        </TooltipProvider>
      </BrowserRouter>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
