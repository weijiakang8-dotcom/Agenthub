import type { ExecutionStatus } from "@/lib/api";

export const STATUS_META: Record<
  ExecutionStatus,
  { label: string; className: string; dot: string }
> = {
  pending: {
    label: "待处理",
    className: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground",
  },
  running: {
    label: "运行中",
    className: "bg-agent-running/10 text-agent-running",
    dot: "bg-agent-running",
  },
  waiting_for_approval: {
    label: "待审核",
    className: "bg-agent-waiting/10 text-agent-waiting",
    dot: "bg-agent-waiting",
  },
  completed: {
    label: "已完成",
    className: "bg-agent-completed/10 text-agent-completed",
    dot: "bg-agent-completed",
  },
  failed: {
    label: "失败",
    className: "bg-agent-failed/10 text-agent-failed",
    dot: "bg-agent-failed",
  },
  rolled_back: {
    label: "已回滚",
    className: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground",
  },
};

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  return `${days} 天前`;
}

export function truncate(value: string, length = 30): string {
  return value.length > length ? `${value.slice(0, length)}…` : value;
}
