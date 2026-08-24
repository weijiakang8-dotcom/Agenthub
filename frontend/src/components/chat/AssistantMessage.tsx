import { Children, isValidElement, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";
import rehypeHighlight from "rehype-highlight";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type CodeBlockProps = {
  children?: ReactNode;
};

function plainText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isValidElement<{ children?: ReactNode }>(node)) return "";
  return Children.toArray(node.props.children).map(plainText).join("");
}

function codeText(children: ReactNode): string {
  return Children.toArray(children).map(plainText).join("").replace(/\n$/, "");
}

function codeLanguage(children: ReactNode): string {
  const child = Children.toArray(children)[0];
  if (!isValidElement<{ className?: string }>(child)) return "代码";
  return child.props.className?.match(/language-([\w-]+)/)?.[1] ?? "代码";
}

function CodeBlock({ children }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const source = codeText(children);
  const language = codeLanguage(children);

  async function copyCode() {
    await navigator.clipboard.writeText(source);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="chat-code-block">
      <div className="chat-code-header">
        <span>{language}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-slate-300 hover:bg-white/10 hover:text-white"
          onClick={copyCode}
          aria-label={copied ? "已复制代码" : "复制代码"}
          title={copied ? "已复制" : "复制代码"}
        >
          {copied ? (
            <Check className="h-3.5 w-3.5" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>
      <pre>{children}</pre>
    </div>
  );
}

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

const markdownComponents: Components = {
  a: ({ children, ...props }) => (
    <a {...props} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  ),
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  code: ({ className, children, ...props }) => (
    <code className={className} {...props}>
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className="chat-table-wrap">
      <table>{children}</table>
    </div>
  ),
};

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
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
          components={markdownComponents}
        >
          {normalizedContent}
        </ReactMarkdown>
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
