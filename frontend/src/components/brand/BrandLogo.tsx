import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";
import { getStoredTheme, THEME_CHANGED_EVENT, type Theme } from "@/lib/theme";

type BrandLogoProps = {
  className?: string;
  showWordmark?: boolean;
  size?: "sm" | "md" | "lg" | "xl";
  layout?: "row" | "stack";
  bright?: boolean;
  wordmark?: string;
  wordmarkImage?: boolean;
};

const markSize = {
  sm: "h-6 w-6",
  md: "h-8 w-8",
  lg: "h-12 w-12",
  xl: "h-32 w-32 sm:h-36 sm:w-36",
};

const wordmarkSize = {
  sm: "text-sm",
  md: "text-base",
  lg: "text-2xl",
  xl: "text-3xl",
};

const wordmarkImageSize = {
  sm: "h-5",
  md: "h-7",
  lg: "h-10",
  xl: "h-9 sm:h-10",
};

/** 主题感知 Logo：白天黑标、黑夜白标（bright 强制白标，用于 Landing 暗色场景）。 */
function useThemeAwareLogo(): Theme {
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme());
  useEffect(() => {
    const onChange = (event: Event) =>
      setTheme((event as CustomEvent<Theme>).detail);
    window.addEventListener(THEME_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(THEME_CHANGED_EVENT, onChange);
  }, []);
  return theme;
}

export function BrandLogo({
  className,
  showWordmark = true,
  size = "md",
  layout = "row",
  bright = false,
  wordmark = "AgentHub",
  wordmarkImage = false,
}: BrandLogoProps) {
  const theme = useThemeAwareLogo();
  const markSrc = bright
    ? "/brand/logo-mark-light.png"
    : theme === "dark"
      ? "/brand/logo-mark-light.png"
      : "/brand/logo-mark-dark.png";

  return (
    <span
      className={cn(
        "inline-flex shrink-0",
        layout === "stack"
          ? "flex-col items-center gap-3"
          : "items-center gap-2",
        className,
      )}
    >
      <img
        src={markSrc}
        alt={wordmark}
        className={cn(
          "object-contain transition-opacity duration-200",
          markSize[size],
          bright && "brand-mark-bright",
        )}
        draggable={false}
      />
      {showWordmark &&
        (wordmarkImage ? (
          <img
            src="/brand/logo-wordmark-clean.png"
            alt={wordmark}
            className={cn(
              "w-auto object-contain",
              wordmarkImageSize[size],
              bright && "brand-wordmark-bright",
            )}
            draggable={false}
          />
        ) : (
          <span
            className={cn(
              "font-semibold tracking-tight text-foreground",
              wordmarkSize[size],
            )}
          >
            {wordmark}
          </span>
        ))}
    </span>
  );
}
