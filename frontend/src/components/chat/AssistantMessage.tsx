import { lazy, Suspense } from "react";

import { cn } from "@/lib/utils";

const MarkdownContent = lazy(() => import("@/components/chat/MarkdownContent"));

export function normalizeAssistantContent(content: string): string {
  const trimmed = content.trim();
  if (!trimmed.startsWith('"') || !trimmed.endsWith('"')) return content;
  try {
    const parsed: unknown = JSON.parse(trimmed);
    return typeof parsed === "string" ? parsed : content;
  } catch {
    return content;
  }
}

export function AssistantMessage({
  content,
  streaming = false,
  className,
}: {
  content: string;
  streaming?: boolean;
  className?: string;
}) {
  const normalizedContent = normalizeAssistantContent(content);

  return (
    <div className={cn("assistant-markdown", className)}>
      {normalizedContent ? (
        <Suspense fallback={<p>{normalizedContent}</p>}>
          <MarkdownContent content={normalizedContent} />
        </Suspense>
      ) : streaming ? null : (
        <p className="text-muted-foreground">（空回复）</p>
      )}
      {streaming ? (
        <span
          className="animate-cursor-blink text-primary"
          aria-label="正在生成"
        >
          ▍
        </span>
      ) : null}
    </div>
  );
}
