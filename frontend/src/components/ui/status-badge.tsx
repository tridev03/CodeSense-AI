"use client";

import { cn } from "@/lib/utils";

type Status = 'pending' | 'cloning' | 'indexing' | 'indexed' | 'failed' | 'running' | 'completed';

interface StatusBadgeProps {
  status: Status;
  className?: string;
}

const statusConfig: Record<Status, { label: string; className: string }> = {
  pending: { label: "Pending", className: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20" },
  cloning: { label: "Cloning", className: "bg-amber/10 text-amber border-amber/20" },
  indexing: { label: "Indexing", className: "bg-amber/10 text-amber border-amber/20" },
  running: { label: "Running", className: "bg-amber/10 text-amber border-amber/20" },
  indexed: { label: "Indexed", className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" },
  completed: { label: "Completed", className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" },
  failed: { label: "Failed", className: "bg-red-500/10 text-red-400 border-red-500/20" },
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status];
  
  if (!config) return null;

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border",
        config.className,
        className
      )}
    >
      {config.label}
    </span>
  );
}
