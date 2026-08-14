import type { ExecutionStatus } from "@/lib/api";

export const STATUS_META: Record<
  ExecutionStatus,
  { label: string; className: string; dot: string }
> = {
  pending: {
    label: "待处理",
    className: "bg-slate-100 text-slate-600",
    dot: "bg-slate-400",
  },
  running: {
    label: "运行中",
    className: "bg-amber-100 text-amber-700",
    dot: "bg-amber-500",
  },
  waiting_for_approval: {
    label: "待审核",
    className: "bg-purple-100 text-purple-700",
    dot: "bg-purple-500",
  },
  completed: {
    label: "已完成",
    className: "bg-emerald-100 text-emerald-700",
    dot: "bg-emerald-500",
  },
  failed: {
    label: "失败",
    className: "bg-red-100 text-red-700",
    dot: "bg-red-500",
  },
  rolled_back: {
    label: "已回滚",
    className: "bg-slate-100 text-slate-600",
    dot: "bg-slate-400",
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
