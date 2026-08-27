import { Children, isValidElement, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";
import rehypeHighlight from "rehype-highlight";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";

function plainText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isValidElement<{ children?: ReactNode }>(node)) return "";
  return Children.toArray(node.props.children).map(plainText).join("");
}

function CodeBlock({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const source = Children.toArray(children)
    .map(plainText)
    .join("")
    .replace(/\n$/, "");
  const child = Children.toArray(children)[0];
  const language = isValidElement<{ className?: string }>(child)
    ? (child.props.className?.match(/language-([\w-]+)/)?.[1] ?? "代码")
    : "代码";

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

export default function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={markdownComponents}
    >
      {content}
    </ReactMarkdown>
  );
}
