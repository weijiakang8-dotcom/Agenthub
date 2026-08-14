import type { ExecutionStatus } from "@/lib/api";
import { STATUS_META } from "@/lib/format";
import { cn } from "@/lib/utils";

export function StatusBadge({
  status,
  className,
}: {
  status: ExecutionStatus;
  className?: string;
}) {
  const meta = STATUS_META[status];

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        meta.className,
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", meta.dot)} />
      {meta.label}
    </span>
  );
}
