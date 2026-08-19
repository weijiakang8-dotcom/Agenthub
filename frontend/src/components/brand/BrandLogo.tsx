import { cn } from "@/lib/utils";

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

export function BrandLogo({
  className,
  showWordmark = true,
  size = "md",
  layout = "row",
  bright = false,
  wordmark = "AgentHub",
  wordmarkImage = false,
}: BrandLogoProps) {
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
        src="/brand/logo-mark.png"
        srcSet="/brand/logo-mark@2x.png 2x"
        alt={wordmark}
        className={cn(
          "object-contain",
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
